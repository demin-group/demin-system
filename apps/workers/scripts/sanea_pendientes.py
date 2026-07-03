"""Saneamiento de los pendientes de 1er correo antes de generar borradores.

(1) CUARENTENA: pone is_primary=false en los contactos sospechosos (TLD
    extranjero, dominio que no cuadra con la razón social, sector raro) para
    que NO se dibujen ni envíen. Quedan en BD para investigarlos luego.
    Se commitea ANTES del FIX: un fallo en (2) no debe deshacer (1).
(2) FIX: corrige emails malformados (prefijo "%20" del scraping) — la empresa
    es correcta, solo el email venía sucio. Si ya existe el duplicado limpio,
    migra mensajes + is_primary al limpio y BORRA el roto (renombrar daría
    UniqueViolation, el bug del 30-jun).

NO envía nada. Idempotente (re-ejecutar no duplica). Solo lectura tras aplicar.

Uso (en apps/workers):  ENV=prod uv run python -m scripts.sanea_pendientes
"""
from __future__ import annotations

import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")

# Sospechosos → CUARENTENA (is_primary=false). Motivo entre paréntesis.
CUARENTENA = [
    "csmith@fowler.ca",                 # TLD .ca (Canadá) — empresa equivocada
    "lcirne@ekan.com.br",               # TLD .br (Brasil) — empresa equivocada
    "fabienne.vilain@spmt-arista.be",   # TLD .be (Bélgica) — empresa equivocada
    "shahriar@konasl.com",              # dominio no cuadra (NONIKA SL)
    "asun@alsamasa.com",                # dominio no cuadra (MECANICAS MONTESINOS)
    "laren@laren2000.com",              # dominio no cuadra (FURMEN 2000)
    "david@menasl.com",                 # dominio no cuadra (REYAC SL)
    "sonia@home4living.net",            # dominio no cuadra (LAMPAYANA SL)
    "salcon@salconalimentaria.es",      # sector raro (alimentaria) — posible empresa distinta
]

# Emails rotos (prefijo "%20" del scraping) → FIX. Empresas correctas.
MALFORMADOS = [
    "beatrizmejiamarti@estudiorydinteriorismo.es",  # ESTUDIO RYD SL
    "crisduar@crisduar.es",                         # CRISDUAR SL
]


with get_session(env) as s:  # type: ignore[arg-type]
    print("=" * 72)
    print(f"SANEAMIENTO PENDIENTES — env={env}")
    print("=" * 72)

    print("\n[1] CUARENTENA (is_primary=false → fuera de envío)")
    quar = 0
    for email in CUARENTENA:
        res = s.execute(
            text("update contacts set is_primary=false "
                 "where lower(email)=lower(:e) and is_primary=true"),
            {"e": email},
        )
        n = res.rowcount or 0
        quar += n
        print(f"   {'✓' if n else '–'} {email:<40} ({n} afectado)")
    print(f"   → {quar} contactos en cuarentena")
    s.commit()  # cuarentena guardada aunque el FIX falle

    print("\n[2] FIX emails malformados")
    for clean in MALFORMADOS:
        mal_rows = s.execute(
            text("select id::text cid, is_primary from contacts "
                 "where email like :pat and email <> :clean"),
            {"pat": "%" + clean, "clean": clean},
        ).mappings().all()
        if not mal_rows:
            print(f"   – {clean} (nada que corregir)")
            continue
        clean_row = s.execute(
            text("select id::text cid, is_primary from contacts "
                 "where lower(email) = lower(:c)"),
            {"c": clean},
        ).mappings().first()
        for mal in mal_rows:
            if clean_row is None:
                s.execute(
                    text("update contacts set email=:c where id=cast(:i as uuid)"),
                    {"c": clean, "i": mal["cid"]},
                )
                print(f"   ✓ {clean} (renombrado in situ)")
            else:
                s.execute(
                    text("update messages set contact_id=cast(:c as uuid) "
                         "where contact_id=cast(:m as uuid)"),
                    {"c": clean_row["cid"], "m": mal["cid"]},
                )
                if mal["is_primary"] and not clean_row["is_primary"]:
                    s.execute(
                        text("update contacts set is_primary=true where id=cast(:i as uuid)"),
                        {"i": clean_row["cid"]},
                    )
                s.execute(text("delete from contacts where id=cast(:i as uuid)"),
                          {"i": mal["cid"]})
                print(f"   ✓ {clean} (duplicado roto borrado; mensajes e is_primary migrados)")
        s.commit()

    # Estado tras sanear: qué se dibujará (virgin primary enviable, por tipo)
    print("\n[3] Pendientes que QUEDAN para dibujar (tras sanear)")
    for r in s.execute(text("""
        select ct.email_type, count(*) n
        from contacts ct join companies co on co.id=ct.company_id
        where ct.is_primary and not ct.is_optout and co.ia_fit='fit'
          and not exists (select 1 from messages m where m.contact_id=ct.id)
        group by 1 order by 2 desc
    """)).mappings().all():
        print(f"   {r['email_type']:<22}{r['n']:>5}")

    print("\n[4] EN CUARENTENA (para investigar después)")
    print(f"   {'NIF':<12}{'email':<40} empresa")
    for r in s.execute(text("""
        select co.nif, ct.email, co.nombre
        from contacts ct join companies co on co.id=ct.company_id
        where ct.is_primary=false and lower(ct.email) = any(:emails)
    """), {"emails": [e.lower() for e in CUARENTENA]}).mappings().all():
        print(f"   {r['nif'] or '?':<12}{r['email']:<40} {(r['nombre'] or '')[:26]}")
    print("=" * 72)
