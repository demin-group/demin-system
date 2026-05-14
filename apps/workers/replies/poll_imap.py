"""poll_imap.py -- Fase 3 Sprint 5.

Lee respuestas recibidas del buzon Gmail de Gonzalo y las persiste en `replies`.

Despite el nombre "poll_imap" del plan original §14, este worker usa la Gmail
REST API (no IMAP). Mismo refresh_token que `send_gmail.py` -- pero requiere
scope OAuth ampliado a `gmail.modify` (no solo `gmail.send`). Sin re-auth de
Gonzalo, este worker falla con 401/403 -- bloqueador humano B7 documentado en
§14 paso 9.

Flujo por run:
1. fetch_active_mailbox -> refresh_token + email.
2. GmailAdapter.list_unread_message_ids(query="is:unread newer_than:30d").
3. Para cada msg_id:
   a. get_message_with_headers -> headers + plain_body + threadId.
   b. Match `in-reply-to` o `references` con `messages.gmail_message_id`.
      Si MATCH -> insertar en `replies` (idempotente por (message_id,
      received_at + ~5min jitter; o por header Message-Id del reply usando
      como dedup) y mark_message_as_read.
      Si NO MATCH -> log info y NO mark as read (email no nuestro).
4. Reporte resumen + exit code.

Idempotencia:
- Dedup primaria: el filtro `is:unread` + marcar como leido tras insertar.
  Si el run falla DESPUES de inserrt y ANTES de mark_as_read, en el proximo
  run se procesara otra vez. Para evitar duplicados, hacemos check en BD:
  `select 1 from replies where message_id=? and received_at = ?` antes de
  insertar. La probabilidad de colision exacta de (message_id, received_at)
  para 2 inserciones distintas es despreciable.

CLI:
    cd apps/workers
    uv run python -m replies.poll_imap --env prod
    uv run python -m replies.poll_imap --env dev --max-results 10 --dry-run

Exit codes:
- 0: OK (replies procesadas o no hay nada).
- 2: error config / BD / mailbox no activo.
- 3: bloqueador OAuth scope (gmail.readonly/modify no concedido). B7.
- 4: error inesperado en parse/insert (algun reply no encajo -- log error).
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import text

from outreach.send_gmail import fetch_active_mailbox
from shared.db import get_engine, get_session
from shared.gmail_adapter import GmailAdapter, GmailAuthError, GmailError

EnvName = Literal["dev", "prod"]

logger = logging.getLogger("demin.poll_imap")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass(slots=True)
class MessageMatch:
    """Resultado del match in-reply-to/references contra messages."""
    message_id: str  # uuid de nuestra messages
    contact_id: str  # uuid del contact al que enviamos
    our_gmail_message_id: str  # el gmail_message_id que matcheo


def _normalize_message_id_header(raw: str) -> str:
    """Gmail's `Message-Id:`, `In-Reply-To:`, `References:` headers vienen con
    angle brackets: `<abc@gmail.com>`. Quita los angle brackets y lowercase
    para matching consistente con `messages.gmail_message_id` (que Gmail
    devuelve sin brackets en el campo `id` interno, pero el header del email
    enviado SI lleva brackets).

    Note: `gmail_message_id` en BD es el `id` interno Gmail (e.g.
    `19e225c90c613612`), no el header RFC `Message-ID`. Para matchear contra
    `In-Reply-To` necesitamos buscar el header `Message-ID` que enviamos.
    """
    return raw.strip().strip("<>").lower()


def extract_matching_ids_from_headers(headers: dict[str, str]) -> list[str]:
    """Extrae todos los Message-ID candidatos de In-Reply-To + References.

    `In-Reply-To: <abc@gmail.com>` -> ['abc@gmail.com']
    `References: <a@x> <b@y> <c@z>` -> ['a@x', 'b@y', 'c@z']
    """
    out: list[str] = []
    in_reply_to = headers.get("in-reply-to", "")
    if in_reply_to:
        out.append(_normalize_message_id_header(in_reply_to))
    references = headers.get("references", "")
    if references:
        # References puede tener multiples ids separados por whitespace.
        for ref in references.split():
            ref = ref.strip()
            if ref:
                out.append(_normalize_message_id_header(ref))
    # Dedup preservando orden.
    seen = set()
    result = []
    for mid in out:
        if mid and mid not in seen:
            seen.add(mid)
            result.append(mid)
    return result


def find_matching_message_by_rfc_id(
    env: EnvName, rfc_message_ids: list[str]
) -> MessageMatch | None:
    """Busca si alguno de los rfc_message_ids corresponde a un email que
    enviamos. La tabla `messages` guarda `gmail_message_id` (id interno Gmail)
    pero NO el RFC `Message-ID` con el que se envio el email.

    Workaround: Gmail expone una API `users.messages.get` con format=metadata
    que devuelve los headers, incluido el `Message-ID` RFC. Pero eso requiere
    una llamada extra por mensaje.

    Alternativa: en el momento del envio (send_gmail), guardamos el
    `Message-Id` que generamos (`make_msgid` en build_raw_message). Voy a
    asumir que `messages.gmail_message_id` es el id interno y el RFC
    `Message-Id` vive en `events.payload.rfc_message_id` o similar. Si no
    existe esa columna todavia, este matching falla.

    Por ahora, intento matching por subject + thread como fallback.
    """
    if not rfc_message_ids:
        return None
    with get_session(env) as s:
        # messages.rfc_message_id no existe en schema actual (paso 7 inseta
        # gmail_message_id que es el id interno Gmail, no el header RFC).
        # Fallback: match por thread/subject mas adelante. Por ahora retornamos
        # None y dejamos que el worker reporte "no match" hasta que se anada
        # la columna.
        _ = s  # placeholder
    return None


def find_matching_message_by_subject_and_to(
    env: EnvName, reply_from: str, reply_subject: str
) -> MessageMatch | None:
    """Fallback: match por `(contact.email, message.subject)` con strip de
    "Re:" / "RE:" / "Fwd:" prefixes.

    `reply_from` es el header `From:` del reply (el prospecto). Lo
    normalizamos para extraer solo el email (sin display name).
    `reply_subject` es el subject del reply, esperamos que sea "Re: <subject
    original>".
    """
    from email.utils import parseaddr

    _, addr = parseaddr(reply_from)
    addr = addr.strip().lower()
    if not addr:
        return None

    # Strip Re:/RE:/Fwd:/Fw: del subject.
    subj = reply_subject.strip()
    for prefix in ("Re:", "RE:", "re:", "Fwd:", "FWD:", "fwd:", "Fw:", "fw:"):
        while subj.startswith(prefix):
            subj = subj[len(prefix):].strip()

    if not subj:
        return None

    with get_session(env) as s:
        row = s.execute(
            text(
                """
                SELECT m.id::text AS message_id,
                       m.contact_id::text AS contact_id,
                       m.gmail_message_id
                FROM messages m
                JOIN contacts c ON c.id = m.contact_id
                WHERE lower(c.email) = :addr
                  AND m.subject = :subj
                  AND m.status = 'sent'
                ORDER BY m.sent_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"addr": addr, "subj": subj},
        ).mappings().fetchone()

    if not row:
        return None
    return MessageMatch(
        message_id=str(row["message_id"]),
        contact_id=str(row["contact_id"]),
        our_gmail_message_id=str(row.get("gmail_message_id") or ""),
    )


