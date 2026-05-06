"""Audit del universo elegible para generate_draft tras research+find_contacts."""
from __future__ import annotations

from sqlalchemy import text

from shared.db import get_session


def main() -> None:
    with get_session("dev") as s:
        rows = s.execute(
            text(
                """
                SELECT
                    c.nif, c.nombre, c.web,
                    c.research_done_at IS NOT NULL AS has_research,
                    (c.research_data ? '_failed') AS research_failed,
                    count(ct.id) FILTER (WHERE ct.is_optout = false) AS n_contacts,
                    count(ct.id) FILTER (
                        WHERE ct.is_optout = false
                        AND NOT EXISTS (
                            SELECT 1 FROM messages m WHERE m.contact_id = ct.id AND m.step_index = 0
                        )
                    ) AS n_contacts_pendientes_opening
                FROM companies c
                LEFT JOIN contacts ct ON ct.company_id = c.id
                WHERE c.tier = 'T3' AND c.ia_fit = 'fit'
                GROUP BY c.id, c.nif, c.nombre, c.web, c.research_done_at, c.research_data
                HAVING count(ct.id) FILTER (WHERE ct.is_optout = false) > 0
                    OR c.research_done_at IS NOT NULL
                ORDER BY c.nif
                """
            )
        ).mappings().all()

    print(f"{'NIF':<12} {'EMPRESA':<32} {'RES':4} {'FAIL':4} {'CTS':4} {'PEND':4}")
    print("-" * 70)
    for r in rows:
        print(
            f"{r['nif']:<12} {(r['nombre'] or '')[:31]:<32} "
            f"{'sí' if r['has_research'] else 'no':<4} "
            f"{'sí' if r['research_failed'] else 'no':<4} "
            f"{r['n_contacts']:<4} {r['n_contacts_pendientes_opening']:<4}"
        )

    elegibles = sum(1 for r in rows if r['has_research'] and not r['research_failed']
                    and r['n_contacts_pendientes_opening'] > 0)
    print(f"\nT3 elegibles para generate_draft (research OK + contacts sin message step 0): {elegibles}")


if __name__ == "__main__":
    main()
