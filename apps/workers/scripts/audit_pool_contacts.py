"""audit_pool_contacts.py -- Sesion 2026-05-25 (Leccion 41).

Audita el pool real de contactos VIRGENES elegibles para entrar a la
cadencia automatica. Un contacto es "virgen elegible" si cumple TODAS
las condiciones:

  - companies.ia_fit = 'fit'
  - companies.research_done_at IS NOT NULL
  - NOT (companies.research_data ? '_failed')
  - contacts.is_primary = true
  - contacts.is_optout = false
  - NO existe ningun message previo para ese contact (NOT EXISTS sobre
    messages.contact_id, en CUALQUIER status -- drafted/approved/scheduled/
    sent/bounced/failed/cancelled).

Razon (Leccion 41): el pool elegible "virgen" es el universo real sobre
el que el sistema puede generar drafts NUEVOS sin re-machacar contactos
con mensajes previos. Si <100 antes de pasar a modo autonomo, el
sistema termina insistiendo a los mismos pocos contactos y quema
deliverability del dominio.

Ejecuta tambien una sanity check sobre `auto_replenish.count_contacts_
without_draft`: ambos deben devolver el mismo numero por tier (el
replenish ya filtra por `is_primary + is_optout=false` y `NOT EXISTS
messages` -- si las cifras divergen, hay un bug de filtros entre el
worker y el reporte).

CLI:
    cd apps/workers
    uv run python -m scripts.audit_pool_contacts --env prod
    uv run python -m scripts.audit_pool_contacts --env dev --threshold 100

Exit codes:
    0 -- pool >= threshold en algun tier (T3 o T3+T2)
    1 -- pool < threshold en todos los tiers (alerta de "machaque inminente")
"""
from __future__ import annotations

import argparse
import sys
from typing import Literal

from sqlalchemy import text

from shared.db import get_session

EnvName = Literal["dev", "prod"]

TIERS = ("T1", "T2", "T3", "T4")
DEFAULT_THRESHOLD = 100


def pool_breakdown(env: EnvName) -> dict[str, dict[str, int]]:
    """Devuelve por tier: {fit, with_research, with_primary, virgin_eligible}.

    Cada nivel es un filtro acumulativo. Permite ver donde se cae el
    universo: muchas empresas fit pero pocas con research = research no
    se ha ejecutado todavia; muchas con research pero pocas con primary
    = find_contacts no encontro emails; muchas con primary pero pocas
    virgenes = el sistema ya envio a la mayoria.
    """
    out: dict[str, dict[str, int]] = {}
    with get_session(env) as s:
        for tier in TIERS:
            fit = int(s.execute(
                text("select count(*) from companies where tier=:t and ia_fit='fit'"),
                {"t": tier},
            ).scalar() or 0)
            with_research = int(s.execute(
                text(
                    "select count(*) from companies "
                    "where tier=:t and ia_fit='fit' "
                    "  and research_done_at is not null "
                    "  and not (research_data ? '_failed')"
                ),
                {"t": tier},
            ).scalar() or 0)
            with_primary = int(s.execute(
                text(
                    "select count(distinct c.id) from companies c "
                    "join contacts ct on ct.company_id = c.id "
                    "where c.tier=:t and c.ia_fit='fit' "
                    "  and c.research_done_at is not null "
                    "  and not (c.research_data ? '_failed') "
                    "  and ct.is_primary=true and ct.is_optout=false"
                ),
                {"t": tier},
            ).scalar() or 0)
            # Pool virgen elegible: contact con primary + sin mensaje previo
            virgin = int(s.execute(
                text(
                    "select count(*) from contacts ct "
                    "join companies c on c.id = ct.company_id "
                    "where c.tier=:t and c.ia_fit='fit' "
                    "  and c.research_done_at is not null "
                    "  and not (c.research_data ? '_failed') "
                    "  and ct.is_primary=true and ct.is_optout=false "
                    "  and not exists ("
                    "    select 1 from messages m where m.contact_id = ct.id"
                    "  )"
                ),
                {"t": tier},
            ).scalar() or 0)
            out[tier] = {
                "fit": fit,
                "with_research": with_research,
                "with_primary": with_primary,
                "virgin_eligible": virgin,
            }
    return out


def replenish_sanity(env: EnvName) -> dict[str, int]:
    """Cross-check: ejecuta el mismo query que `auto_replenish.count_
    contacts_without_draft` y reporta por tier. Debe coincidir con
    `virgin_eligible` de pool_breakdown -- si no coincide, hay un drift
    de filtros entre auditoria y worker que hay que reconciliar.
    """
    out: dict[str, int] = {}
    with get_session(env) as s:
        for tier in TIERS:
            n = int(s.execute(
                text(
                    "select count(*) from contacts c "
                    "join companies co on co.id = c.company_id "
                    "where c.is_primary = true "
                    "  and c.is_optout = false "
                    "  and co.tier = :tier "
                    "  and co.ia_fit = 'fit' "
                    "  and co.research_done_at is not null "
                    "  and not (co.research_data ? '_failed') "
                    "  and not exists ("
                    "    select 1 from messages m where m.contact_id = c.id"
                    "  )"
                ),
                {"tier": tier},
            ).scalar() or 0)
            out[tier] = n
    return out


