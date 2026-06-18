"""Diag: por que generate_draft dice "No hay contacts pendientes" (T3, opening).

Replica el WHERE de fetch_pending_contacts() y muestra el embudo paso a paso
+ el detalle por contacto, para ver QUE filtro deja la cola a 0.

Filtros de generate_draft (angle=opening, step_index=0):
  company: ia_fit='fit', tier=T3, research_done_at not null, NOT research_data?'_failed'
  contact: is_optout=false, is_primary=true
  + sin message previo en step_index=0

Uso (en apps/workers, ENV se fija dentro):
    uv run python -m scripts.diag_draft_eligibility
"""
from __future__ import annotations

import os

os.environ["ENV"] = "prod"  # DEBE ir antes de importar shared.* (carga env-file)

from sqlalchemy import text  # noqa: E402

from shared.db import get_session  # noqa: E402

# Base "estricta" = exactamente lo que exige generate_draft sobre la empresa.
CO = (
    "from contacts ct join companies c on c.id = ct.company_id "
    "where c.tier='T3' and c.ia_fit='fit' and c.research_done_at is not null "
    "and not jsonb_exists(c.research_data, '_failed')"
)
# Base "laxa" para el detalle: T3 fit con research, sin filtrar por _failed/flags,
# para no esconder ningun contacto.
CO_LOOSE = (
    "from contacts ct join companies c on c.id = ct.company_id "
    "where c.tier='T3' and c.ia_fit='fit' and c.research_done_at is not null"
)


def main() -> None:
    with get_session("prod") as s:
        def n(sql: str) -> int:
            return int(s.execute(text(sql)).scalar() or 0)

        print("=== Embudo de elegibilidad generate_draft (T3, opening, step 0) ===")
        print("Companies T3 fit:",
              n("select count(*) from companies where tier='T3' and ia_fit='fit'"))
        print("  + research_done_at:",
              n("select count(*) from companies where tier='T3' and ia_fit='fit' "
                "and research_done_at is not null"))
        print("  + sin research_data._failed:",
              n("select count(*) from companies where tier='T3' and ia_fit='fit' "
                "and research_done_at is not null "
                "and not jsonb_exists(research_data, '_failed')"))
        print()
        print("Contactos (en empresas T3 fit + research_done):",
              n(f"select count(*) {CO_LOOSE}"))
        print("  + empresa sin _failed:", n(f"select count(*) {CO}"))
        print("  + ct.is_optout=false:", n(f"select count(*) {CO} and ct.is_optout=false"))
        print("  + ct.is_primary=true:",
              n(f"select count(*) {CO} and ct.is_optout=false and ct.is_primary=true"))
        print("  + sin opening previo  ==> ELEGIBLES:",
              n(f"select count(*) {CO} and ct.is_optout=false and ct.is_primary=true "
                "and not exists (select 1 from messages m "
                "where m.contact_id=ct.id and m.step_index=0)"))
        print()

        print("=== Detalle por contacto (T3 fit + research_done) ===")
        rows = s.execute(text(f"""
            select c.nif, ct.email, ct.email_priority as prio,
                   ct.is_primary, ct.is_optout,
                   jsonb_exists(c.research_data, '_failed') as research_failed,
                   exists(select 1 from messages m
                          where m.contact_id=ct.id and m.step_index=0) as has_opening
            {CO_LOOSE}
            order by c.nif, ct.email_priority, ct.email
        """)).mappings().all()
        if not rows:
            print("(0 contactos: el cuello esta ANTES, no hay contactos en esas empresas)")
        for r in rows:
            print(
                f"{(r['nif'] or '-'):<12} {(r['email'] or '-'):<38} "
                f"prio={r['prio']} primary={r['is_primary']} optout={r['is_optout']} "
                f"r_failed={r['research_failed']} opening={r['has_opening']}"
            )


if __name__ == "__main__":
    main()
