"""poll_imap.py -- Fase 3 Sprint 5.

Lee respuestas recibidas del buzon Gmail de Gonzalo y las persiste en `replies`.

Despite el nombre "poll_imap" del plan original §14, este worker usa la Gmail
REST API (no IMAP). Mismo refresh_token que `send_gmail.py`; requiere scope
`gmail.readonly` o `gmail.modify` -- bloqueador humano B7 resuelto el
2026-05-26 (Leccion 47).

Flujo por run (revision 2026-05-27 tras diagnostico de 3 bugs encadenados):
1. fetch_active_mailbox -> refresh_token + email.
2. GmailAdapter.list_unread_message_ids(query="newer_than:7d") -- SIN
   `is:unread` (decision PM: el bot no marca leidos en Gmail, asi Gonzalo
   conserva la senal humana "que he visto"). Dedup vive en BD.
3. Para cada msg_id: get_message_with_headers + cascada de 3 matchers:
   a. RFC Message-ID via In-Reply-To/References vs messages.rfc_message_id.
   b. Subject (strippeado de Re:/Fwd:/RV:) + From == contact.email exacto.
   c. Subject + dominio del From (60d ventana) -- otra persona del mismo
      dominio respondio (forwards internos).
4. Insert en replies con dedup por gmail_message_id UNIQUE (migration 17).
5. NO marca leido en Gmail (cambio 2026-05-27).

CLI:
    cd apps/workers
    uv run python -m replies.poll_imap --env prod
    uv run python -m replies.poll_imap --env dev --max-results 10 --dry-run
    uv run python -m replies.poll_imap --env prod --query "newer_than:30d"  # backfill

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
    """Match primario: cruza los Message-IDs RFC encontrados en
    In-Reply-To/References del reply contra `messages.rfc_message_id`
    (columna añadida en migration 17 + poblada por send_gmail desde
    2026-05-27). Los valores estan ya normalizados (sin angle brackets,
    lowercase) tanto en BD como en `rfc_message_ids` (via
    `_normalize_message_id_header`).

    Cubre los casos donde el reply viene de OTRA persona del mismo dominio
    (forwards internos) -- el `From:` no matchea con contact.email pero el
    In-Reply-To/References si apuntan al Message-ID que enviamos.

    Devuelve el match mas reciente si hay varios (improbable; un mismo
    rfc_message_id por mensaje, unico).
    """
    if not rfc_message_ids:
        return None
    with get_session(env) as s:
        row = s.execute(
            text(
                """
                SELECT m.id::text AS message_id,
                       m.contact_id::text AS contact_id,
                       m.gmail_message_id
                FROM messages m
                WHERE m.rfc_message_id = ANY(:ids)
                  AND m.status = 'sent'
                ORDER BY m.sent_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"ids": rfc_message_ids},
        ).mappings().fetchone()
    if not row:
        return None
    return MessageMatch(
        message_id=str(row["message_id"]),
        contact_id=str(row["contact_id"]),
        our_gmail_message_id=str(row.get("gmail_message_id") or ""),
    )


def find_matching_message_by_subject_and_to(
    env: EnvName, reply_from: str, reply_subject: str
) -> MessageMatch | None:
    """Fallback 2: match por `(contact.email, message.subject)` con strip
    de prefijos comunes (Re:/RE:/Fwd:/Fw:/RV: español).

    Requiere `From:` del reply == `contact.email` exacto. Para casos donde
    responde otra persona del dominio, ver
    `find_matching_message_by_domain_and_subject`. Para casos con
    threading, ver `find_matching_message_by_rfc_id` (matcher primario).
    """
    from email.utils import parseaddr

    _, addr = parseaddr(reply_from)
    addr = addr.strip().lower()
    if not addr:
        return None

    subj = _strip_reply_prefixes(reply_subject)
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


def find_matching_message_by_domain_and_subject(
    env: EnvName, reply_from: str, reply_subject: str
) -> MessageMatch | None:
    """Fallback 3: match por (dominio del From, message.subject strippeado),
    cuando el email exacto del responder no coincide con ningun
    contact.email. Cubre casos donde otra persona del mismo dominio
    responde (administracion@empresa.es -> alvaro@empresa.es, o variantes
    TLD .com vs .es del mismo nombre).

    Ventana 60d para no atribuir respuestas a outreach muy antiguo. Si
    hay >1 match, elige sent_at mas reciente.
    """
    from email.utils import parseaddr

    _, addr = parseaddr(reply_from)
    addr = addr.strip().lower()
    if not addr or "@" not in addr:
        return None
    domain = addr.split("@", 1)[1]
    if not domain:
        return None

    subj = _strip_reply_prefixes(reply_subject)
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
                WHERE lower(c.email) LIKE :pat
                  AND m.subject = :subj
                  AND m.status = 'sent'
                  AND m.sent_at > now() - interval '60 days'
                ORDER BY m.sent_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"pat": f"%@{domain}", "subj": subj},
        ).mappings().fetchone()

    if not row:
        return None
    return MessageMatch(
        message_id=str(row["message_id"]),
        contact_id=str(row["contact_id"]),
        our_gmail_message_id=str(row.get("gmail_message_id") or ""),
    )


