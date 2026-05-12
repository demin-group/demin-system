"""send_gmail.py -- Sprint 4 paso 7. Envio real Gmail API.

Lee `messages` con `status='approved'` cuyo `mailbox.status='active'`, los
envia respetando cap diario (`mailboxes.daily_cap`), ventana horaria 9-13
y 15-18 hora Madrid, weekday only, y jitter aleatorio entre envios.
Actualiza `messages.status='sent'` con `gmail_message_id`, inserta evento
`message_sent` (o `bounce`/`failed` segun corresponda) y refresca el
contador `mailboxes.current_day_sent`.

Modelo de scheduling (D22 paso 7):
- El operador (o cron) llama el worker durante ventana 9-13 o 15-18 Madrid.
  Fuera de ventana, --max-sends > 0 falla con exit code 4 (mensaje claro)
  -- evita envios accidentales fuera de horario.
- Dentro de ventana, toma hasta `--max-sends` messages approved ordenados
  por `approved_at asc` (FIFO de la cola HITL).
- Entre envios, sleep aleatorio 0 a `--jitter-max-min` minutos (default 5;
  conservador para que un --max-sends 20 termine en ~90 min razonables).
- Cap diario: count(events.type='message_sent' joining messages.mailbox_id
  donde created_at > now() - interval '1 day'). Si cap alcanzado, aborta.

Pre-requisitos (bloqueador humano B1 hasta resolverse):
- Mailbox active con `oauth_refresh_token_encrypted` poblado.
- Settings.GMAIL_OAUTH_CLIENT_ID/SECRET poblados.

Hard bounces invisibles (no llegan como respuesta sincronica) requieren
poll_imap (Fase 3). Para paso 7 captura solo bounces sync detectados en
respuesta 4xx Gmail con mensaje tipo "Invalid To"/"Recipient"/"domain";
otros 4xx van a `status='failed'`. auto_pause vigila events.type='bounce'
y events.type='message_failed' como senales tempranas.

Footer opt-out + firma se anade al body antes del envio (decision PM
1.3 paso 7: no en generate_draft -- el LLM no se pelea con texto fijado).

CLI:
    cd apps/workers
    uv run python -m outreach.send_gmail --env dev --max-sends 1 --dry-run
    uv run python -m outreach.send_gmail --env dev --max-sends 5
    uv run python -m outreach.send_gmail --env prod --max-sends 20

Override de destino para smoke pre-envio real (decision PM 1.5 paso 7):
    uv run python -m outreach.send_gmail --env dev --max-sends 1 \\
        --override-to albertobueno10@gmail.com
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import text

from shared.config import settings
from shared.db import get_session
from shared.gmail_adapter import (
    GmailAdapter,
    GmailAuthError,
    GmailError,
    GmailQuotaError,
    SendResult,
)

EnvName = Literal["dev", "prod"]

MADRID = ZoneInfo("Europe/Madrid")

# Ventana horaria laboral Madrid (§9.3)
_WORK_HOURS: list[tuple[int, int]] = [(9, 13), (15, 18)]

_DEFAULT_MAX_SENDS = 5
_DEFAULT_JITTER_MAX_MIN = 5

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
"""scripts/seed_oauth_token.py guarda 3 formatos en
mailboxes.oauth_refresh_token_encrypted: UUID (Vault secret id),
'PLAINTEXT:<token>' (Vault no disponible, plaintext con marca), o el
refresh_token directo (legacy / seed manual). resolve_refresh_token
los normaliza."""

_BOUNCE_KEYWORDS = (
    "invalid to",
    "invalid recipient",
    "recipient address rejected",
    "domain not found",
    "no such user",
    "user unknown",
    "address does not exist",
)
"""Substrings (case-insensitive) en el mensaje de error 4xx Gmail que
clasificamos como bounce sincrono. El resto de 4xx -> 'failed'."""

# Footer fijo (decision PM 2026-05-12 D24 paso 7 pre-B5). §9.3 derogada
# en su linea de opt-out -- ver D24 + Leccion 32 para justificacion y
# riesgo aceptado. Separador estandar '-- \n' (RFC 3676). Telefono
# `+34 692 319 217` verificado contra dossier comercial + onboarding PDF
# (docs/). Plaintext puro (§9.3 mantiene plain text para deliverability).
_FOOTER = (
    "\n\n-- \n"
    "Gonzalo Perez\n"
    "Responsable DEMIN Group\n"
    "demingroupmadrid.com\n"
    "+34 692 319 217"
)

logger = logging.getLogger("demin.send_gmail")
if not logger.handlers:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# --- Datos ----------------------------------------------------------------


@dataclass(slots=True)
class MailboxRow:
    id: str
    email: str
    display_name: str
    daily_cap: int
    status: str
    oauth_refresh_token: str | None


@dataclass(slots=True)
class PendingMessage:
    message_id: str
    contact_id: str
    contact_email: str
    company_nif: str
    company_nombre: str
    subject: str
    body: str
    step_index: int
    in_reply_to: str | None  # gmail_message_id del step anterior, si hay


# --- Helpers de tiempo ----------------------------------------------------


def is_business_hours(now: datetime | None = None) -> bool:
    """True si `now` (UTC default) cae en ventana 9-13 o 15-18 Madrid,
    lunes a viernes."""
    if now is None:
        now = datetime.now(timezone.utc)
    local = now.astimezone(MADRID)
    if local.weekday() >= 5:  # 5=sat, 6=sun
        return False
    hour_decimal = local.hour + local.minute / 60.0
    for start, end in _WORK_HOURS:
        if start <= hour_decimal < end:
            return True
    return False


def build_full_body(generated_body: str) -> str:
    """Anade footer opt-out + firma al body generado por LLM."""
    return generated_body.rstrip() + _FOOTER


# --- Acceso a BD ----------------------------------------------------------


def resolve_refresh_token(env: EnvName, raw: str | None) -> str | None:
    """Resuelve el contenido de mailboxes.oauth_refresh_token_encrypted al
    refresh_token real Gmail. Soporta 3 formatos que scripts/seed_oauth_token.py
    puede haber persistido:

    - UUID de Supabase Vault secret -> SELECT decrypted_secret FROM
      vault.decrypted_secrets WHERE id = :uuid (caso happy con Vault).
    - 'PLAINTEXT:<token>' -> strip prefijo (caso Vault no disponible).
    - else -> asume plaintext directo (caso seed manual o legacy).

    Devuelve None si raw es None/vacio. Levanta RuntimeError si UUID parece
    valido pero vault.decrypted_secrets no devuelve nada (secret borrado o
    permisos faltantes en el role)."""
    if not raw:
        return None
    if raw.startswith("PLAINTEXT:"):
        return raw[len("PLAINTEXT:"):]
    if _UUID_RE.match(raw):
        with get_session(env) as s:
            decrypted = s.execute(
                text(
                    "SELECT decrypted_secret FROM vault.decrypted_secrets "
                    "WHERE id = cast(:uuid as uuid)"
                ),
                {"uuid": raw},
            ).scalar()
        if not decrypted:
            raise RuntimeError(
                f"vault secret id={raw} no encontrado en "
                "vault.decrypted_secrets. Secret borrado o el role actual "
                "no tiene grant para leer la view."
            )
        return str(decrypted)
    return raw


def fetch_active_mailbox(env: EnvName) -> MailboxRow | None:
    """Devuelve el unico mailbox active. Si hay >1, devuelve el primero
    y loggea warning (estado anomalo -- Leccion 4 prescribe 1+warm standby)."""
    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT id, email, display_name, daily_cap, status,
                       oauth_refresh_token_encrypted AS rt
                FROM mailboxes
                WHERE status = 'active'
                ORDER BY email ASC
                """
            )
        ).mappings().all()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "mas de un mailbox active (%d) -- usando %s. Leccion 4 prescribe 1.",
            len(rows), rows[0]["email"],
        )
    r = rows[0]
    return MailboxRow(
        id=str(r["id"]),
        email=r["email"],
        display_name=r["display_name"] or r["email"],
        daily_cap=int(r["daily_cap"]),
        status=r["status"],
        oauth_refresh_token=resolve_refresh_token(env, r["rt"]),
    )


