"""handle_actions.py -- Fase 3 Sprint 5 (§11.2 todo.md), actualizado L45+L46.

Procesa replies con category set y human_action='pendiente'. Ejecuta la accion
correspondiente por categoria segun matriz Leccion 45 (cero respuesta
automatica dentro de hilo abierto) y Leccion 46 (re_engage no_ahora pasa de
+60d a +40d):

| Categoria       | Bot dentro hilo  | Programa correo nuevo futuro          |
|-----------------|------------------|---------------------------------------|
| interesado      | NO               | NO (event interesado_flag + pendiente)|
| pide_info       | NO               | NO (event pide_info_flag + pendiente) |
| no_ahora        | NO               | re_engage_40 a +40d (L46)             |
| no_interesado   | NO               | re_engage_90 a +90d                   |
| rebote          | NO               | NO (email_verified=false + cancel)    |
| fuera_oficina   | NO               | Reschedule +5d desde retorno OOO si   |
|                 |                  | detectado, sino +7d                   |
| opt-out         | NO (ni acuse)    | NO (cancel + event optout_explicit)   |
| desconocido     | NO               | NO (deja pendiente)                   |

Cambios L45 vs version anterior:
- interesado/pide_info: NO genera draft de respuesta sugerida. Solo flag
  evento + deja human_action='pendiente' para visibilidad /inbox. Gonzalo
  responde manualmente en Gmail.
- opt-out: NO envia acuse automatico. Solo registra event optout_explicit.
- fuera_oficina: intenta parsear fecha de retorno del body con regex
  espanol; si encuentra, reschedule a fecha+5d; si no, default +7d.

Cambios L46:
- no_ahora: re_engage_60 -> re_engage_40 (constante + angle string).
- step_idx 3 sigue mapeando a re_engage_40 (sustituye re_engage_60).

Apendice A regla 1: nunca enviar sin pasar por HITL. Las re-engages se crean
con status='scheduled' (entran a la cola HITL en su fecha programada, no se
envian automaticamente). generate_draft puede regenerar el body via
angle='re_engage_40' / 're_engage_90' antes de scheduled_for.

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
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import text

from shared.db import get_session

EnvName = Literal["dev", "prod"]

# L46: re_engage no_ahora baja de +60d a +40d. no_interesado se mantiene +90d.
RE_ENGAGE_40_DAYS = 40
RE_ENGAGE_90_DAYS = 90
# fuera_oficina: si parse_ooo_return_date detecta fecha de retorno usa
# fecha+OOO_DAYS_AFTER_RETURN; sino default OOO_DEFAULT_DAYS.
OOO_DAYS_AFTER_RETURN = 5
OOO_DEFAULT_DAYS = 7

logger = logging.getLogger("demin.handle_actions")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def fetch_pending_actions(env: EnvName, limit: int | None) -> list[dict[str, Any]]:
    """Trae replies con category set + human_action='pendiente'.
    raw_body se incluye para parse OOO (fecha de retorno).
    """
    sql = """
        SELECT
            r.id::text AS reply_id,
            r.message_id::text AS message_id,
            r.contact_id::text AS contact_id,
            r.category,
            r.is_explicit_optout,
            r.raw_body,
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