# ─── Deteccion de bounces / DSN (fix 2026-06-04) ───────────────────────────
# Los DSN llegan de postmaster@/mailer-daemon@ con subject tipo
# "Undeliverable: ..."; nunca matchean la cascada (From != contact.email,
# subject con prefijo no strippeado) y quedaban en skipped_no_match. El
# bounce rate de auto_pause (events type='bounce') se infracontaba —
# deuda documentada en auto_pause.py lineas 23-24, cerrada hoy.

_DSN_FROM_MARKERS = ("mailer-daemon@", "postmaster@")

_DSN_SUBJECT_MARKERS = (
    "undeliverable", "undelivered mail", "mail delivery",
    "delivery status notification", "delivery failure", "delivery has failed",
    "returned mail", "failure notice",
    "no se pudo entregar", "entrega fallida", "no se ha podido entregar",
)

_EMAIL_IN_BODY_RE = None  # compilado lazy en extract_bounced_recipient

_DSN_RECIPIENT_HEADER_RE = None


def is_dsn(from_addr: str, subject: str) -> bool:
    """True si el email entrante parece un Delivery Status Notification.

    Conservador: remitente postmaster@/mailer-daemon@ O subject con marcador
    DSN tipico (en/es). No mira el Content-Type porque `get_message_with_headers`
    ya aplana el payload; from+subject cubren los DSN reales observados.
    """
    f = (from_addr or "").lower()
    if any(m in f for m in _DSN_FROM_MARKERS):
        return True
    s = (subject or "").lower()
    return any(m in s for m in _DSN_SUBJECT_MARKERS)


def extract_bounced_recipient(body: str, exclude: set[str]) -> str | None:
    """Extrae la direccion que reboto del cuerpo de un DSN.

    Orden de preferencia:
    1. Headers DSN embebidos: `Final-Recipient: rfc822; x@y` /
       `Original-Recipient: rfc822; x@y` / `X-Failed-Recipients: x@y`.
    2. Fallback: primera direccion del cuerpo que no sea nuestra ni del
       propio postmaster/mailer-daemon/noreply.

    Devuelve lowercase o None si no hay candidata (NO se inventa nada).
    """
    import re as _re

    global _EMAIL_IN_BODY_RE, _DSN_RECIPIENT_HEADER_RE
    if _EMAIL_IN_BODY_RE is None:
        _EMAIL_IN_BODY_RE = _re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
        _DSN_RECIPIENT_HEADER_RE = _re.compile(
            r"(?:final-recipient|original-recipient|x-failed-recipients)\s*:"
            r"(?:\s*rfc822\s*;)?\s*<?([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})>?",
            _re.IGNORECASE,
        )

    if not body:
        return None
    excluded = {e.lower() for e in exclude}

    def acceptable(addr: str) -> bool:
        a = addr.lower()
        if a in excluded:
            return False
        local = a.split("@", 1)[0]
        return local not in ("postmaster", "mailer-daemon", "noreply", "no-reply")

    m = _DSN_RECIPIENT_HEADER_RE.search(body)
    if m and acceptable(m.group(1)):
        return m.group(1).lower()

    for cand in _EMAIL_IN_BODY_RE.findall(body):
        if acceptable(cand):
            return cand.lower()
    return None


def find_sent_message_by_recipient(env: EnvName, recipient: str) -> MessageMatch | None:
    """Message 'sent' mas reciente cuyo contact.email == recipient exacto.
    Para atribuir un DSN al envio que reboto."""
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
                  AND m.status = 'sent'
                ORDER BY m.sent_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"addr": recipient.lower()},
        ).mappings().fetchone()
    if not row:
        return None
    return MessageMatch(
        message_id=str(row["message_id"]),
        contact_id=str(row["contact_id"]),
        our_gmail_message_id=str(row.get("gmail_message_id") or ""),
    )


