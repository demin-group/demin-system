"""Imprime los drafts del smoke E2E paso 6 para auditoría."""
from __future__ import annotations

from sqlalchemy import text

from shared.db import get_session


def main() -> None:
    with get_session("dev") as s:
        rows = s.execute(
            text(
                """
                SELECT
                    m.id, m.subject, m.body, m.angle, m.created_at,
                    m.research_snapshot,
                    ct.email, ct.email_type, ct.email_priority, ct.nombre, ct.cargo,
                    c.nif, c.nombre AS company_nombre
                FROM messages m
                JOIN contacts ct ON ct.id = m.contact_id
                JOIN companies c ON c.id = ct.company_id
                WHERE m.status = 'drafted'
                ORDER BY c.nif, ct.email_priority, m.created_at
                """
            )
        ).mappings().all()

    sep = "=" * 78
    for r in rows:
        print(f"\n{sep}")
        print(f"{r['nif']} {r['company_nombre']} — {r['email']} ({r['email_type']}, prio={r['email_priority']})")
        if r['nombre']:
            print(f"  Nombre/cargo: {r['nombre']} / {r['cargo'] or '—'}")
        print(f"  Ángulo: {r['angle']}  msg_id={str(r['id'])[:8]}")
        print(f"\n  ASUNTO: {r['subject']}")
        print(f"  CUERPO:")
        for line in (r['body'] or '').splitlines():
            print(f"    {line}")
        razonamiento = (r['research_snapshot'] or {}).get("_razonamiento_breve")
        if razonamiento:
            print(f"\n  RAZONAMIENTO: {razonamiento}")


if __name__ == "__main__":
    main()