_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def parse_ooo_return_date(body: str | None, today: date | None = None) -> date | None:
    """Heuristica simple para detectar fecha de retorno en OOO espanol/ingles.

    Reconoce patrones tipicos:
      - "vuelvo el 15/06/2026", "regreso 15-06-2026", "back on 06/15"
      - "estare de vuelta el 15 de junio", "vuelvo el 5 de junio de 2026"
      - "hasta el 30 de mayo"
      - "del 1 al 15 de junio" -> usa el dia final (15)

    Devuelve date en futuro inmediato (max ~3 meses); None si no encuentra.
    today (testing): inyectable para tests deterministas.
    """
    if not body:
        return None
    text_lc = body.lower()
    today = today or datetime.now(timezone.utc).date()
    candidates: list[date] = []

    # Patron 1: dd/mm/yyyy o dd-mm-yyyy o dd.mm.yyyy
    for m in re.finditer(
        r"\b(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?\b", text_lc
    ):
        d, mo, y = m.group(1), m.group(2), m.group(3)
        try:
            day_int = int(d)
            mon_int = int(mo)
            if mon_int < 1 or mon_int > 12 or day_int < 1 or day_int > 31:
                continue
            if y:
                year_int = int(y)
                if year_int < 100:
                    year_int += 2000
            else:
                year_int = today.year
                # Si la fecha ya paso este ano, asumir proximo ano.
                if (mon_int, day_int) < (today.month, today.day):
                    year_int += 1
            candidates.append(date(year_int, mon_int, day_int))
        except ValueError:
            continue

    # Patron 2: "DD de MES [de YYYY]"
    pat_es = re.compile(
        r"\b(\d{1,2})\s+de\s+("
        + "|".join(_SPANISH_MONTHS.keys())
        + r")(?:\s+de\s+(\d{2,4}))?\b"
    )
    for m in pat_es.finditer(text_lc):
        try:
            day_int = int(m.group(1))
            mon_int = _SPANISH_MONTHS[m.group(2)]
            if m.group(3):
                year_int = int(m.group(3))
                if year_int < 100:
                    year_int += 2000
            else:
                year_int = today.year
                if (mon_int, day_int) < (today.month, today.day):
                    year_int += 1
            candidates.append(date(year_int, mon_int, day_int))
        except (ValueError, KeyError):
            continue

    # Filtrar: solo fechas en futuro proximo (max 120 dias). 120 cubre
    # OOO largos tipicos (verano, baja maternidad/paternidad) sin pisarse
    # con re_engage_90d. Dates >120d probablemente no son OOO real (firma
    # de un contrato con fecha lejana, fecha de proyecto futuro, etc.).
    horizon = today + timedelta(days=120)
    future = [d for d in candidates if today < d <= horizon]
    if not future:
        return None
    # Elegir la mas lejana (cierra rangos del estilo "del 1 al 15 de junio"
    # con la fecha final, que es cuando vuelve).
    return max(future)


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
    angle: Literal["re_engage_40", "re_engage_90"],
    days_from_now: int,
) -> str | None:
    """Crea un message scheduled con angle re_engage_*. status='scheduled'
    (no drafted) para que generate_draft lo regenere antes de enviar.

    L46: re_engage_40 (era re_engage_60, +60d -> +40d).
    step_index 3 = re_engage_40, 4 = re_engage_90 (convencion).
    """
    step_idx = 3 if angle == "re_engage_40" else 4
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


