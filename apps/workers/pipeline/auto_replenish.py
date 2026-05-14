"""auto_replenish.py — Sprint 4 paso 8.

Worker periodico que mantiene la cola HITL prod con >=TARGET drafts pendientes.

Logica:
1. Cuenta drafts status='drafted' en BD del env solicitado.
2. Si >=target: exit 0 (no-op).
3. Si <target: ejecuta secuencia research_prospect -> find_contacts ->
   generate_draft sobre N empresas T3 fit con web (research_done_at NULL)
   hasta llegar a target o agotar caps por run.

Diseno:
- Pensado para correr como systemd timer cada 4h en el VPS (6 runs/dia).
- Cap diario aproximado se controla via cap por run = diario / 6:
    LLM diario $3 -> $0.50 por run
    Hunter diario 60 -> 10 por run
- NO persiste estado entre runs. Cada run es self-contained.
- Si la cola se vacia rapido (Gonzalo aprueba > genera_draft produce), el
  proximo timer rellenara. Si la cola se mantiene, los runs son no-op.

CLI:
    cd apps/workers
    uv run python -m pipeline.auto_replenish --env prod
    uv run python -m pipeline.auto_replenish --env dev --target 5
    uv run python -m pipeline.auto_replenish --env prod \\
        --target 15 --batch-size 10 \\
        --max-cost-usd 0.50 --max-hunter-calls 10 \\
        --tier T3

Exit codes:
- 0: OK (cola rellenada o ya estaba llena)
- 2: error config (env, db, prompts faltantes)
- 3: cap absorbido y cola sigue por debajo de target (no fatal, log WARNING)
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Literal

from sqlalchemy import text

from pipeline import find_contacts, generate_draft, research_prospect
from shared.db import get_engine

EnvName = Literal["dev", "prod"]
Tier = Literal["T1", "T2", "T3", "T4"]

DEFAULT_TARGET = 15
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_COST_USD = 0.50
DEFAULT_MAX_HUNTER_CALLS = 10
DEFAULT_TIER: Tier = "T3"

logger = logging.getLogger("demin.auto_replenish")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def count_drafts_in_queue(env: EnvName) -> int:
    """Cuenta messages con status='drafted'. Approved no cuenta como pending
    (ya pasaron HITL, esperan ventana de envio).
    """
    engine = get_engine(env)
    with engine.connect() as conn:
        row = conn.execute(
            text("select count(*) from messages where status='drafted'")
        ).fetchone()
        return int(row[0]) if row else 0


def count_research_pending(env: EnvName, tier: Tier) -> int:
    """Empresas tier fit con web aun sin research_done_at."""
    engine = get_engine(env)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select count(*) from companies
                where tier=:tier and ia_fit='fit'
                      and web is not null and web <> ''
                      and research_done_at is null
                """
            ),
            {"tier": tier},
        ).fetchone()
        return int(row[0]) if row else 0


