"""Desatasca el research de empresas fit con contacto virgen y web.

Pone research_done_at=NULL en empresas fit cuyo research quedó '_failed'
(scraping_failed/empty_text/insufficient_research/...), que tienen web y
algún contacto primary sin opt-out y sin ningún mensaje (virgen). Así
`research_prospect` (modo default: research_done_at IS NULL) las reintenta
y, si esta vez sale research, `generate_draft` podrá dibujarlas.

NO toca empresas ya contactadas, ni sin web, ni sin contactos vírgenes.
Idempotente: si el reintento vuelve a fallar, quedan igual que estaban.

Uso (en apps/workers):
    ENV=prod uv run python -m scripts.desatasca_research [--dry-run]
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")

WHERE = """
    c.ia_fit = 'fit'
    and c.research_data ? '_failed'
    and c.web is not null and length(trim(c.web)) > 0
    and exists (select 1 from contacts ct
                where ct.company_id = c.id
                  and ct.is_primary and not ct.is_optout
                  and not exists (select 1 from messages m
                                  where m.contact_id = ct.id))
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with get_session(env) as s:  # type: ignore[arg-type]
        rows = s.execute(text(
            f"""select c.tier, c.nombre, c.web,
                       coalesce(c.research_data->>'_failed','?') motivo
                from companies c where {WHERE}
                order by c.tier, c.nombre"""
        )).mappings().all()
        print(f"desatasca_research  env={env}  dry_run={args.dry_run}")
        print(f"empresas a reintentar: {len(rows)}\n")
        for r in rows:
            print(f"  [{r['tier']}] {(r['nombre'] or '')[:36]:<36} {r['motivo']:<22} {r['web'][:40]}")

        if args.dry_run or not rows:
            return

        res = s.execute(text(
            f"update companies c set research_done_at = null where {WHERE}"
        ))
        s.commit()
        print(f"\n→ research reseteado en {res.rowcount} empresas "
              "(las recogerá `pipeline.research_prospect` en modo default)")


if __name__ == "__main__":
    main()