def count_sent_last_24h(env: EnvName, mailbox_id: str) -> int:
    """Cuenta events.type='message_sent' joining messages.mailbox_id en
    las ultimas 24h. Fuente unica de la verdad para el cap diario rolling
    (mailboxes.current_day_sent queda como cache informativo)."""
    with get_session(env) as s:
        return int(s.execute(
            text(
                """
                SELECT count(*) FROM events e
                JOIN messages m ON m.id = e.message_id
                WHERE e.type = 'message_sent'
                  AND m.mailbox_id = cast(:mid as uuid)
                  AND e.created_at > now() - interval '1 day'
                """
            ),
            {"mid": mailbox_id},
        ).scalar() or 0)


def fetch_approved_messages(env: EnvName, limit: int) -> list[PendingMessage]:
    """Trae messages status='approved' con datos del contact + company,
    ordenados FIFO por approved_at.

    in_reply_to (gmail_message_id del step anterior) se inferira a partir
    del message sent previo para el mismo contact con step_index < actual.
    NULL para opening (step 0).
    """
    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT
                    m.id AS message_id,
                    m.subject,
                    m.body,
                    m.step_index,
                    ct.id AS contact_id,
                    ct.email AS contact_email,
                    c.nif AS company_nif,
                    c.nombre AS company_nombre,
                    (
                        SELECT m_prev.gmail_message_id
                        FROM messages m_prev
                        WHERE m_prev.contact_id = ct.id
                          AND m_prev.step_index < m.step_index
                          AND m_prev.status = 'sent'
                          AND m_prev.gmail_message_id IS NOT NULL
                        ORDER BY m_prev.step_index DESC
                        LIMIT 1
                    ) AS in_reply_to
                FROM messages m
                JOIN contacts ct ON ct.id = m.contact_id
                JOIN companies c ON c.id = ct.company_id
                WHERE m.status = 'approved'
                  AND ct.is_optout = false
                ORDER BY m.approved_at ASC NULLS FIRST, m.created_at ASC
                LIMIT :n
                """
            ),
            {"n": int(limit)},
        ).mappings().all()
    return [
        PendingMessage(
            message_id=str(r["message_id"]),
            contact_id=str(r["contact_id"]),
            contact_email=r["contact_email"],
            company_nif=r["company_nif"],
            company_nombre=r["company_nombre"],
            subject=r["subject"],
            body=r["body"],
            step_index=int(r["step_index"]),
            in_reply_to=r["in_reply_to"],
        )
        for r in rows
    ]


def persist_send_success(
    env: EnvName,
    msg: PendingMessage,
    mailbox_id: str,
    result: SendResult,
) -> None:
    """UPDATE messages a sent + INSERT event message_sent.
    Tambien UPDATE mailboxes.current_day_sent como cache."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages
                SET status = 'sent',
                    mailbox_id = cast(:mid as uuid),
                    sent_at = :sat,
                    gmail_message_id = :gmid
                WHERE id = cast(:mid_msg as uuid)
                """
            ),
            {
                "mid": mailbox_id,
                "mid_msg": msg.message_id,
                "sat": result.sent_at,
                "gmid": result.gmail_message_id,
            },
        )
        s.execute(
            text(
                """
                INSERT INTO events (type, message_id, contact_id, payload)
                VALUES ('message_sent', cast(:mid_msg as uuid),
                        cast(:cid as uuid), cast(:payload as jsonb))
                """
            ),
            {
                "mid_msg": msg.message_id,
                "cid": msg.contact_id,
                "payload": json.dumps({
                    "gmail_message_id": result.gmail_message_id,
                    "to": msg.contact_email,
                    "subject": msg.subject,
                    "step_index": msg.step_index,
                }),
            },
        )
        s.execute(
            text(
                """
                UPDATE mailboxes
                SET current_day_sent = current_day_sent + 1
                WHERE id = cast(:mid as uuid)
                """
            ),
            {"mid": mailbox_id},
        )


def persist_send_failure(
    env: EnvName,
    msg: PendingMessage,
    mailbox_id: str,
    result: SendResult,
    is_bounce: bool,
) -> None:
    """UPDATE messages a bounced/failed + INSERT event."""
    new_status = "bounced" if is_bounce else "failed"
    event_type = "bounce" if is_bounce else "message_failed"
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages
                SET status = :st,
                    mailbox_id = cast(:mid as uuid)
                WHERE id = cast(:mid_msg as uuid)
                """
            ),
            {
                "st": new_status,
                "mid": mailbox_id,
                "mid_msg": msg.message_id,
            },
        )
        s.execute(
            text(
                """
                INSERT INTO events (type, message_id, contact_id, payload)
                VALUES (:et, cast(:mid_msg as uuid),
                        cast(:cid as uuid), cast(:payload as jsonb))
                """
            ),
            {
                "et": event_type,
                "mid_msg": msg.message_id,
                "cid": msg.contact_id,
                "payload": json.dumps({
                    "to": msg.contact_email,
                    "http_status": result.http_status,
                    "error": result.error,
                    "step_index": msg.step_index,
                }),
            },
        )