def count_contacts_without_draft(env: EnvName, tier: Tier) -> int:
    """Contacts is_primary del tier sin message asociado (huerfanos).

    Estos pueden generar drafts directamente sin pasar por research/find_contacts.
    """
    engine = get_engine(env)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select count(*) from contacts c
                join companies co on co.id = c.company_id
                where c.is_primary = true
                      and co.tier = :tier
                      and co.ia_fit = 'fit'
                      and not exists (
                        select 1 from messages m where m.contact_id = c.id
                      )
                """
            ),
            {"tier": tier},
        ).fetchone()
        return int(row[0]) if row else 0


def run_replenish(
    env: EnvName,
    target: int,
    batch_size: int,
    max_cost_usd: float,
    max_hunter_calls: int,
    tier: Tier,
) -> int:
    """Ejecuta el flujo replenish completo. Retorna exit code."""
    drafts_now = count_drafts_in_queue(env)
    gap = target - drafts_now
    logger.info(
        "replenish_start env=%s tier=%s drafts_now=%d target=%d gap=%d",
        env, tier, drafts_now, target, gap,
    )

    if gap <= 0:
        logger.info("cola_ya_completa drafts=%d >= target=%d, exit 0", drafts_now, target)
        return 0

    # Paso 1: drafts sobre contacts huerfanos (sin coste Hunter ni research).
    # Esto vacia primero el stock disponible antes de tirar pipeline desde 0.
    huerfanos = count_contacts_without_draft(env, tier)
    if huerfanos > 0:
        logger.info("generate_draft huerfanos=%d (sin pasar research/find_contacts)", huerfanos)
        rc = generate_draft.main([
            "--env", env,
            "--tier", tier,
            "--angle", "opening",
            "--limit", str(min(huerfanos, gap)),
            "--max-cost-usd", f"{max_cost_usd:.2f}",
        ])
        if rc not in (0, 1):  # rc=1 cuando hay alguna fallida pero no fatal
            logger.error("generate_draft fallo rc=%d (cap absorbido o error)", rc)
            return 3

        drafts_after = count_drafts_in_queue(env)
        gap = target - drafts_after
        logger.info("post_huerfanos drafts_now=%d gap=%d", drafts_after, gap)
        if gap <= 0:
            return 0

    # Paso 2: si gap sigue >0, tira pipeline completo sobre empresas no procesadas.
    research_pending = count_research_pending(env, tier)
    if research_pending == 0:
        logger.warning(
            "no_research_pending_y_gap_persiste tier=%s gap=%d "
            "(o todas las empresas ya tienen research, o las pendientes no tienen web). "
            "Considera tier=%s o esperar a anadir mas empresas.",
            tier, gap, tier,
        )
        return 3

    # Tirar batch_size de empresas. Aprox: si hit rate find_contacts = 20%,
    # 10 empresas dan 2 drafts. Para gap=15 necesitarias ~75 empresas, pero
    # eso excede max_hunter_calls=10 y max_cost_usd=0.50. El timer 4h
    # reintenta hasta que se rellena.
    limit = min(batch_size, research_pending)
    logger.info("pipeline_start limit=%d research_pending=%d", limit, research_pending)

    # research_prospect: $0.01/empresa aprox, no usa Hunter.
    rc_research = research_prospect.main([
        "--env", env,
        "--tier", tier,
        "--limit", str(limit),
        "--max-cost-usd", f"{max_cost_usd:.2f}",
    ])
    if rc_research == 2:
        logger.warning("research_cap_absorbido rc=2, sigo a find_contacts")
    elif rc_research not in (0, 1):
        logger.error("research_prospect fallo rc=%d", rc_research)
        return 3

    # find_contacts: 1 Hunter call por empresa minimo, +1 por email_finder si encontro.
    rc_find = find_contacts.main([
        "--env", env,
        "--tier", tier,
        "--limit", str(limit),
        "--max-hunter-calls", str(max_hunter_calls),
    ])
    if rc_find not in (0, 1):
        logger.error("find_contacts fallo rc=%d", rc_find)
        return 3

    # generate_draft: rellena hasta gap o agotar contacts huerfanos nuevos.
    drafts_pre_gen = count_drafts_in_queue(env)
    gap_pre_gen = target - drafts_pre_gen
    if gap_pre_gen <= 0:
        logger.info("post_find_contacts cola_llena drafts=%d", drafts_pre_gen)
        return 0

    rc_gen = generate_draft.main([
        "--env", env,
        "--tier", tier,
        "--angle", "opening",
        "--limit", str(gap_pre_gen),
        "--max-cost-usd", f"{max_cost_usd:.2f}",
    ])
    if rc_gen not in (0, 1):
        logger.warning("generate_draft cap absorbido o error rc=%d", rc_gen)

    drafts_final = count_drafts_in_queue(env)
    gap_final = target - drafts_final
    if gap_final > 0:
        logger.warning(
            "fin_run_cola_incompleta drafts=%d target=%d gap=%d "
            "(esperando proximo timer)",
            drafts_final, target, gap_final,
        )
        return 3
    logger.info("fin_run_cola_completa drafts=%d", drafts_final)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="auto_replenish — mantiene cola HITL con >=target drafts pendientes (Sprint 4 paso 8)"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--target", type=int, default=DEFAULT_TARGET,
                   help=f"Target drafts en cola (default {DEFAULT_TARGET}).")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                   help=f"Empresas a procesar por run en pipeline completo (default {DEFAULT_BATCH_SIZE}).")
    p.add_argument("--max-cost-usd", type=float, default=DEFAULT_MAX_COST_USD,
                   help=f"Cap LLM por run (default {DEFAULT_MAX_COST_USD}, ~1/6 del cap diario).")
    p.add_argument("--max-hunter-calls", type=int, default=DEFAULT_MAX_HUNTER_CALLS,
                   help=f"Cap Hunter por run (default {DEFAULT_MAX_HUNTER_CALLS}, ~1/6 del cap diario 60).")
    p.add_argument("--tier", choices=("T1", "T2", "T3", "T4"), default=DEFAULT_TIER,
                   help=f"Tier a procesar (default {DEFAULT_TIER}). Roll-out D22.")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(
        f"auto_replenish  env={env}  target={args.target}  "
        f"batch_size={args.batch_size}  max_cost_usd={args.max_cost_usd}  "
        f"max_hunter_calls={args.max_hunter_calls}  tier={args.tier}"
    )
    print("=" * 76)

    return run_replenish(
        env=env,
        target=args.target,
        batch_size=args.batch_size,
        max_cost_usd=args.max_cost_usd,
        max_hunter_calls=args.max_hunter_calls,
        tier=args.tier,
    )


if __name__ == "__main__":
    sys.exit(main())
