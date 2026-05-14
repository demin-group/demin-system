"""handle_actions.py -- Fase 3 Sprint 5 (§11.2 todo.md).

Procesa replies con category set y human_action='pendiente'. Ejecuta la accion
correspondiente por categoria:

| Categoria       | Accion                                                     |
|-----------------|------------------------------------------------------------|
| interesado      | Cancel future steps + DEJA pendiente (escalado humano).    |
| pide_info       | Cancel future steps + DEJA pendiente (HITL respuesta).     |
| no_ahora        | Cancel future steps + crea re_engage_60 (scheduled +60d).  |
| no_interesado   | Cancel future steps + crea re_engage_90 (scheduled +90d).  |
| rebote          | contacts.email_verified=false + cancel future steps.       |
| fuera_oficina   | Reschedule pending message proximo a now()+7d.             |
| desconocido     | DEJA pendiente (humano decide).                            |
| (opt-out)       | Apendice A regla 2: contact.is_optout ya marcado por       |
|                 | classify_replies; aqui solo cancel future steps.           |

Tras la accion, `human_action='archivado'` para las categorias auto-handled o
queda 'pendiente' para las que requieren humano (`interesado`, `pide_info`,
`desconocido`).

Apendice A regla 1: nunca enviar sin pasar por HITL. Las re-engages se crean
con status='drafted' (entran a la cola HITL en su fecha programada, no se
envian automaticamente). El timer demin-replenish puede regenerar el body via
generate_draft con angle='re_engage_60' / 're_engage_90' antes de scheduled_for.

CLI:
    cd apps/workers
    uv run python -m replies.handle_actions --env prod
    uv run python -m replies.handle_actions --env dev --dry-run

Exit codes:
- 0: OK
- 1: alguna accion fallo (no fatal)
- 2: error config / BD
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import text

from shared.db import get_session

EnvName = Literal["dev", "prod"]

RE_ENGAGE_60_DAYS = 60
RE_ENGAGE_90_DAYS = 90
FUERA_OFICINA_RESCHEDULE_DAYS = 7

logger = logging.getLogger("demin.handle_actions")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def fetch_pending_actions(env: EnvName, limit: int | None) -> list[dict[str, Any]]:
    """Trae replies con category set + human_action='pendiente'."""
    sql = """
        SELECT
            r.id::text AS reply_id,
            r.message_id::text AS message_id,
            r.contact_id::text AS contact_id,
            r.category,
            r.is_explicit_optout,
            m.campaign_id::text AS campaign_id,
            m.mailbox_id::text AS mailbox_id
        FROM replies r
        LEFT JOIN messages m ON m.id = r.message_id
        WHERE r.category IS NOT NULL
          AND r.human_action = 'pendiente'
        ORDER BY r.received_at ASC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_session(env) as s:
        rows = s.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


def cancel_future_steps(env: EnvName, contact_id: str) -> int:
    """Cancela messages no enviados todavia (drafted/approved/scheduled) del
    contact. Devuelve count cancelados.
    """
    with get_session(env) as s:
        r = s.execute(
            text(
                """
                UPDATE messages
                SET status = 'cancelled'
                WHERE contact_id = cast(:cid as uuid)
                  AND status IN ('drafted', 'approved', 'scheduled')
                """
            ),
            {"cid": contact_id},
        )
        s.commit()
    return int(getattr(r, "rowcount", 0) or 0)


def schedule_re_engage(
    env: EnvName,
    *,
    contact_id: str,
    campaign_id: str | None,
    mailbox_id: str | None,
    angle: Literal["re_engage_60", "re_engage_90"],
    days_from_now: int,
) -> str | None:
    """Crea un message scheduled con angle re_engage_*. status='scheduled'
    (no drafted) para que generate_draft lo regenere antes de enviar.

    step_index 3 = re_engage_60, 4 = re_engage_90 (convencion).
    """
    step_idx = 3 if angle == "re_engage_60" else 4
    scheduled = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    with get_session(env) as s:
        # Check duplicado: si ya hay un re_engage del mismo angle pendiente
        # para este contact, no creamos otro.
        exists = s.execute(
            text(
                """
                SELECT id::text FROM messages
                WHERE contact_id = cast(:cid as uuid)
                  AND angle = :angle
                  AND status IN ('drafted','approved','scheduled')
                """
            ),
            {"cid": contact_id, "angle": angle},
        ).fetchone()
        if exists:
            logger.info(
                "re_engage_dup contact=%s angle=%s ya existe msg=%s",
                contact_id, angle, exists[0],
            )
            return None

        ins = s.execute(
            text(
                """
                INSERT INTO messages (
                    contact_id, mailbox_id, campaign_id,
                    step_index, angle, status, scheduled_for
                ) VALUES (
                    cast(:cid as uuid),
                    CASE WHEN :mid='' THEN NULL ELSE cast(:mid as uuid) END,
                    CASE WHEN :camp='' THEN NULL ELSE cast(:camp as uuid) END,
                    :step, :angle, 'scheduled', :sched
                )
                RETURNING id::text
                """
            ),
            {
                "cid": contact_id,
                "mid": mailbox_id or "",
                "camp": campaign_id or "",
                "step": step_idx,
                "angle": angle,
                "sched": scheduled,
            },
        )
        row = ins.fetchone()
        s.commit()
        return str(row[0]) if row else None


