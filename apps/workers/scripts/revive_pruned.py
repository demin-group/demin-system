"""Revive a la Approval Queue los drafts cancelados por 'no_verificado_prune'.

Contexto: el 18-jun `prune_to_verified` canceló todo draft cuyo email no pudo
verificar Hunter (risky/catch-all/unknown). Decisión de Fer (03-jul-2026):
meterlos en la cola igualmente — el HITL decide uno a uno y la auto-pausa
protege el dominio si alguno rebota.

Revive SOLO drafts step-0 'cancelled' con motivo 'no_verificado_prune' cuyo
contacto siga primary + sin opt-out + empresa fit, sin otro mensaje step-0
vivo (si hubiera varios cancelados por contacto, revive el más reciente).
Idempotente. NO envía nada: entran como status='drafted' (HITL).

Uso (en apps/workers):
    ENV=prod uv run python -m scripts.revive_pruned [--dry-run]
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")

SELECT_CANDIDATAS = """
    select distinct on (m.contact_id)
           m.id::text mid, co.tier, ct.email, co.nombre, m.subject
    from messages m
    join contacts ct on ct.id = m.contact_id
    join companies co on co.id = ct.company_id
    where m.status = 'cancelled' and m.step_index = 0
      and m.research_snapshot->>'_cancelled_reason' = 'no_verificado_prune'
      and ct.is_primary and not ct.is_optout and co.ia_fit = 'fit'
      and not exists (select 1 from messages m2
                      where m2.contact_id = m.contact_id
                        and m2.step_index = 0 and m2.status <> 'cancelled')
    order by m.contact_id, m.created_at desc
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with get_session(env) as s:  # type: ignore[arg-type]
        cand = s.execute(text(SELECT_CANDIDATAS)).mappings().all()
        print(f"revive_pruned  env={env}  dry_run={args.dry_run}")
        print(f"candidatos a revivir: {len(cand)}\n")
        for r in sorted(cand, key=lambda r: (r["tier"], r["email"])):
            print(f"  [{r['tier']}] {r['email']:<46} {(r['nombre'] or '')[:32]}")

        if args.dry_run or not cand:
            return

        res = s.execute(
            text(
                """
                update messages
                set status = 'drafted',
                    research_snapshot = (coalesce(research_snapshot,'{}'::jsonb)
                        - '_cancelled_reason')
                        || jsonb_build_object('_revived_from', 'no_verificado_prune')
                where id = any(cast(:ids as uuid[]))
                """
            ),
            {"ids": [r["mid"] for r in cand]},
        )
        s.commit()
        print(f"\n→ revividos a 'drafted': {res.rowcount}")
        rem = s.execute(text("select count(*) from messages where status='drafted'")).scalar()
        print(f"→ drafts totales en la Approval Queue: {rem}")


if __name__ == "__main__":
    main()
