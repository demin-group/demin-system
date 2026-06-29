"""Detalle de los contactos PENDIENTES de primer correo (vírgenes enviables):
¿son info@ (corporativo_pequeno) o de calidad (decisor/nominal)? Solo lectura.

Uso (en apps/workers):  ENV=prod uv run python -m scripts.faltan_detalle
"""
from __future__ import annotations

import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")

WHERE = """
    from contacts ct join companies co on co.id = ct.company_id
    where ct.is_primary and not ct.is_optout and co.ia_fit = 'fit'
      and not exists (select 1 from messages m where m.contact_id = ct.id)
"""

with get_session(env) as s:  # type: ignore[arg-type]
    print("=" * 78)
    print(f"PENDIENTES DE 1er CORREO — calidad del email — env={env}")
    print("=" * 78)

    print("\n[por email_type]")
    for r in s.execute(text(
        f"select ct.email_type, count(*) n {WHERE} group by 1 order by 2 desc"
    )).mappings().all():
        print(f"   {r['email_type']:<22}{r['n']:>5}")

    print("\n[por fuente del email]")
    for r in s.execute(text(
        f"select coalesce(ct.email_source,'(sin)') src, count(*) n {WHERE} group by 1 order by 2 desc"
    )).mappings().all():
        print(f"   {r['src']:<22}{r['n']:>5}")

    print("\n[lista completa]")
    print(f"   {'tier':<6}{'email_type':<22}{'prio':>4}  {'email':<38} empresa")
    for r in s.execute(text(
        f"""select co.tier, ct.email_type, ct.email_priority prio, ct.email, co.nombre {WHERE}
            order by ct.email_priority, co.tier"""
    )).mappings().all():
        nombre = (r["nombre"] or "")[:28]
        print(f"   {r['tier'] or '?':<6}{r['email_type']:<22}{r['prio']:>4}  {r['email']:<38} {nombre}")
    print("=" * 78)
