"""Piloto de medición — canal de DECISOR sin info@ (BORME → Hunter Email Finder).

Mide, sin enviar nada y (en modo --from-list) sin tocar la BD, el rendimiento
real del puente: empresa (con dominio) → nombre del administrador/cargo del
BORME (OpenMercantil) → email PERSONAL (Hunter Email Finder por nombre+dominio)
→ política cero-info@ (`email_policy`). Reporta cuántas empresas producen un
email personal aceptable (decisor/nominal) y cuántas se DESCARTAN (sin caer
nunca a info@).

Decisiones que implementa (2026-06-23, Fer):
  - Cero info@: se RECHAZA `corporativo_pequeno`; si no hay personal → descartar.
  - Sin verificador de pago: la confianza se basa en el `score` de Hunter, su
    `verification.status` y el nº de `sources`. Se reporta para calibrar umbral.

Modos:
  --from-list FICHERO   Una empresa por línea: "RAZÓN SOCIAL | dominio.es".
                        No toca BD. Para validación local.
  --from-db --tier T3   Lee companies ia_fit='fit' con web del tier (en VPS/prod).
                        --limit N (default 25).

Uso (en apps/workers):
  ENV=dev  uv run python -m scripts.pilot_decisor_emails --from-list lista.txt
  ENV=prod uv run python -m scripts.pilot_decisor_emails --from-db --tier T3 --limit 25
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

from shared.config import settings
from shared.email_policy import classify_email, is_acceptable_for_tier
from shared.openmercantil_adapter import OpenMercantilClient

VALID_TIERS = ("T1", "T2", "T3", "T4")


def hunter_email_finder(client: httpx.Client, full_name: str, domain: str) -> dict | None:
    """Llama Hunter Email Finder (nombre+dominio). Devuelve el bloque `data`
    completo (email, score, position, sources, verification) o None.

    La API key va en el header `Authorization` del cliente (ver `main`), NO en
    la query string — así no se filtra en logs/URLs ni en la excepción de
    `raise_for_status()`."""
    if not full_name or not domain:
        return None
    r = client.get(
        settings.HUNTER_BASE_URL + "email-finder",
        params={"full_name": full_name, "domain": domain},
    )
    if r.status_code in (400, 404):
        return None
    r.raise_for_status()
    return r.json().get("data") or {}


def load_companies_from_list(path: str) -> list[tuple[str, str, str | None]]:
    """Lee 'razón social | dominio' por línea. Devuelve (name, domain, nif=None)."""
    out: list[tuple[str, str, str | None]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.upper().startswith("TOTAL"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and parts[1]:
                domain = parts[1].replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
                out.append((parts[0], domain, None))
    return out


def load_companies_from_db(tier: str, limit: int) -> list[tuple[str, str, str | None]]:
    """Lee del pool SABI: companies ia_fit='fit' del tier, con web. Solo VPS/prod."""
    from sqlalchemy import text  # noqa: PLC0415

    from shared.db import get_session  # noqa: PLC0415

    env = "prod" if settings.SUPABASE_ENV == "prod" else "dev"
    sql = text(
        """
        SELECT nombre, web, nif FROM companies
        WHERE ia_fit = 'fit' AND tier = :tier
          AND web IS NOT NULL AND length(trim(web)) > 0
        ORDER BY nif LIMIT :lim
        """
    )
    with get_session(env) as s:
        rows = s.execute(sql, {"tier": tier, "lim": limit}).mappings().all()
    out: list[tuple[str, str, str | None]] = []
    for r in rows:
        domain = (r["web"] or "").replace("https://", "").replace("http://", "").replace("www.", "").strip().rstrip("/")
        domain = domain.split("/")[0]
        if domain:
            out.append((r["nombre"], domain, r["nif"]))
    return out


def confidence_note(data: dict) -> str:
    """Resume la señal de confianza disponible SIN verificador de pago."""
    score = data.get("score")
    ver = (data.get("verification") or {}).get("status")
    n_src = len(data.get("sources") or [])
    return f"score={score} verif={ver} sources={n_src}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Piloto canal decisor sin info@")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-list", metavar="FICHERO")
    src.add_argument("--from-db", action="store_true")
    p.add_argument("--tier", default="T3", choices=VALID_TIERS)
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--min-score", type=int, default=0,
                   help="Umbral de score Hunter para considerar 'enviable' (0=solo reporta).")
    args = p.parse_args(argv)

    if not settings.HUNTER_API_KEY:
        print("ERROR: HUNTER_API_KEY no configurada en el .env del entorno.", file=sys.stderr)
        return 2

    if args.from_list:
        companies = load_companies_from_list(args.from_list)
    else:
        companies = load_companies_from_db(args.tier, args.limit)

    tier = args.tier
    print("=" * 100)
    print(f"PILOTO DECISOR sin info@  |  tier={tier}  |  {len(companies)} empresas  |  fuente nombre=BORME/OpenMercantil")
    print("=" * 100)

    n = len(companies)
    no_decisor = 0     # BORME no da persona física
    decisor_no_email = 0  # hay nombre pero Hunter no encuentra email
    personal_ok = 0    # email personal aceptado (decisor/nominal)
    rejected_generic = 0  # Hunter devolvió genérico → rechazado (cero info@)
    sendable = 0       # personal_ok que además pasa --min-score

    # API key en header Authorization (fuera de la URL → no se filtra en logs).
    hunter_headers = {"Authorization": f"Bearer {settings.HUNTER_API_KEY}"}
    with OpenMercantilClient() as om, httpx.Client(timeout=30.0, headers=hunter_headers) as hc:
        for name, domain, nif in companies:
            officer = om.find_decisor(nif, name)
            if officer is None:
                no_decisor += 1
                print(f"  ✗ {name[:38]:38} {domain:30} → sin persona física en BORME")
                time.sleep(0.1)
                continue

            data = hunter_email_finder(hc, officer.full_name_natural, domain)
            email = (data or {}).get("email")
            if not email:
                decisor_no_email += 1
                print(f"  ◐ {name[:38]:38} {domain:30} → {officer.role}: {officer.full_name_natural} | Hunter sin email")
                time.sleep(0.2)
                continue

            cls = classify_email(email, officer.role, officer.full_name_natural, tier)
            acceptable = is_acceptable_for_tier(cls.email_type, tier)
            is_generic = cls.email_type == "corporativo_pequeno"
            note = confidence_note(data)

            if is_generic or not acceptable:
                rejected_generic += 1
                print(f"  ✗ {name[:38]:38} {domain:30} → {email} [{cls.email_type}] RECHAZADO (cero info@) | {note}")
            else:
                personal_ok += 1
                score = (data or {}).get("score") or 0
                send = score >= args.min_score
                if send:
                    sendable += 1
                flag = "✔" if send else "✓"
                print(f"  {flag} {name[:38]:38} {domain:30} → {email} [{cls.email_type}] {officer.role}: {officer.full_name_natural} | {note}")
            time.sleep(0.2)

    print("=" * 100)
    print("RESUMEN")
    print(f"  empresas evaluadas:                 {n}")
    print(f"  sin persona física en BORME:        {no_decisor}  ({pct(no_decisor, n)})")
    print(f"  con nombre pero Hunter sin email:   {decisor_no_email}  ({pct(decisor_no_email, n)})")
    print(f"  email genérico → RECHAZADO:         {rejected_generic}  ({pct(rejected_generic, n)})")
    print(f"  EMAIL PERSONAL aceptado:            {personal_ok}  ({pct(personal_ok, n)})  ← cola sin info@")
    if args.min_score:
        print(f"     de ellos con score>={args.min_score}:        {sendable}  ({pct(sendable, n)})  ← 'enviable' sin verificador")
    print("=" * 100)
    return 0


def pct(x: int, total: int) -> str:
    return f"{100 * x // total}%" if total else "0%"


if __name__ == "__main__":
    raise SystemExit(main())