def messages_by_status(env: EnvName) -> dict[str, int]:
    """Conteo total de messages por status. Util para contextualizar
    el pool virgen: si hay 100 messages 'sent' y 10 contactos virgenes,
    el sistema casi ha agotado su universo (Leccion 41)."""
    out: dict[str, int] = {}
    with get_session(env) as s:
        rows = s.execute(
            text(
                "select status, count(*) as n from messages "
                "group by status order by status"
            )
        ).mappings().all()
        for r in rows:
            out[r["status"]] = int(r["n"])
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_THRESHOLD,
        help=f"Pool minimo virgen elegible para activar autonomo (default {DEFAULT_THRESHOLD}, Leccion 41).",
    )
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(f"audit_pool_contacts  env={env}  threshold={args.threshold}")
    print("=" * 76)
    print()

    # 1. Breakdown por tier
    breakdown = pool_breakdown(env)
    print("[pool por tier]")
    print(
        f"  {'tier':<6} {'fit':>8} {'+research':>12} {'+primary':>10} {'virgin':>10}"
    )
    total_virgin = 0
    for tier in TIERS:
        b = breakdown[tier]
        print(
            f"  {tier:<6} {b['fit']:>8} {b['with_research']:>12} "
            f"{b['with_primary']:>10} {b['virgin_eligible']:>10}"
        )
        total_virgin += b["virgin_eligible"]
    print(f"  {'TOTAL':<6} {'':>8} {'':>12} {'':>10} {total_virgin:>10}")
    print()

    # 2. Sanity check vs auto_replenish
    sanity = replenish_sanity(env)
    print("[sanity vs auto_replenish.count_contacts_without_draft]")
    drift = False
    for tier in TIERS:
        v = breakdown[tier]["virgin_eligible"]
        s = sanity[tier]
        marker = "" if v == s else "  ⚠ DRIFT"
        if v != s:
            drift = True
        print(f"  {tier}: pool_breakdown={v}  replenish={s}{marker}")
    if drift:
        print()
        print("⚠ DRIFT DETECTADO: los filtros de la auditoria y de auto_replenish")
        print("  difieren. Investigar antes de confiar en cualquiera de los dos.")
    print()

    # 3. Conteo de messages por status
    statuses = messages_by_status(env)
    print("[messages por status (contexto del consumo del pool)]")
    if not statuses:
        print("  (sin mensajes en BD)")
    else:
        for st, n in statuses.items():
            print(f"  {st:<12} {n:>6}")
    print()

    # 4. Veredicto
    print("=" * 76)
    print("[veredicto pool virgen (Leccion 41)]")
    t3 = breakdown["T3"]["virgin_eligible"]
    t2 = breakdown["T2"]["virgin_eligible"]
    t1 = breakdown["T1"]["virgin_eligible"]
    t4 = breakdown["T4"]["virgin_eligible"]
    print(f"  T3 solo:        {t3:>6}")
    print(f"  T3 + T2:        {t3 + t2:>6}")
    print(f"  T3 + T2 + T1:   {t3 + t2 + t1:>6}")
    print(f"  TOTAL (4 tiers):{total_virgin:>6}")
    print()

    if t3 >= args.threshold:
        print(f"  ✅ T3 solo cubre threshold ({t3} >= {args.threshold}).")
        rc = 0
    elif (t3 + t2) >= args.threshold:
        print(f"  ⚠  T3 solo no cubre ({t3} < {args.threshold}). T3+T2 si ({t3 + t2}).")
        print(f"     Recomendacion: arrancar autonomo con T3+T2 incorporado, no solo T3.")
        rc = 0
    elif total_virgin >= args.threshold:
        print(f"  ⚠  T3+T2 < threshold. Total 4 tiers cubre ({total_virgin}).")
        print(f"     Recomendacion: ampliar a T1 y/o T4 (Opcion C Sprint 5) antes de autonomo.")
        rc = 0
    else:
        print(f"  ❌ POOL INSUFICIENTE: {total_virgin} < {args.threshold} (threshold).")
        print(f"     Activar autonomo aqui machacaria el mismo subset de contactos.")
        print(f"     Acciones: ejecutar research_prospect sobre fits sin research, o")
        print(f"     find_contacts sobre research-done sin primary, antes de continuar.")
        rc = 1
    print("=" * 76)
    return rc


if __name__ == "__main__":
    sys.exit(main())