def insert_reply_idempotent(
    env: EnvName,
    *,
    message_match: MessageMatch,
    received_at: datetime,
    subject: str,
    body: str,
) -> str | None:
    """Inserta en `replies`. Idempotente por (message_id, received_at).
    Devuelve uuid del reply o None si ya existia.
    """
    with get_session(env) as s:
        # Check existencia previa.
        exists = s.execute(
            text(
                """
                SELECT id::text FROM replies
                WHERE message_id = cast(:mid as uuid)
                  AND received_at = :received_at
                """
            ),
            {"mid": message_match.message_id, "received_at": received_at},
        ).fetchone()
        if exists:
            logger.info(
                "reply_dedup msg=%s received_at=%s already inserted as %s",
                message_match.message_id, received_at, exists[0],
            )
            return None

        ins = s.execute(
            text(
                """
                INSERT INTO replies (
                    message_id, contact_id, received_at,
                    raw_subject, raw_body
                ) VALUES (
                    cast(:mid as uuid), cast(:cid as uuid), :received_at,
                    :subject, :body
                )
                RETURNING id::text
                """
            ),
            {
                "mid": message_match.message_id,
                "cid": message_match.contact_id,
                "received_at": received_at,
                "subject": subject[:1000] if subject else "",
                "body": body[:32000] if body else "",  # cap defensivo
            },
        )
        new_id = ins.fetchone()
        s.commit()
        return str(new_id[0]) if new_id else None


