"""Pre/post smoke audit del worker research_prospect."""
from __future__ import annotations

import json

from sqlalchemy import text

from shared.db import get_session


def main() -> None:
    with get_session("dev") as s:
        for tier in ("T2", "T3"):
            total = s.execute(
                text(
                    "select count(*) from companies where tier=:t and ia_fit=:f "
                    "and web is not null and length(trim(web)) > 0"
                ),
                {"t": tier, "f": "fit"},
            ).scalar()
            sin_research = s.execute(
                text(
                    "select count(*) from companies where tier=:t and ia_fit=:f "
                    "and web is not null and length(trim(web)) > 0 "
                    "and research_done_at is null"
                ),
                {"t": tier, "f": "fit"},
            ).scalar()
            con_research = s.execute(
                text(
                    "select count(*) from companies where tier=:t and ia_fit=:f "
                    "and research_done_at is not null"
                ),
                {"t": tier, "f": "fit"},
            ).scalar()
            con_failed = s.execute(
                text(
                    "select count(*) from companies where tier=:t and ia_fit=:f "
                    "and research_data ? '_failed'"
                ),
                {"t": tier, "f": "fit"},
            ).scalar()
            print(f"{tier} fit con web: total={total}  sin_research={sin_research}  "
                  f"con_research={con_research}  con_failed={con_failed}")

        rows = s.execute(
            text(
                "select c.nif, c.nombre, c.tier, c.research_data "
                "from companies c "
                "where c.research_done_at is not null "
                "and not (c.research_data ? '_failed') "
                "order by c.research_done_at desc limit 10"
            )
        ).all()

    print()
    print("Dossiers OK más recientes (max 10):")
    for r in rows:
        print(f"\n--- {r[0]} {r[2]} {r[1]} ---")
        rd = r[3]
        if isinstance(rd, str):
            rd = json.loads(rd)
        for key in (
            "tipo_actividad_concreta", "tamano_aparente",
            "tipo_obra_que_hacen", "lenguaje_que_usan",
            "valores_que_destacan", "hooks_de_personalizacion",
            "personas_extraidas", "_warning", "_meta",
        ):
            val = rd.get(key)
            if val:
                print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