def mark_message_bounced(env: EnvName, message_id: str | None) -> None:
    """messages.status='bounced' para el envio que reboto (solo si sigue
    'sent' — no pisa cancelled/aprobaciones). No-op si message_id es None."""
    if not message_id:
        return
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE messages SET status = 'bounced'
                WHERE id = cast(:mid as uuid) AND status = 'sent'
                """
            ),
            {"mid": message_id},
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


def insert_event(
    env: EnvName,
    *,
    event_type: str,
    message_id: str | None,
    contact_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """INSERT en events. L45: usado para flag de interesado/pide_info/optout
    explicit. /metrics y /inbox pueden agregar por estos events.
    """
    with get_session(env) as s:
        s.execute(
            text(
                """
                INSERT INTO events (type, message_id, contact_id, payload)
                VALUES (
                    :etype,
                    CASE WHEN :mid='' THEN NULL ELSE cast(:mid as uuid) END,
                    cast(:cid as uuid),
                    cast(:payload as jsonb)
                )
                """
            ),
            {
                "etype": event_type,
                "mid": message_id or "",
                "cid": contact_id,
                "payload": json.dumps(payload or {}),
            },
        )
        s.commit()


def handle_one(env: EnvName, reply: dict[str, Any], dry_run: bool) -> str:
    """Ejecuta la accion para una reply. Returns label de la accion.

    Matriz Leccion 45: cero respuesta dentro del hilo (incluido opt-out
    acuse). Leccion 46: re_engage no_ahora a +40d (era +60).
    """
    cat = reply["category"]
    contact_id = reply["contact_id"]
    reply_id = reply["reply_id"]
    message_id = reply.get("message_id")
    is_optout = bool(reply.get("is_explicit_optout"))

    # Apendice A regla 2: opt-out es transversal -> cancel future steps,
    # NO acuse automatico (L45). Registra evento para auditoria.
    if is_optout:
        if dry_run:
            return "DRY: optout -> cancel future + event optout_explicit"
        n = cancel_future_steps(env, contact_id)
        insert_event(
            env,
            event_type="optout_explicit",
            message_id=message_id,
            contact_id=contact_id,
            payload={"category_detected": cat, "reply_id": reply_id},
        )
        update_reply_archivado(env, reply_id)
        return f"optout_cancelled={n}"

    if cat == "interesado":
        if dry_run:
            return "DRY: interesado -> cancel + event flag + leave pending HITL"
        n = cancel_future_steps(env, contact_id)
        # L45: NO genera draft de respuesta. Solo flag para /inbox.
        insert_event(
            env,
            event_type="interesado_flag",
            message_id=message_id,
            contact_id=contact_id,
            payload={"reply_id": reply_id},
        )
        # human_action queda 'pendiente' para visibilidad en /inbox.
        return f"interesado_escalado cancelled={n}"

    if cat == "pide_info":
        if dry_run:
            return "DRY: pide_info -> cancel + event flag + leave pending HITL"
        n = cancel_future_steps(env, contact_id)
        insert_event(
            env,
            event_type="pide_info_flag",
            message_id=message_id,
            contact_id=contact_id,
            payload={"reply_id": reply_id},
        )
        return f"pide_info_pending cancelled={n}"

    if cat == "no_ahora":
        if dry_run:
            return "DRY: no_ahora -> cancel future + re_engage_40 (L46)"
        n = cancel_future_steps(env, contact_id)
        new_id = schedule_re_engage(
            env,
            contact_id=contact_id,
            campaign_id=reply.get("campaign_id"),
            mailbox_id=reply.get("mailbox_id"),
            angle="re_engage_40",
            days_from_now=RE_ENGAGE_40_DAYS,
        )
        update_reply_archivado(env, reply_id)
        return f"re_engage_40={new_id} cancelled={n}"

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
            return "DRY: rebote -> bounced + event bounce + email_verified=false + cancel future"
        # Fix 2026-06-04: el message que reboto pasa a status='bounced' y se
        # registra evento 'bounce' (auto_pause cuenta events type='bounce'
        # joineados por message_id — antes los DSN eran invisibles y el
        # bounce rate se infracontaba, Apendice A regla 6).
        mark_message_bounced(env, message_id)
        insert_event(
            env,
            event_type="bounce",
            message_id=message_id,
            contact_id=contact_id,
            payload={"reply_id": reply_id, "source": "handle_actions_rebote"},
        )
        mark_contact_email_invalid(env, contact_id)
        n = cancel_future_steps(env, contact_id)
        update_reply_archivado(env, reply_id)
        return f"bounced cancelled={n}"

    if cat == "fuera_oficina":
        # L45: parsea fecha de retorno del body; si encuentra, +5d desde
        # esa fecha; si no, default +7d desde hoy.
        ret_date = parse_ooo_return_date(reply.get("raw_body"))
        if ret_date:
            today_d = datetime.now(timezone.utc).date()
            days = (ret_date - today_d).days + OOO_DAYS_AFTER_RETURN
            mode = f"parsed_return={ret_date} (+{OOO_DAYS_AFTER_RETURN}d)"
        else:
            days = OOO_DEFAULT_DAYS
            mode = f"default (+{OOO_DEFAULT_DAYS}d)"
        if dry_run:
            return f"DRY: fuera_oficina -> reschedule +{days}d {mode}"
        n = reschedule_pending_for_contact(env, contact_id, days)
        update_reply_archivado(env, reply_id)
        return f"reschedule_ooo={n} days={days} {mode}"

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