# Prefijos de reply/forward que strippeamos del subject para matching.
# Incluye RV/R (reenvío español), Fwd/Fw (forward ingles), Re/RE (reply).
_REPLY_PREFIXES = (
    "Re:", "RE:", "re:",
    "Fwd:", "FWD:", "fwd:",
    "Fw:", "FW:", "fw:",
    "RV:", "Rv:", "rv:",
    "R:", "r:",
)


def _strip_reply_prefixes(subject: str) -> str:
    """Strip iterativo de prefijos reply/forward. Soporta "Re: RV:"
    encadenados (subject reenviado de un reply)."""
    subj = subject.strip()
    changed = True
    while changed:
        changed = False
        for prefix in _REPLY_PREFIXES:
            if subj.startswith(prefix):
                subj = subj[len(prefix):].strip()
                changed = True
                break
    return subj


def insert_reply_idempotent(
    env: EnvName,
    *,
    message_match: MessageMatch,
    gmail_message_id: str,
    received_at: datetime,
    subject: str,
    body: str,
    category: str | None = None,
    classification_reason: str | None = None,
) -> str | None:
    """Inserta en `replies`. Dedup primario por `gmail_message_id` (UNIQUE
    desde migration 17). Si ya existe -> skip silencioso. Devuelve uuid
    del reply o None si ya existia.

    `category` preseteada (fix DSN 2026-06-04): los bounces detectados
    estructuralmente entran con category='rebote' directa — no necesitan
    LLM (classify_replies solo procesa category IS NULL) y handle_actions
    los recoge en su rama rebote.
    """
    with get_session(env) as s:
        # Dedup primario por gmail_message_id.
        exists = s.execute(
            text("SELECT id::text FROM replies WHERE gmail_message_id = :gmid"),
            {"gmid": gmail_message_id},
        ).fetchone()
        if exists:
            logger.info(
                "reply_dedup gmail_id=%s already inserted as %s",
                gmail_message_id, exists[0],
            )
            return None

        ins = s.execute(
            text(
                """
                INSERT INTO replies (
                    message_id, contact_id, received_at,
                    raw_subject, raw_body, gmail_message_id,
                    category, ai_classification_reason
                ) VALUES (
                    cast(:mid as uuid), cast(:cid as uuid), :received_at,
                    :subject, :body, :gmid,
                    :category, :cls_reason
                )
                RETURNING id::text
                """
            ),
            {
                "mid": message_match.message_id,
                "cid": message_match.contact_id,
                "received_at": received_at,
                "subject": subject[:1000] if subject else "",
                "body": body[:32000] if body else "",
                "gmid": gmail_message_id,
                "category": category,
                "cls_reason": classification_reason,
            },
        )
        new_id = ins.fetchone()
        s.commit()
        return str(new_id[0]) if new_id else None


