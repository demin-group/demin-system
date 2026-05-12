"""Recompute paso 6.6 — recalcula `contacts.email_priority` con la regla
1..5 (bucket nominal-con-cargo vs sin-cargo) y reasigna `is_primary` por
empresa coherentemente.

Tras el cambio de `assign_priority` (paso 6.6, bucket 5 explícito), los
contacts ya en BD tienen `email_priority` con la enumeración antigua 1..4:
    1 = decisor confidence>=80
    2 = decisor confidence<80
    3 = nominal (sin distinción cargo)
    4 = corporativo_pequeno

Este script los pasa a la enumeración nueva 1..5:
    1 = decisor confidence>=80     (sin cambio)
    2 = decisor confidence<80      (sin cambio)
    3 = nominal CON cargo          (subset del antiguo 3)
    4 = nominal SIN cargo          (subset del antiguo 3)
    5 = corporativo_pequeno        (antes 4)

Lee `email_type`, `cargo`, `confidence` de cada contact, llama a la misma
función `assign_priority` que el worker, y aplica el UPDATE. Luego por cada
`company_id` con ≥1 contact, re-determina `is_primary`: el contact de menor
`email_priority` (desempate por confidence desc, None al final) lleva
`is_primary=true`, el resto `false`.

Idempotente: re-correr no produce cambios sobre BD ya recomputada.

Pre-requisito: migration 10 aplicada (CHECK 1..5). Sin esa migración, el
UPDATE a `email_priority=5` violaría el CHECK constraint.

Uso:
    cd apps/workers
    uv run python scripts/recompute_priorities_paso66.py --env dev --dry-run
    uv run python scripts/recompute_priorities_paso66.py --env dev
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text

from pipeline.find_contacts import assign_priority
from shared.db import get_session

EnvName = Literal["dev", "prod"]


@dataclass(slots=True)
class ContactRow:
    id: str
    company_id: str
    company_nif: str
    company_nombre: str
    email: str
    email_type: str
    cargo: str | None
    current_priority: int
    current_is_primary: bool


def fetch_contacts(env: EnvName) -> list[ContactRow]:
    """Lee contacts activos (no 'descartado'). NB: `contacts.confidence` no
    está persistido — la señal vivía solo en runtime durante el insert
    (`process_company`). Por eso para distinguir decisor priority 1 vs 2 en
    el recompute miramos el `current_priority` (preservado: 1 ⇒ era ≥80, 2 ⇒
    era <80 o None)."""
    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT
                    ct.id, ct.company_id, c.nif, c.nombre,
                    ct.email, ct.email_type, ct.cargo,
                    ct.email_priority, ct.is_primary
                FROM contacts ct
                JOIN companies c ON c.id = ct.company_id
                WHERE ct.email_type IS NOT NULL
                  AND ct.email_type != 'descartado'
                ORDER BY c.nif, ct.email_priority, ct.email
                """
            )
        ).mappings().all()
    return [
        ContactRow(
            id=str(r["id"]),
            company_id=str(r["company_id"]),
            company_nif=r["nif"],
            company_nombre=r["nombre"],
            email=r["email"],
            email_type=r["email_type"],
            cargo=r["cargo"],
            current_priority=r["email_priority"],
            current_is_primary=r["is_primary"],
        )
        for r in rows
    ]


def compute_new_priority(c: ContactRow) -> int:
    """Mapping current_priority + email_type + cargo → new_priority.

    Sin acceso a `confidence` (no persistido), la distinción decisor 1 vs 2
    se preserva del `current_priority` original. Para nominal usamos
    `assign_priority` que solo necesita `position` (cargo). Para
    corporativo_pequeno es siempre 5.
    """
    if c.email_type == "decisor":
        # Preservar la asignación 1/2 original. Sin confidence no podemos
        # recomputar el umbral 80.
        return c.current_priority
    if c.email_type == "nominal":
        # confidence no afecta a nominal en assign_priority — None es OK.
        return assign_priority("nominal", None, c.cargo)
    if c.email_type == "corporativo_pequeno":
        return 5
    # Defensivo — fetch_contacts ya filtra 'descartado', no debería caer aquí.
    raise ValueError(
        f"email_type inesperado en contact {c.email}: {c.email_type!r}"
    )


def compute_new_primary_per_company(
    contacts: list[ContactRow], new_priorities: dict[str, int]
) -> dict[str, str]:
    """Devuelve `{company_id: contact_id_primary}` ordenando por
    (new_priority asc, email asc). El desempate por email es determinístico
    e independiente de `confidence` (no persistida). En la práctica los
    buckets están suficientemente finos tras paso 6.6 que el desempate
    rara vez se invoca."""
    by_company: dict[str, list[ContactRow]] = {}
    for c in contacts:
        by_company.setdefault(c.company_id, []).append(c)

    primary_per_company: dict[str, str] = {}
    for company_id, cs in by_company.items():
        def sort_key(c: ContactRow) -> tuple[int, str]:
            return (new_priorities[c.id], c.email)
        ordered = sorted(cs, key=sort_key)
        primary_per_company[company_id] = ordered[0].id
    return primary_per_company


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo muestra el plan de cambios, sin modificar BD.",
    )
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(f"recompute_priorities_paso66  env={env}  dry_run={args.dry_run}")
    print("=" * 76)

    contacts = fetch_contacts(env)
    if not contacts:
        print("No hay contacts (email_type IS NOT NULL, != descartado). Nada que hacer.")
        return 0

    new_priorities = {c.id: compute_new_priority(c) for c in contacts}
    new_primaries = compute_new_primary_per_company(contacts, new_priorities)

    # Cambios planificados
    priority_changes = [
        c for c in contacts
        if new_priorities[c.id] != c.current_priority
    ]
    primary_changes: list[tuple[ContactRow, bool]] = []
    # contact → bool desired
    for c in contacts:
        desired = new_primaries[c.company_id] == c.id
        if desired != c.current_is_primary:
            primary_changes.append((c, desired))

    print(f"{len(contacts)} contacts revisados.")
    print()
    print(f"Priority changes: {len(priority_changes)}")
    for c in priority_changes:
        print(
            f"  {c.company_nif:<12} {c.email:<40} "
            f"type={c.email_type:<20} cargo={c.cargo or '-'!r:<32} "
            f"prio {c.current_priority} -> {new_priorities[c.id]}"
        )
    print()
    print(f"is_primary changes: {len(primary_changes)}")
    for c, desired in primary_changes:
        print(
            f"  {c.company_nif:<12} {c.email:<40} "
            f"is_primary {c.current_is_primary} -> {desired}"
        )
    print()

    if not priority_changes and not primary_changes:
        print("OK -- ningun cambio. BD ya coherente con regla paso 6.6.")
        return 0

    if args.dry_run:
        print("(dry-run -- no se modifica nada)")
        return 0

    # Aplicamos todo en una transacción.
    with get_session(env) as s:
        for c in priority_changes:
            s.execute(
                text(
                    "UPDATE contacts SET email_priority = :p "
                    "WHERE id = cast(:id as uuid)"
                ),
                {"p": new_priorities[c.id], "id": c.id},
            )
        for c, desired in primary_changes:
            s.execute(
                text(
                    "UPDATE contacts SET is_primary = :v "
                    "WHERE id = cast(:id as uuid)"
                ),
                {"v": desired, "id": c.id},
            )
    print(
        f"OK -- {len(priority_changes)} priority updates + "
        f"{len(primary_changes)} is_primary updates aplicados."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
