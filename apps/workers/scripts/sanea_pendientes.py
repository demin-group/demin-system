"""Saneamiento de los pendientes de 1er correo antes de generar borradores.

(1) CUARENTENA: pone is_primary=false en los contactos sospechosos (TLD
    extranjero, dominio que no cuadra con la razón social, sector raro) para
    que NO se dibujen ni envíen. Quedan en BD para investigarlos luego.
(2) FIX: corrige un email malformado (espacio %20 al inicio) — la empresa es
    correcta, solo el email venía sucio del scraping.

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

# Email roto → FIX (quita el %20 inicial). Empresa correcta (ESTUDIO RYD SL).
FIX_SUFFIX = "beatrizmejiamarti@estudiorydinteriorismo.es"


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

    print("\n[2] FIX email malformado")
    fix = s.execute(
        text("update contacts set email=:clean "
             "where email like :pat and email <> :clean"),
        {"clean": FIX_SUFFIX, "pat": "%" + FIX_SUFFIX},
    )
    print(f"   {'✓' if fix.rowcount else '–'} {FIX_SUFFIX} ({fix.rowcount or 0} corregido)")

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
