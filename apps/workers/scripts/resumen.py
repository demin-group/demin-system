"""Resumen preciso del estado de captación. Solo lectura.

Responde, con números exactos de la BD:
  1) Cuántos correos hay para enviar (total) — empresas por tier y fit +
     contactos (emails) que tenemos, y cuántos son "enviables".
  2) A cuántos se ha enviado un correo hasta ahora.
  3) Cuántos faltan por enviar.
  4) Cuántos se han recontactado (follow-ups + re-engage).

Uso (en apps/workers):  ENV=prod uv run python -m scripts.resumen
"""
from __future__ import annotations

import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")


def rows(s, sql):
    return s.execute(text(sql)).mappings().all()


def one(s, sql):
    return s.execute(text(sql)).scalar() or 0


with get_session(env) as s:  # type: ignore[arg-type]
    print("=" * 72)
    print(f"RESUMEN DE CAPTACIÓN — env={env}")
    print("=" * 72)

    # ── 1a. EMPRESAS por tier y fit ─────────────────────────────────────────
    print("\n[1a] EMPRESAS (universo) por tier × fit")
    print(f"     {'tier':<12}{'ia_fit':<10}{'n':>8}")
    for r in rows(s, "select coalesce(tier,'(sin)') tier, coalesce(ia_fit,'(sin)') fit, "
                     "count(*) n from companies group by 1,2 order by 1,2"):
        print(f"     {r['tier']:<12}{r['fit']:<10}{r['n']:>8}")
    tot_emp = one(s, "select count(*) from companies")
    tot_fit = one(s, "select count(*) from companies where ia_fit='fit'")
    print(f"     {'-'*30}")
    print(f"     TOTAL empresas: {tot_emp}   |   FIT (objetivo real): {tot_fit}")

    # ── 1b. CONTACTOS (emails que tenemos) ──────────────────────────────────
    print("\n[1b] CONTACTOS (emails que tenemos) por tier")
    print(f"     {'tier':<12}{'total':>8}{'primary':>9}{'ENVIABLE':>10}")
    for r in rows(s, """
        select coalesce(co.tier,'(sin)') tier,
               count(*) total,
               count(*) filter (where ct.is_primary) prim,
               count(*) filter (where ct.is_primary and not ct.is_optout and co.ia_fit='fit') env
        from contacts ct join companies co on co.id = ct.company_id
        group by 1 order by 1
    """):
        print(f"     {r['tier']:<12}{r['total']:>8}{r['prim']:>9}{r['env']:>10}")
    tot_ct = one(s, "select count(*) from contacts")
    enviables = one(s, """
        select count(*) from contacts ct join companies co on co.id=ct.company_id
        where ct.is_primary and not ct.is_optout and co.ia_fit='fit'
    """)
    print(f"     {'-'*39}")
    print(f"     TOTAL contactos: {tot_ct}")
    print(f"     >>> CORREOS PARA ENVIAR (primary + fit + no opt-out): {enviables}")

    # ── 2. ENVIADOS hasta ahora ─────────────────────────────────────────────
    print("\n[2] ENVIADOS hasta ahora (a cuántos se ha escrito)")
    print(f"     {'tier':<12}{'contactos':>11}")
    for r in rows(s, """
        select coalesce(co.tier,'(sin)') tier, count(distinct m.contact_id) n
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where m.status in ('sent','bounced')
        group by 1 order by 1
    """):
        print(f"     {r['tier']:<12}{r['n']:>11}")
    cont_env = one(s, "select count(distinct contact_id) from messages where status in ('sent','bounced')")
    emp_env = one(s, """
        select count(distinct co.id) from messages m
        join contacts ct on ct.id=m.contact_id join companies co on co.id=ct.company_id
        where m.status in ('sent','bounced')
    """)
    msg_env = one(s, "select count(*) from messages where status in ('sent','bounced')")
    print(f"     {'-'*23}")
    print(f"     >>> CONTACTOS con correo enviado: {cont_env}   (EMPRESAS distintas: {emp_env})")
    print(f"     (correos totales enviados, incl. follow-ups: {msg_env})")

    # ── 3. FALTAN por enviar ────────────────────────────────────────────────
    print("\n[3] FALTAN por enviar (enviables vírgenes, sin ningún correo)")
    print(f"     {'tier':<12}{'faltan':>8}")
    for r in rows(s, """
        select coalesce(co.tier,'(sin)') tier, count(*) n
        from contacts ct join companies co on co.id = ct.company_id
        where ct.is_primary and not ct.is_optout and co.ia_fit='fit'
          and not exists (select 1 from messages m where m.contact_id = ct.id)
        group by 1 order by 1
    """):
        print(f"     {r['tier']:<12}{r['n']:>8}")
    faltan = one(s, """
        select count(*) from contacts ct join companies co on co.id=ct.company_id
        where ct.is_primary and not ct.is_optout and co.ia_fit='fit'
          and not exists (select 1 from messages m where m.contact_id=ct.id)
    """)
    print(f"     {'-'*20}")
    print(f"     >>> FALTAN POR ENVIAR (1er correo): {faltan}")

    # ── 4. RECONTACTO ───────────────────────────────────────────────────────
    print("\n[4] RECONTACTO")
    print("     correos enviados por ángulo:")
    for r in rows(s, "select coalesce(angle,'(sin)') angle, count(*) n from messages "
                     "where status in ('sent','bounced') group by 1 order by 2 desc"):
        print(f"       {r['angle']:<16}{r['n']:>6}")
    recontactados = one(s, """
        select count(*) from (
          select contact_id from messages where status in ('sent','bounced')
          group by contact_id having count(*) > 1
        ) x
    """)
    reengage = one(s, "select count(*) from messages where angle in ('re_engage_40','re_engage_90')")
    print(f"     {'-'*22}")
    print(f"     >>> CONTACTOS RECONTACTADOS (≥2 correos / follow-up): {recontactados}")
    print(f"     >>> de ellos, re-engage (re_engage_40/90): {reengage}")
    print("=" * 72)
