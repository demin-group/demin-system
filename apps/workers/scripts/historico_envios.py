"""Histórico de envíos: cuántos correos y a cuántas empresas. Solo lectura.
Uso (en apps/workers):  ENV=prod uv run python -m scripts.historico_envios
"""
from __future__ import annotations

import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")


def q(s, sql):
    return s.execute(text(sql)).mappings().all()


with get_session(env) as s:  # type: ignore[arg-type]
    print("=" * 60)
    print(f"HISTÓRICO DE ENVÍOS — env={env}")
    print("=" * 60)

    print("\n[mensajes por estado]")
    for r in q(s, "select status, count(*) n from messages group by status order by n desc"):
        print(f"  {r['status']:<12} {r['n']:>5}")

    sent = q(s, "select count(*) n from messages where status='sent'")[0]["n"]
    bounced = q(s, "select count(*) n from messages where status='bounced'")[0]["n"]
    print(f"\n  → CORREOS ENVIADOS (sent): {sent}   (+{bounced} rebotados)")

    emp = q(s, """
        select count(distinct co.id) n
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where m.status in ('sent','bounced')
    """)[0]["n"]
    print(f"  → EMPRESAS DISTINTAS contactadas: {emp}")

    print("\n[envíos por ángulo (apertura vs seguimientos)]")
    for r in q(s, "select coalesce(angle,'<null>') a, count(*) n from messages "
                  "where status in ('sent','bounced') group by a order by n desc"):
        print(f"  {r['a']:<14} {r['n']:>5}")

    print("\n[envíos por mes]")
    rows = q(s, "select to_char(sent_at,'YYYY-MM') ym, count(*) n from messages "
                "where status in ('sent','bounced') and sent_at is not null "
                "group by ym order by ym")
    if not rows:
        print("  (sin sent_at)")
    for r in rows:
        print(f"  {r['ym']}   {r['n']:>5}")

    print("\n[envíos por tier]")
    for r in q(s, """
        select coalesce(co.tier,'<null>') t, count(*) n
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where m.status in ('sent','bounced')
        group by t order by n desc
    """):
        print(f"  {r['t']:<6} {r['n']:>5}")
    print()
