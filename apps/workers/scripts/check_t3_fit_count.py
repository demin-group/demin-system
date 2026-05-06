"""Smoke previo / posterior a Sprint 4 paso 4. Inspecciona contacts insertados
por find_contacts en dev."""
from __future__ import annotations

from sqlalchemy import text

from shared.config import settings
from shared.db import get_session


def main() -> None:
    with get_session("dev") as s:
        total = s.execute(
            text("select count(*) from companies where tier=:t and ia_fit=:f"),
            {"t": "T3", "f": "fit"},
        ).scalar()
        sin_contacts = s.execute(
            text(
                "select count(*) from companies c "
                "where c.tier=:t and c.ia_fit=:f "
                "and not exists (select 1 from contacts where company_id = c.id)"
            ),
            {"t": "T3", "f": "fit"},
        ).scalar()
        marcadas_sin_contactos = s.execute(
            text(
                "select count(*) from companies "
                "where tier=:t and ia_fit=:f and ia_fit_reason=:r"
            ),
            {"t": "T3", "f": "fit", "r": "no_contactos_encontrados"},
        ).scalar()
        rows = s.execute(
            text(
                "select c.nif, c.nombre, ct.email, ct.email_type, ct.email_priority, "
                "ct.is_primary, ct.nombre, ct.cargo, ct.email_verified, ct.email_source "
                "from contacts ct join companies c on c.id = ct.company_id "
                "order by c.nif, ct.email_priority"
            )
        ).all()

    print(f"companies T3 ia_fit='fit' en dev:                    {total}")
    print(f"  de las cuales sin contacts:                       {sin_contacts}")
    print(f"  marcadas con ia_fit_reason='no_contactos_encontrados': {marcadas_sin_contactos}")
    print(f"HUNTER_API_KEY len: {len(settings.HUNTER_API_KEY) if settings.HUNTER_API_KEY else 0}")
    print()
    print(f"Contacts insertados ({len(rows)}):")
    for r in rows:
        print(
            f"  {r[0]} {r[1][:30]:<30}  {r[2]:<35}  "
            f"type={r[3]:<20}  prio={r[4]}  primary={r[5]}  "
            f"verified={r[8]}  src={r[9]}"
        )
        print(f"      nombre={r[6]!r}  cargo={r[7]!r}")


if __name__ == "__main__":
    main()
