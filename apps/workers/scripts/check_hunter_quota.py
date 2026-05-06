"""Pre-check de cuota Hunter antes del smoke E2E del paso 6.

Llama GET /v2/account de Hunter, que NO consume búsquedas — solo lee metadata
de la cuenta. Reporta búsquedas usadas/restantes del mes y fecha de reset.

Si quedan <10, el caller debe parar el smoke y reportar al humano antes de
gastar nada (gate confirmado por Alberto en sesión 2026-05-06).
"""
from __future__ import annotations

import sys

import httpx

from shared.config import settings


def main() -> int:
    if not settings.HUNTER_API_KEY:
        print("ERROR: HUNTER_API_KEY no configurada")
        return 2

    url = f"{settings.HUNTER_BASE_URL.rstrip('/')}/account"
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, params={"api_key": settings.HUNTER_API_KEY})

    if r.status_code != 200:
        print(f"ERROR: HTTP {r.status_code}")
        print(r.text[:500])
        return 2

    body = r.json().get("data", {})
    plan = body.get("plan_name", "?")
    plan_level = body.get("plan_level")
    reset_date = body.get("reset_date", "?")
    requests_used = body.get("requests", {}).get("searches", {}).get("used")
    requests_avail = body.get("requests", {}).get("searches", {}).get("available")

    print("=" * 60)
    print(f"Hunter account quota — pre-check Sprint 4 paso 6")
    print("=" * 60)
    print(f"plan: {plan} (level={plan_level})")
    print(f"searches usadas:   {requests_used}")
    print(f"searches available: {requests_avail}")
    if requests_used is not None and requests_avail is not None:
        remaining = requests_avail - requests_used
        print(f"searches restantes: {remaining}")
    print(f"reset_date: {reset_date}")
    print("=" * 60)

    if requests_used is None or requests_avail is None:
        print("WARNING: Hunter no devolvió contadores claros. Inspecciona body raw:")
        print(body)
        return 1

    remaining = requests_avail - requests_used
    if remaining < 10:
        print(f"GATE: {remaining} < 10. PARAR antes del smoke.")
        return 3

    print(f"GATE OK: quedan {remaining} búsquedas, suficientes para 5 del smoke.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