def run_poll(
    env: EnvName,
    *,
    query: str = "newer_than:7d",
    max_results: int = 100,
    dry_run: bool = False,
) -> dict[str, int]:
    """Ejecuta una pasada de polling.

    Query default `newer_than:7d` (sin `is:unread`) -- decision PM 2026-05-27:
    el bot NO marca leidos en Gmail (Gonzalo conserva la senal humana
    "que he visto"). Dedup primario por `replies.gmail_message_id UNIQUE`
    impide doble insert si el mismo mensaje aparece en runs sucesivos.

    Matcher en 3 niveles:
    1. RFC Message-ID via In-Reply-To/References vs messages.rfc_message_id
       (cubre forwards internos donde el From: del reply no coincide con
       contact.email).
    2. Subject + From exacto (caso normal donde responde la misma persona
       que recibio el outreach).
    3. Subject + dominio del From (60d ventana) -- otra persona del mismo
       dominio respondio. Log explicito para auditoria.

    Returns dict con metricas: {listed, matched_rfc, matched_subject,
    matched_domain, inserted, dedup, errors, skipped_no_match}.
    """
    mailbox = fetch_active_mailbox(env)
    if mailbox is None:
        raise SystemExit("No hay mailbox active en BD. Revisa migration 11.")

    stats = {
        "listed": 0,
        "matched_rfc": 0,
        "matched_subject": 0,
        "matched_domain": 0,
        "inserted": 0,
        "dedup": 0,
        "errors": 0,
        "skipped_no_match": 0,
        "dsn_bounces": 0,
        "dsn_unattributed": 0,
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
            from_addr = headers.get("from", "")
            subj_raw = headers.get("subject", "")
            rfc_ids = extract_matching_ids_from_headers(headers)

            # Skip emails que enviamos NOSOTROS (gonzalo.perez@...). Gmail
            # devuelve sent items en la query newer_than sin is:unread.
            if mailbox.email.lower() in from_addr.lower():
                continue

            # Rama DSN/bounce (fix 2026-06-04) — ANTES de la cascada: los
            # DSN nunca matchean (From=postmaster, subject "Undeliverable:")
            # y se perdian como skipped_no_match.
            if is_dsn(from_addr, subj_raw):
                recipient = extract_bounced_recipient(
                    detail.get("plain_body") or "", {mailbox.email}
                )
                bounce_match = (
                    find_sent_message_by_recipient(env, recipient)
                    if recipient else None
                )
                if bounce_match is None:
                    stats["dsn_unattributed"] += 1
                    logger.warning(
                        "dsn_unattributed msg_id=%s from=%r subject=%r recipient=%r",
                        msg_id, from_addr[:80], subj_raw[:80], recipient,
                    )
                    continue
                if dry_run:
                    logger.info(
                        "DRY_RUN dsn msg_id=%s recipient=%s -> our_message_id=%s",
                        msg_id, recipient, bounce_match.message_id,
                    )
                    continue
                try:
                    reply_id = insert_reply_idempotent(
                        env,
                        message_match=bounce_match,
                        gmail_message_id=msg_id,
                        received_at=detail["internalDate"],
                        subject=subj_raw,
                        body=detail.get("plain_body") or "",
                        category="rebote",
                        classification_reason=f"dsn_poll_imap: bounce de {recipient}",
                    )
                except Exception as e:
                    logger.exception("insert dsn reply failed msg_id=%s: %s", msg_id, e)
                    stats["errors"] += 1
                    continue
                if reply_id is None:
                    stats["dedup"] += 1
                else:
                    stats["dsn_bounces"] += 1
                    logger.info(
                        "dsn_bounce_inserted id=%s recipient=%s contact_msg=%s",
                        reply_id, recipient, bounce_match.message_id,
                    )
                continue

            # Cascada de 3 matchers.
            match = find_matching_message_by_rfc_id(env, rfc_ids)
            match_kind = "rfc" if match else None
            if match is None:
                match = find_matching_message_by_subject_and_to(
                    env, reply_from=from_addr, reply_subject=subj_raw,
                )
                match_kind = "subject" if match else None
            if match is None:
                match = find_matching_message_by_domain_and_subject(
                    env, reply_from=from_addr, reply_subject=subj_raw,
                )
                match_kind = "domain" if match else None

            if match is None:
                stats["skipped_no_match"] += 1
                logger.info(
                    "no_match msg_id=%s from=%r subject=%r in_reply_to=%r",
                    msg_id, from_addr[:80], subj_raw[:80],
                    headers.get("in-reply-to", "")[:80],
                )
                continue

            stats["matched_" + match_kind] += 1
            if match_kind == "domain":
                logger.info(
                    "matched_by=domain_fallback contact_msg=%s reply_from=%s subject=%r",
                    match.message_id, from_addr[:80], subj_raw[:80],
                )

            if dry_run:
                logger.info(
                    "DRY_RUN match[%s] msg_id=%s -> our_message_id=%s contact_id=%s",
                    match_kind, msg_id, match.message_id, match.contact_id,
                )
                continue

            try:
                reply_id = insert_reply_idempotent(
                    env,
                    message_match=match,
                    gmail_message_id=msg_id,
                    received_at=detail["internalDate"],
                    subject=subj_raw,
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
                logger.info(
                    "reply_inserted id=%s matched_by=%s msg_id=%s contact_msg=%s",
                    reply_id, match_kind, msg_id, match.message_id,
                )

    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="poll_imap (Gmail API) -- lee replies del buzon y persiste"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument(
        "--query", default="newer_than:7d",
        help="Gmail search query. Default: ultimos 7 dias (sin is:unread, "
             "decision PM 2026-05-27).",
    )
    p.add_argument("--max-results", type=int, default=100)
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
        f"FIN poll_imap  listed={stats['listed']}  "
        f"matched_rfc={stats['matched_rfc']}  "
        f"matched_subject={stats['matched_subject']}  "
        f"matched_domain={stats['matched_domain']}  "
        f"inserted={stats['inserted']}  dedup={stats['dedup']}  "
        f"dsn_bounces={stats['dsn_bounces']}  "
        f"dsn_unattributed={stats['dsn_unattributed']}  "
        f"skipped={stats['skipped_no_match']}  errors={stats['errors']}"
    )
    return 0 if stats["errors"] == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
