"""Deja en la Approval Queue SOLO los drafts con email verificado.

1. RESCATE: reintenta Hunter email-verifier sobre los drafts cuyo contacto
   sigue email_verified=false (rescata errores transitorios de la 1a pasada).
     - deliverable -> email_verified=true (sobrevive)
     - undeliverable -> cancela el draft
2. PRUNE: cancela todo draft cuyo contacto siga email_verified=false
   (risky/catch-all/error no rescatado), con _cancelled_reason='no_verificado_prune'.

Resultado: status='drafted' == solo contactos email_verified=true.

Uso (en apps/workers):  ENV=prod uv run python -m scripts.prune_to_verified
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("ENV", "prod")

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from shared.config import settings  # noqa: E402
from shared.db import get_session  # noqa: E402

API = "https://api.hunter.io/v2/email-verifier"


def verify_one(email: str, client: httpx.Client) -> str:
    try:
        r = client.get(API, params={"email": email, "api_key": settings.HUNTER_API_KEY})
        if r.status_code != 200:
            return "error"
        return str(r.json().get("data", {}).get("result"))
    except Exception as e:  # noqa: BLE001
        return f"error:{type(e).__name__}"


def main() -> None:
    with get_session("prod") as s:
        rows = s.execute(text(
            """
            select m.id as msg_id, ct.id as cid, ct.email
            from messages m join contacts ct on ct.id = m.contact_id
            where m.status = 'drafted' and ct.email_verified = false
            """
        )).mappings().all()
        print(f"[rescate] reintentando {len(rows)} no verificados...")
        rescued = killed = 0
        with httpx.Client(timeout=30.0) as client:
            for r in rows:
                result = verify_one(r["email"], client)
                if result == "deliverable":
                    s.execute(text("update contacts set email_verified=true where id=cast(:i as uuid)"), {"i": r["cid"]})
                    rescued += 1
                    print(f"  RESCATADO -> {r['email']}")
                elif result == "undeliverable":
                    s.execute(text(
                        "update messages set status='cancelled', "
                        "research_snapshot=coalesce(research_snapshot,'{}'::jsonb)"
                        "||jsonb_build_object('_cancelled_reason','hunter_undeliverable') "
                        "where id=cast(:i as uuid)"
                    ), {"i": r["msg_id"]})
                    killed += 1
                time.sleep(0.15)

        pruned = s.execute(text(
            """
            update messages set status='cancelled',
              research_snapshot=coalesce(research_snapshot,'{}'::jsonb)
              ||jsonb_build_object('_cancelled_reason','no_verificado_prune')
            where status='drafted'
              and contact_id in (select id from contacts where email_verified=false)
            """
        ))

        print(f"\n[rescate] rescatados deliverable: {rescued} | undeliverable cancelados: {killed}")
        print(f"[prune] drafts cancelados por no verificados: {pruned.rowcount}")
        rem = s.execute(text("select count(*) from messages where status='drafted'")).scalar()
        ver = s.execute(text(
            "select count(*) from messages m join contacts ct on ct.id=m.contact_id "
            "where m.status='drafted' and ct.email_verified=true"
        )).scalar()
        print(f"\n== COLA FINAL: {rem} drafts (verificados: {ver}) ==")


if __name__ == "__main__":
    main()
