"""follow_ups.py -- Sprint 4 paso 7. Programa step+1 cuando step previo
fue enviado hace suficientes dias y no hay reply.

Lee la sequence 'demin_v1' (D+0/D+4/D+10) seedada en migration 11. Para
cada step_index 1 (reframe, D+4) y 2 (closing, D+10):

1. Busca messages con step_index = N-1 + status='sent' + sent_at <= now()
   - days_required (4 dias para step 1, 6 dias para step 2 desde el step 1).
2. Filtra contacts que NO tienen reply (sequence detiene en cualquier reply).
3. Filtra contacts que NO tienen ya message para (contact, step_index=N)
   (idempotencia tras re-correr).
4. Para cada candidato, llama `process_one_contact(angle=siguiente)` y
   persiste con `insert_draft`. El draft queda con `status='drafted'` para
   HITL approval en `/approval-queue`.

NO envia nada -- solo programa drafts. send_gmail.py los recoge una vez
aprobados.

Cap defensivo `--max-cost-usd 5.0` (Sonnet 4.6 ~$0.005/draft, 20 follow-ups
~ $0.10).

CLI:
    cd apps/workers
    uv run python -m outreach.follow_ups --env dev --dry-run
    uv run python -m outreach.follow_ups --env dev --max-cost-usd 1.0
    uv run python -m outreach.follow_ups --env prod
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text

from pipeline.generate_draft import (
    PendingContact,
    _load_prompt_for_angle,
    insert_draft,
    process_one_contact,
)
from shared.config import settings
from shared.db import get_session

EnvName = Literal["dev", "prod"]
Angle = Literal["opening", "reframe", "closing"]

SEQUENCE_NAME = "demin_v1"
USD_COST_CAP = 5.0
VOYAGE_RATE_LIMIT_SLEEP_S = 22.0

logger = logging.getLogger("demin.follow_ups")
if not logger.handlers:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass(slots=True)
class FollowUpStep:
    next_step_index: int
    next_angle: Angle
    days_since_prev_sent: int
    """Dias minimos entre `messages.sent_at` del paso previo y now() para
    que este follow-up se programe."""


def load_sequence_steps(env: EnvName) -> list[FollowUpStep]:
    """Lee sequences.steps[].day y construye los FollowUpSteps para 1+.
    Step 0 (opening) no se programa via follow_ups -- generate_draft.py lo
    hace en la fase de arranque."""
    with get_session(env) as s:
        row = s.execute(
            text("SELECT steps FROM sequences WHERE nombre = :n"),
            {"n": SEQUENCE_NAME},
        ).mappings().first()
    if not row:
        raise RuntimeError(
            f"sequence {SEQUENCE_NAME!r} no encontrada. Aplica migration 11."
        )
    steps_raw = row["steps"]
    if not isinstance(steps_raw, list) or len(steps_raw) < 2:
        raise RuntimeError(
            f"sequence {SEQUENCE_NAME!r} con steps malformada: {steps_raw!r}"
        )
    out: list[FollowUpStep] = []
    for i in range(1, len(steps_raw)):
        prev_day = int(steps_raw[i - 1]["day"])
        cur_day = int(steps_raw[i]["day"])
        angle = steps_raw[i]["angle"]
        if angle not in ("opening", "reframe", "closing"):
            raise RuntimeError(f"angle desconocido en sequence: {angle!r}")
        out.append(FollowUpStep(
            next_step_index=i,
            next_angle=angle,
            days_since_prev_sent=cur_day - prev_day,
        ))
    return out


def fetch_followup_candidates(
    env: EnvName, step: FollowUpStep
) -> list[PendingContact]:
    """Trae contacts cuyo step previo se envio hace >= days_since_prev_sent
    y NO tienen ya message para el next_step_index y NO tienen reply.

    Filtros equivalentes a `fetch_pending_contacts` de generate_draft, pero
    pivota desde el message del paso previo:
    - prev message status='sent', sent_at antiguo suficiente
    - contact.is_optout=false, contact.is_primary=true
    - company.research_done_at NOT NULL, NOT _failed
    - NO existe reply para el contact (sequence detiene)
    - NO existe message para (contact, next_step_index) -- idempotencia
    """
    prev_step_index = step.next_step_index - 1
    sql = """
        SELECT
            ct.id   AS contact_id,
            ct.email,
            ct.email_type,
            ct.email_priority,
            ct.nombre AS contact_nombre,
            ct.cargo  AS contact_cargo,
            c.id    AS company_id,
            c.nif,
            c.nombre AS company_nombre,
            c.tier,
            c.research_data
        FROM messages m_prev
        JOIN contacts ct ON ct.id = m_prev.contact_id
        JOIN companies c ON c.id = ct.company_id
        WHERE m_prev.step_index = :prev_step
          AND m_prev.status = 'sent'
          AND m_prev.sent_at <= now() - cast(:days_text AS interval)
          AND ct.is_optout = false
          AND ct.is_primary = true
          AND c.research_done_at IS NOT NULL
          AND NOT (c.research_data ? '_failed')
          AND NOT EXISTS (
              SELECT 1 FROM messages m_next
              WHERE m_next.contact_id = ct.id
                AND m_next.step_index = :next_step
          )
          AND NOT EXISTS (
              SELECT 1 FROM replies r
              WHERE r.contact_id = ct.id
          )
        ORDER BY c.nif, ct.email_priority
    """
    days_text = f"{step.days_since_prev_sent} days"
    with get_session(env) as s:
        rows = s.execute(
            text(sql),
            {
                "prev_step": prev_step_index,
                "next_step": step.next_step_index,
                "days_text": days_text,
            },
        ).mappings().all()
    return [
        PendingContact(
            contact_id=str(r["contact_id"]),
            company_id=str(r["company_id"]),
            email=r["email"],
            email_type=r["email_type"],
            email_priority=int(r["email_priority"]),
            nombre_contacto=r["contact_nombre"],
            cargo_contacto=r["contact_cargo"],
            nif=r["nif"],
            nombre_empresa=r["company_nombre"],
            tier=r["tier"],
            research_data=r["research_data"] or {},
        )
        for r in rows
    ]


def estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    """Sonnet 4.6 aprox: input $3/MTok, output $15/MTok."""
    return (tokens_in * 3.0 + tokens_out * 15.0) / 1_000_000.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--max-cost-usd", type=float, default=USD_COST_CAP)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--no-voyage-sleep",
        action="store_true",
        help="Salta los 22s entre embeds. Solo para tests sin red.",
    )
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(
        f"follow_ups  env={env}  max_cost_usd={args.max_cost_usd}  "
        f"dry_run={args.dry_run}"
    )
    print("=" * 76)

    steps = load_sequence_steps(env)
    print(f"[sequence] {SEQUENCE_NAME} steps follow-up = {len(steps)}:")
    for st in steps:
        print(
            f"  step={st.next_step_index} angle={st.next_angle} "
            f"days_since_prev_sent>={st.days_since_prev_sent}"
        )

    total_scheduled = 0
    total_cost_usd = 0.0
    total_errors = 0

    for step in steps:
        candidates = fetch_followup_candidates(env, step)
        print()
        print(
            f"[step={step.next_step_index} angle={step.next_angle}] "
            f"{len(candidates)} candidatos"
        )
        if not candidates:
            continue

        system, user_template = _load_prompt_for_angle(step.next_angle)
        for i, item in enumerate(candidates, 1):
            if total_cost_usd >= args.max_cost_usd:
                print(
                    f"[cap] coste {total_cost_usd:.4f} >= max {args.max_cost_usd}, "
                    f"parando"
                )
                break

            if args.dry_run:
                print(
                    f"  [dry-run] would schedule msg step={step.next_step_index} "
                    f"nif={item.nif} contact={item.email}"
                )
                total_scheduled += 1
                continue

            result = process_one_contact(env, item, step.next_angle, system, user_template)
            if not result.success or result.draft is None:
                total_errors += 1
                print(
                    f"  [ERR] nif={item.nif} contact={item.email} "
                    f"err={result.error}"
                )
            else:
                cost_usd = estimate_cost_usd(
                    result.draft.tokens_in, result.draft.tokens_out
                )
                msg_id = insert_draft(
                    env=env,
                    item=item,
                    draft=result.draft,
                    angle=step.next_angle,
                )
                total_scheduled += 1
                total_cost_usd += cost_usd
                marker = " (con _failed_validations)" if result.draft.failed_validations else ""
                print(
                    f"  [{i}/{len(candidates)}] OK msg={msg_id[:8]} nif={item.nif} "
                    f"contact={item.email}{marker} tok={result.draft.tokens_in}+"
                    f"{result.draft.tokens_out}"
                )

            if not args.no_voyage_sleep and i < len(candidates):
                time.sleep(VOYAGE_RATE_LIMIT_SLEEP_S)

    print()
    print("=" * 76)
    print(
        f"FIN follow_ups  env={env}  scheduled={total_scheduled}  "
        f"errors={total_errors}  cost=${total_cost_usd:.4f}"
    )
    print("=" * 76)
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
