"""Debug — estado de contacts T3 dev + messages."""
from __future__ import annotations

from sqlalchemy import text

from shared.db import get_session


def main() -> None:
    with get_session("dev") as s:
        rows = s.execute(
            text(
                """
                SELECT ct.email, ct.email_type, ct.email_priority, ct.is_primary,
                       c.nif, c.nombre, m.id AS msg_id, m.status, m.subject
                FROM contacts ct
                JOIN companies c ON c.id = ct.company_id
                LEFT JOIN messages m ON m.contact_id = ct.id
                WHERE c.tier = 'T3' AND c.ia_fit = 'fit'
                ORDER BY c.nif, ct.email_priority, ct.email
                """
            )
        ).mappings().all()
    for r in rows:
        msg = str(r["msg_id"])[:8] if r["msg_id"] else "-"
        status = r["status"] or "-"
        print(
            f"{r['nif']:<12} {r['email']:<40} "
            f"type={r['email_type']:<22} prio={r['email_priority']} "
            f"primary={r['is_primary']} msg={msg} status={status}"
        )


if __name__ == "__main__":
    main()