# --- Clasificacion 4xx ----------------------------------------------------


def classify_error_as_bounce(error: str | None) -> bool:
    """True si el error 4xx Gmail huele a bounce sincronico (mailbox/
    domain invalido). False -> 'failed' (cuota, suspendido, etc.)."""
    if not error:
        return False
    lower = error.lower()
    return any(kw in lower for kw in _BOUNCE_KEYWORDS)


# --- Loop principal -------------------------------------------------------


def send_loop(
    env: EnvName,
    mailbox: MailboxRow,
    messages: list[PendingMessage],
    *,
    dry_run: bool,
    jitter_max_min: int,
    override_to: str | None,
) -> tuple[int, int, int]:
    """Procesa los mensajes secuencialmente con jitter entre cada uno.
    Devuelve (sent, bounced, failed)."""
    if not mailbox.oauth_refresh_token:
        raise RuntimeError(
            f"mailbox {mailbox.email} no tiene oauth_refresh_token poblado. "
            "Resuelve bloqueador B1 (Gmail OAuth) antes de enviar."
        )

    sent = bounced = failed = 0

    with GmailAdapter(
        from_email=mailbox.email,
        from_display=mailbox.display_name,
        refresh_token=mailbox.oauth_refresh_token,
    ) as g:
        for i, msg in enumerate(messages, 1):
            to_addr = override_to or msg.contact_email
            full_body = build_full_body(msg.body)

            if dry_run:
                logger.info(
                    "[dry-run] %d/%d would send to=%s subject=%r in_reply_to=%s",
                    i, len(messages), to_addr, msg.subject[:50], msg.in_reply_to,
                )
                sent += 1
                continue

            try:
                result = g.send_email(
                    to=to_addr,
                    subject=msg.subject,
                    body=full_body,
                    in_reply_to=msg.in_reply_to,
                )
            except GmailAuthError as e:
                # Auth bloquea TODO el batch -- refresh_token revocado.
                logger.error("gmail auth error, abortando batch: %s", e)
                raise
            except GmailQuotaError as e:
                logger.error("gmail quota agotada, abortando batch: %s", e)
                raise

            if result.success:
                persist_send_success(env, msg, mailbox.id, result)
                sent += 1
                logger.info(
                    "[%d/%d] sent nif=%s to=%s gmail_id=%s",
                    i, len(messages), msg.company_nif, to_addr,
                    result.gmail_message_id,
                )
            else:
                is_bounce = classify_error_as_bounce(result.error)
                persist_send_failure(env, msg, mailbox.id, result, is_bounce)
                if is_bounce:
                    bounced += 1
                    logger.warning(
                        "[%d/%d] BOUNCE nif=%s to=%s err=%s",
                        i, len(messages), msg.company_nif, to_addr, result.error,
                    )
                else:
                    failed += 1
                    logger.error(
                        "[%d/%d] FAILED nif=%s to=%s status=%s err=%s",
                        i, len(messages), msg.company_nif, to_addr,
                        result.http_status, result.error,
                    )

            # Jitter entre envios (no antes del primero, no despues del ultimo)
            if i < len(messages):
                delta = random.uniform(0, jitter_max_min * 60.0)
                logger.info("jitter %.1fs antes del siguiente envio", delta)
                time.sleep(delta)

    return sent, bounced, failed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument(
        "--max-sends",
        type=int,
        default=_DEFAULT_MAX_SENDS,
        help=f"Tope de envios en este run (default {_DEFAULT_MAX_SENDS}).",
    )
    p.add_argument(
        "--jitter-max-min",
        type=int,
        default=_DEFAULT_JITTER_MAX_MIN,
        help=f"Jitter maximo entre envios en minutos (default {_DEFAULT_JITTER_MAX_MIN}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Loggea que enviaria sin contactar Gmail ni mutar BD.",
    )
    p.add_argument(
        "--override-to",
        type=str,
        default=None,
        help="Sustituye `to` por esta direccion en todos los envios. Para "
             "smoke pre-envio real (decision PM 1.5 paso 7).",
    )
    p.add_argument(
        "--skip-business-hours-check",
        action="store_true",
        help="Salta el guard de ventana 9-13/15-18 Madrid. Solo para tests/smoke.",
    )
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(
        f"send_gmail  env={env}  max_sends={args.max_sends}  "
        f"dry_run={args.dry_run}  override_to={args.override_to}"
    )
    print("=" * 76)

    # Guard 1: ventana horaria
    if not args.skip_business_hours_check and not is_business_hours():
        now_madrid = datetime.now(timezone.utc).astimezone(MADRID)
        print(
            f"FUERA DE VENTANA -- hora Madrid {now_madrid:%Y-%m-%d %H:%M} "
            f"({now_madrid.strftime('%A')}). Ventana: lun-vie 9-13 y 15-18."
        )
        return 4

    # Guard 2: mailbox active con refresh_token
    mailbox = fetch_active_mailbox(env)
    if not mailbox:
        print("ERROR: no hay mailbox con status='active'. Aborta.")
        return 1
    if not mailbox.oauth_refresh_token:
        print(
            f"ERROR: mailbox {mailbox.email} sin oauth_refresh_token. "
            f"Resuelve bloqueador B1 (Gmail OAuth)."
        )
        return 2
    print(f"[mailbox] {mailbox.email} cap={mailbox.daily_cap}")

    # Guard 3: cap diario rolling 24h
    sent_24h = count_sent_last_24h(env, mailbox.id)
    remaining = mailbox.daily_cap - sent_24h
    print(f"[cap] sent_24h={sent_24h} cap={mailbox.daily_cap} remaining={remaining}")
    if remaining <= 0:
        print("CAP DIARIO ALCANZADO -- nada que enviar.")
        return 5

    effective_limit = min(args.max_sends, remaining)
    if effective_limit < args.max_sends:
        print(
            f"[cap] reduciendo max_sends de {args.max_sends} a {effective_limit} "
            f"para no superar cap diario"
        )

    # Fetch
    pending = fetch_approved_messages(env, effective_limit)
    if not pending:
        print("No hay messages approved. Nada que enviar.")
        return 0
    print(f"[fetch] {len(pending)} messages approved a procesar")
    for m in pending:
        target = args.override_to or m.contact_email
        print(
            f"  msg={m.message_id[:8]} nif={m.company_nif} "
            f"to={target} step={m.step_index} subj={m.subject[:40]!r}"
        )
    print()

    try:
        sent, bounced, failed = send_loop(
            env, mailbox, pending,
            dry_run=args.dry_run,
            jitter_max_min=args.jitter_max_min,
            override_to=args.override_to,
        )
    except (GmailAuthError, GmailQuotaError, GmailError) as e:
        print(f"ABORT por error Gmail: {e}")
        return 3

    print()
    print("=" * 76)
    print(
        f"FIN send_gmail  env={env}  "
        f"sent={sent}  bounced={bounced}  failed={failed}"
    )
    print("=" * 76)
    return 0 if (bounced + failed) == 0 else 6


if __name__ == "__main__":
    sys.exit(main())
