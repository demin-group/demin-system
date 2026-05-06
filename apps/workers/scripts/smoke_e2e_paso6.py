"""Pre-check del smoke E2E paso 6.

Lista los 5 T3 fit con web sin research que los 3 workers procesarán por
orden estable (NIF asc, LIMIT 5). NO hace random — los workers ya son
determinísticos por NIF, y eso preserva auditabilidad: los NIFs que este
script imprime SON los que se procesan después.
"""
from __future__ import annotations

from sqlalchemy import text

from shared.db import get_session


def main() -> None:
    with get_session("dev") as s:
        rows = s.execute(
            text(
                """
                SELECT id, nif, nombre, web, localidad
                FROM companies
                WHERE ia_fit = 'fit'
                  AND tier = 'T3'
                  AND web IS NOT NULL
                  AND length(trim(web)) > 0
                  AND research_done_at IS NULL
                ORDER BY nif
                LIMIT 5
                """
            )
        ).mappings().all()

    if len(rows) < 5:
        print(f"AVISO: solo hay {len(rows)} T3 fit con web sin research. Smoke con N<5.")
        if not rows:
            return

    print("=" * 78)
    print("Pre-check smoke E2E paso 6 — los 5 T3 que los workers procesarán")
    print("=" * 78)
    print(f"{'NIF':<13} {'EMPRESA':<35} {'LOCALIDAD':<14} WEB")
    print("-" * 78)
    for r in rows:
        nombre = (r['nombre'] or '')[:34]
        localidad = (r['localidad'] or '')[:13]
        print(f"{r['nif']:<13} {nombre:<35} {localidad:<14} {r['web']}")
    print("=" * 78)
    print()
    print("NIFs para anotar en §19:")
    print(f"  {','.join(r['nif'] for r in rows)}")
    print()
    print("Comandos en orden:")
    print("  1. uv run python -m pipeline.research_prospect --env dev --tier T3 --limit 5 --max-cost-usd 0.50")
    print("  2. uv run python -m pipeline.find_contacts      --env dev --tier T3 --limit 5 --max-hunter-calls 10")
    print("  3. uv run python -m pipeline.generate_draft     --env dev --tier T3 --angle opening --limit 5 --max-cost-usd 0.50")


if __name__ == "__main__":
    main()