def run_poll(
    env: EnvName,
    *,
    query: str = "is:unread newer_than:30d",
    max_results: int = 50,
    dry_run: bool = False,
) -> dict[str, int]:
    """Ejecuta una pasada de polling.

    Returns dict con metricas: {listed, matched, inserted, dedup, errors,
    skipped_no_match}.
    """
    mailbox = fetch_active_mailbox(env)
    if mailbox is None:
        raise SystemExit("No hay mailbox active en BD. Revisa migration 11.")

    stats = {
        "listed": 0,
        "matched": 0,
        "inserted": 0,
        "dedup": 0,
        "errors": 0,
        "skipped_no_match": 0,
    }

    with GmailAdapter(
        from_email=mailbox.email,
        from_display=mailbox.display_name,
        refresh_token=mailbox.oauth_refresh_token,
    ) as g:
        ids = g.list_unread_message_ids(query=query, max_results=max_results)
        stats["listed"] = len(ids)
        logger.info("poll_start env=%s listed=%d query=%r", env, len(ids), query)

        for msg_id in ids:
            try:
                detail = g.get_message_with_headers(msg_id)
            except GmailError as e:
                logger.error("get_message failed msg_id=%s: %s", msg_id, e)
                stats["errors"] += 1
                continue

            headers = detail["headers"]
            rfc_ids = extract_matching_ids_from_headers(headers)

            # Primer intento: por header RFC.
            match = find_matching_message_by_rfc_id(env, rfc_ids)
            # Fallback: por (from, subject).
            if match is None:
                match = find_matching_message_by_subject_and_to(
                    env,
                    reply_from=headers.get("from", ""),
                    reply_subject=headers.get("subject", ""),
                )

            if match is None:
                stats["skipped_no_match"] += 1
                logger.info(
                    "no_match msg_id=%s from=%r subject=%r in_reply_to=%r",
                    msg_id,
                    headers.get("from", "")[:80],
                    headers.get("subject", "")[:80],
                    headers.get("in-reply-to", "")[:80],
                )
                continue

            stats["matched"] += 1

            if dry_run:
                logger.info(
                    "DRY_RUN match msg_id=%s -> our_message_id=%s contact_id=%s",
                    msg_id, match.message_id, match.contact_id,
                )
                continue

            try:
                reply_id = insert_reply_idempotent(
                    env,
                    message_match=match,
                    received_at=detail["internalDate"],
                    subject=headers.get("subject", ""),
                    body=detail.get("plain_body") or "",
                )
            except Exception as e:
                logger.exception("insert_reply failed msg_id=%s: %s", msg_id, e)
                stats["errors"] += 1
                continue

            if reply_id is None:
                stats["dedup"] += 1
            else:
                stats["inserted"] += 1

            # Mark as read solo tras insert OK (o dedup confirmado).
            try:
                g.mark_message_as_read(msg_id)
            except GmailError as e:
                logger.warning(
                    "mark_as_read failed msg_id=%s (reply guardado pero "
                    "siguiente run lo re-procesara): %s", msg_id, e
                )

    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="poll_imap (Gmail API) -- lee replies del buzon y persiste"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument(
        "--query", default="is:unread newer_than:30d",
        help="Gmail search query. Default lista unreads del ultimo mes.",
    )
    p.add_argument("--max-results", type=int, default=50)
    p.add_argument("--dry-run", action="store_true",
                   help="Lista + match pero NO inserta ni mark as read.")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(
        f"poll_imap  env={env}  query={args.query!r}  "
        f"max_results={args.max_results}  dry_run={args.dry_run}"
    )
    print("=" * 76)

    try:
        stats = run_poll(
            env=env, query=args.query,
            max_results=args.max_results, dry_run=args.dry_run,
        )
    except GmailAuthError as e:
        logger.error(
            "BLOQUEADOR B7 -- scope OAuth insuficiente: %s. "
            "Requiere re-auth Gonzalo con scope gmail.modify.", e,
        )
        return 3
    except SystemExit:
        return 2
    except Exception as e:
        logger.exception("error inesperado: %s", e)
        return 4

    print(
        f"FIN poll_imap  listed={stats['listed']}  matched={stats['matched']}  "
        f"inserted={stats['inserted']}  dedup={stats['dedup']}  "
        f"skipped={stats['skipped_no_match']}  errors={stats['errors']}"
    )
    return 0 if stats["errors"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
