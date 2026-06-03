"""hunter_retry_nocontacts.py — retry Hunter dirigido sobre companies fit sin contacts.

Sesión 2026-06-03 (recuperación T2): tras el scraper de webs
(`pipeline/scrape_emails.py`), relanza Hunter SOLO sobre las empresas del tier
que siguen sin ningún contact. Reutiliza la maquinaria de `find_contacts`
(clasificación D20 + priorización D18 + insert idempotente) sin modificarla:
la política D20 se aplica intacta (T2 rechaza corporativo_pequeno y A3).

Diferencia clave con `find_contacts`: además de insertar lo aceptado,
REPORTA lo que Hunter devolvió y D20 filtró (email + tipo + razón), para que
PM tenga visibilidad de si el cuello de botella es cobertura de Hunter o la
política — sin relajar nada silenciosamente.

CLI:
    cd apps/workers
    uv run python -m scripts.hunter_retry_nocontacts --env prod --tier T2 \
        --exclude-nif B28293884 --exclude-nif B87984258 --max-hunter-calls 40
"""
from __future__ import annotations

import argparse
import json
import sys

from pipeline.find_contacts import (
    classify_and_filter,
    fetch_pending,
    insert_contacts,
    resolve_domain_from_company,
    select_top_candidates,
)
from shared.email_policy import classify_email, is_acceptable_for_tier


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Hunter retry dirigido sobre fit sin contacts")
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--tier", choices=("T1", "T2", "T3", "T4"), required=True)
    p.add_argument("--max-hunter-calls", type=int, default=40)
    p.add_argument("--exclude-nif", action="append", default=[])
    args = p.parse_args(argv)

    pending = fetch_pending(args.env, args.tier, None, reprocess=False)
    targets = [c for c in pending if c.nif not in args.exclude_nif]
    print("=" * 76)
    print(
        f"hunter_retry  env={args.env}  tier={args.tier}  "
        f"pendientes={len(pending)}  tras_exclusiones={len(targets)}  "
        f"cap={args.max_hunter_calls}"
    )
    print("=" * 76)
    if not targets:
        print("Nada que reintentar.")
        return 0

    from shared.hunter_adapter import HunterAdapter  # noqa: PLC0415

    calls = 0
    inserted_total = 0
    recovered: list[str] = []
    filtered_d20: list[dict] = []
    empty_hunter: list[str] = []

    with HunterAdapter() as hunter:
        for i, company in enumerate(targets, 1):
            if calls >= args.max_hunter_calls:
                print(f"  [cap] {calls} llamadas — parando")
                break
            domain = resolve_domain_from_company(company.web)
            if not domain:
                print(f"  [{i:>2}/{len(targets)}] {company.nombre[:40]:<40} skip_sin_dominio")
                continue

            raw = hunter.find_contacts_by_domain(domain, company.nombre)
            calls += 1

            accepted = select_top_candidates(classify_and_filter(raw, company))
            if accepted:
                n = insert_contacts(args.env, company, accepted)
                inserted_total += n
                recovered.append(company.nif)
                print(
                    f"  [{i:>2}/{len(targets)}] {company.nombre[:40]:<40} "
                    f"RECUPERADA ins={n}: {', '.join(c.email for c in accepted)}"
                )
                continue

            # Nada aceptado — reportar qué devolvió Hunter y por qué se filtró.
            rejected = []
            for r in raw:
                if not r.email or "@" not in r.email:
                    continue
                cls = classify_email(r.email, r.position, r.person_name, company.tier)
                rejected.append({
                    "email": r.email,
                    "email_type": cls.email_type,
                    "aceptable_tier": is_acceptable_for_tier(cls.email_type, company.tier),
                    "razon": cls.reason,
                })
            if rejected:
                filtered_d20.append({
                    "nif": company.nif, "nombre": company.nombre,
                    "domain": domain, "rechazados": rejected,
                })
                print(
                    f"  [{i:>2}/{len(targets)}] {company.nombre[:40]:<40} "
                    f"FILTRADO_D20 ({len(rejected)} emails de Hunter rechazados)"
                )
            else:
                empty_hunter.append(company.nif)
                print(f"  [{i:>2}/{len(targets)}] {company.nombre[:40]:<40} hunter_vacio")

    print()
    print("=" * 76)
    print(
        f"FIN hunter_retry  calls={calls}  empresas_recuperadas={len(recovered)}  "
        f"contacts_insertados={inserted_total}"
    )
    print(f"  hunter_vacio (sin resultados):     {len(empty_hunter)}")
    print(f"  filtrado_d20 (resultados rechazados): {len(filtered_d20)}")
    if filtered_d20:
        print()
        print("DETALLE FILTRADO D20 (para decisión PM, NO insertado):")
        print(json.dumps(filtered_d20, ensure_ascii=False, indent=2))
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