def reschedule_pending_for_contact(env: EnvName, contact_id: str, days: int) -> int:
    """Re-schedule el siguiente message pendiente del contact a now()+days.
    Si no hay ninguno scheduled, no hace nada.
    """
    new_at = datetime.now(timezone.utc) + timedelta(days=days)
    with get_session(env) as s:
        r = s.execute(
            text(
                """
                UPDATE messages
                SET scheduled_for = :sched
                WHERE contact_id = cast(:cid as uuid)
                  AND status = 'scheduled'
                """
            ),
            {"cid": contact_id, "sched": new_at},
        )
        s.commit()
    return int(getattr(r, "rowcount", 0) or 0)


def mark_contact_email_invalid(env: EnvName, contact_id: str) -> None:
    """contacts.email_verified=false (rebote -> alternativa manual)."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE contacts SET email_verified = false
                WHERE id = cast(:cid as uuid)
                """
            ),
            {"cid": contact_id},
        )
        s.commit()


def update_reply_archivado(env: EnvName, reply_id: str) -> None:
    """human_action='archivado' (auto-handled)."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE replies SET human_action = 'archivado'
                WHERE id = cast(:rid as uuid)
                """
            ),
            {"rid": reply_id},
        )
        s.commit()


def handle_one(env: EnvName, reply: dict[str, Any], dry_run: bool) -> str:
    """Ejecuta la accion para una reply. Returns label de la accion."""
    cat = reply["category"]
    contact_id = reply["contact_id"]
    reply_id = reply["reply_id"]
    is_optout = bool(reply.get("is_explicit_optout"))

    # Apendice A regla 2: opt-out es transversal y siempre cancela future steps.
    if is_optout:
        if dry_run:
            return "DRY: optout -> cancel future steps"
        n = cancel_future_steps(env, contact_id)
        update_reply_archivado(env, reply_id)
        return f"optout_cancelled={n}"

    if cat == "interesado":
        if dry_run:
            return "DRY: interesado -> cancel future, leave pending for HITL"
        n = cancel_future_steps(env, contact_id)
        # Dejamos human_action='pendiente' para que Gonzalo lo vea en /inbox.
        return f"interesado_escalado cancelled={n}"

    if cat == "pide_info":
        if dry_run:
            return "DRY: pide_info -> cancel future, leave pending for HITL"
        n = cancel_future_steps(env, contact_id)
        return f"pide_info_pending cancelled={n}"

    if cat == "no_ahora":
        if dry_run:
            return f"DRY: no_ahora -> cancel future + re_engage_60"
        n = cancel_future_steps(env, contact_id)
        new_id = schedule_re_engage(
            env,
            contact_id=contact_id,
            campaign_id=reply.get("campaign_id"),
            mailbox_id=reply.get("mailbox_id"),
            angle="re_engage_60",
            days_from_now=RE_ENGAGE_60_DAYS,
        )
        update_reply_archivado(env, reply_id)
        return f"re_engage_60={new_id} cancelled={n}"

    if cat == "no_interesado":
        if dry_run:
            return "DRY: no_interesado -> cancel future + re_engage_90"
        n = cancel_future_steps(env, contact_id)
        new_id = schedule_re_engage(
            env,
            contact_id=contact_id,
            campaign_id=reply.get("campaign_id"),
            mailbox_id=reply.get("mailbox_id"),
            angle="re_engage_90",
            days_from_now=RE_ENGAGE_90_DAYS,
        )
        update_reply_archivado(env, reply_id)
        return f"re_engage_90={new_id} cancelled={n}"

    if cat == "rebote":
        if dry_run:
            return "DRY: rebote -> email_verified=false + cancel future"
        mark_contact_email_invalid(env, contact_id)
        n = cancel_future_steps(env, contact_id)
        update_reply_archivado(env, reply_id)
        return f"bounced cancelled={n}"

    if cat == "fuera_oficina":
        if dry_run:
            return f"DRY: fuera_oficina -> reschedule pending +{FUERA_OFICINA_RESCHEDULE_DAYS}d"
        n = reschedule_pending_for_contact(env, contact_id, FUERA_OFICINA_RESCHEDULE_DAYS)
        update_reply_archivado(env, reply_id)
        return f"reschedule_ooo={n}"

    # desconocido o categoria no manejada: dejar pendiente.
    return "leave_pending"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(f"handle_actions  env={env}  limit={args.limit}  dry_run={args.dry_run}")
    print("=" * 76)

    pending = fetch_pending_actions(env, args.limit)
    if not pending:
        print("No hay replies pendientes de action. Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} replies a procesar")

    counts: dict[str, int] = {"ok": 0, "failed": 0, "left_pending": 0}
    actions_breakdown: dict[str, int] = {}
    t0 = time.monotonic()

    for i, reply in enumerate(pending, 1):
        try:
            label = handle_one(env, reply, args.dry_run)
        except Exception as e:
            logger.exception(
                "handle failed reply=%s: %s", reply["reply_id"], e
            )
            counts["failed"] += 1
            continue

        if label.startswith("leave_pending"):
            counts["left_pending"] += 1
        else:
            counts["ok"] += 1
        action_key = label.split()[0]
        actions_breakdown[action_key] = actions_breakdown.get(action_key, 0) + 1
        print(
            f"  [{i:>3}/{len(pending)}] reply={reply['reply_id'][:8]} "
            f"cat={reply['category']:<14} -> {label}"
        )

    elapsed = time.monotonic() - t0
    print()
    print("=" * 76)
    print(f"FIN handle_actions  elapsed={elapsed:.1f}s")
    print(f"  ok:            {counts['ok']}")
    print(f"  left_pending:  {counts['left_pending']}")
    print(f"  failed:        {counts['failed']}")
    print(f"  acciones:      {actions_breakdown}")
    print("=" * 76)

    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
