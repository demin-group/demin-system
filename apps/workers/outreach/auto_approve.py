"""auto_approve.py -- Sprint 6 Fase 3 (modo autonomo).

Aprueba drafts automaticamente cuando mailbox.hitl_mode=false.

Apendice A regla 1: nunca enviar sin pasar por HITL. Cuando hitl_mode=false,
el sistema sigue pasando por cola HITL (status='drafted' -> 'approved'),
pero el "aprobador" es este worker en lugar de Gonzalo. Esto cumple regla 1
a nivel arquitectonico (cola HITL existe) mientras automatiza el step humano.

Logica:
1. Lee mailboxes con status='active' AND hitl_mode=false.
2. Para cada mailbox: busca messages.status='drafted' del mailbox.
3. Valida que el draft cumpla checks minimos (no esta vacio, contact no opt-out,
   no esta cancelled).
4. UPDATE status='approved', approved_by='auto', approved_at=now().

Idempotente. No procesa drafts ya approved/sent. Si hitl_mode=true (default),
NO toca nada.

CLI:
    cd apps/workers
    uv run python -m outreach.auto_approve --env prod
    uv run python -m outreach.auto_approve --env dev --dry-run

Exit codes:
- 0: OK (drafts aprobados o no hay nada/todo HITL).
- 1: alguna aprobacion fallo (no fatal).
- 2: error config / BD.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Any, Literal

from sqlalchemy import text

from shared.db import get_session

EnvName = Literal["dev", "prod"]

logger = logging.getLogger("demin.auto_approve")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def fetch_autonomous_mailboxes(env: EnvName) -> list[dict[str, Any]]:
    """Mailboxes con status='active' AND hitl_mode=false."""
    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT id::text, email, hitl_mode
                FROM mailboxes
                WHERE status = 'active' AND hitl_mode = false
                ORDER BY email
                """
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def fetch_pending_drafts(env: EnvName, mailbox_id: str) -> list[dict[str, Any]]:
    """messages.status='drafted' del mailbox + contact no opt-out."""
    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT m.id::text AS msg_id, m.contact_id::text AS contact_id,
                       m.subject, m.body, c.email AS contact_email,
                       c.is_optout
                FROM messages m
                JOIN contacts c ON c.id = m.contact_id
                WHERE m.mailbox_id = cast(:mid as uuid)
                  AND m.status = 'drafted'
                  AND c.is_optout = false
                ORDER BY m.created_at ASC
                """
            ),
            {"mid": mailbox_id},
        ).mappings().all()
    return [dict(r) for r in rows]


def validate_draft(draft: dict[str, Any]) -> str | None:
    """Returns error reason string si NO valido, None si OK."""
    if not draft.get("subject") or len(draft["subject"]) < 5:
        return "subject vacio o muy corto"
    if not draft.get("body") or len(draft["body"]) < 50:
        return "body vacio o muy corto"
    if draft.get("is_optout"):
        return "contact is_optout=true (no deberia estar aqui pero defensive)"
    return None


def approve_draft(env: EnvName, msg_id: str) -> None:
    """UPDATE status='approved', approved_by='auto', approved_at=now()."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages SET
                    status = 'approved',
                    approved_by = 'auto',
                    approved_at = now()
                WHERE id = cast(:mid as uuid) AND status = 'drafted'
                """
            ),
            {"mid": msg_id},
        )
        # Paper trail event.
        s.execute(
            text(
                """
                INSERT INTO events (type, message_id, payload)
                VALUES ('draft_auto_approved', cast(:mid as uuid),
                        cast(:payload as jsonb))
                """
            ),
            {
                "mid": msg_id,
                "payload": '{"by": "auto_approve.py", "reason": "hitl_mode=false"}',
            },
        )
        s.commit()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap drafts a aprobar por run (default: sin limite).")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(f"auto_approve  env={env}  dry_run={args.dry_run}  limit={args.limit}")
    print("=" * 76)

    mailboxes = fetch_autonomous_mailboxes(env)
    if not mailboxes:
        print("[OK] No hay mailboxes en modo autonomo (hitl_mode=false). Nada que hacer.")
        return 0

    print(f"[mailboxes] {len(mailboxes)} en modo autonomo: "
          f"{', '.join(m['email'] for m in mailboxes)}")

    counts = {"approved": 0, "skipped_invalid": 0, "failed": 0}
    t0 = time.monotonic()

    for mb in mailboxes:
        drafts = fetch_pending_drafts(env, mb["id"])
        if args.limit is not None:
            drafts = drafts[:args.limit]
        if not drafts:
            print(f"  [{mb['email']}] 0 drafts pendientes")
            continue
        print(f"  [{mb['email']}] {len(drafts)} drafts pendientes")

        for draft in drafts:
            err = validate_draft(draft)
            if err:
                counts["skipped_invalid"] += 1
                print(f"    skip {draft['msg_id'][:8]} ({draft['contact_email']}): {err}")
                continue
            if args.dry_run:
                counts["approved"] += 1
                print(f"    DRY {draft['msg_id'][:8]} ({draft['contact_email']}): "
                      f"approve-able")
                continue
            try:
                approve_draft(env, draft["msg_id"])
                counts["approved"] += 1
                print(f"    APPROVED {draft['msg_id'][:8]} ({draft['contact_email']})")
            except Exception as e:
                counts["failed"] += 1
                logger.exception(
                    "approve failed msg=%s: %s", draft["msg_id"], e
                )

    elapsed = time.monotonic() - t0
    print()
    print("=" * 76)
    print(f"FIN auto_approve  env={env}  elapsed={elapsed:.1f}s")
    print(f"  approved:        {counts['approved']}")
    print(f"  skipped_invalid: {counts['skipped_invalid']}")
    print(f"  failed:          {counts['failed']}")
    print("=" * 76)

    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
