"""Verifica via Hunter email-verifier (HTTPS) los emails de los drafts en cola.

El VPS tiene el puerto 25 saliente bloqueado (envia por Gmail API), asi que
smtp_probe no sirve aqui. Hunter verifier funciona por HTTPS.

Por cada contacto con message status='drafted':
  - result='deliverable' -> contacts.email_verified=true
  - result='undeliverable' -> cancela el draft (rebote garantizado),
    research_snapshot._cancelled_reason='hunter_undeliverable'
  - result='risky'/unknown/error -> se deja en cola sin verificar (criterio humano)

Consume 1 verification de Hunter por email (cuota 'verifications', no 'searches').
Idempotente: re-ejecutar reescribe los mismos flags.

Uso (en apps/workers):
    ENV=prod uv run python -m scripts.verify_drafts_hunter
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


def verify_one(email: str, client: httpx.Client) -> tuple[str, str, object]:
    try:
        r = client.get(API, params={"email": email, "api_key": settings.HUNTER_API_KEY})
        if r.status_code != 200:
            return ("error", f"http_{r.status_code}", None)
        d = r.json().get("data", {})
        return (str(d.get("result")), str(d.get("status")), d.get("score"))
    except Exception as e:  # noqa: BLE001
        return ("error", f"{type(e).__name__}:{e}"[:60], None)


def main() -> None:
    with get_session("prod") as s:
        rows = s.execute(text(
            """
            select m.id as msg_id, ct.id as contact_id, ct.email, co.nombre
            from messages m
            join contacts ct on ct.id = m.contact_id
            join companies co on co.id = ct.company_id
            where m.status = 'drafted'
            order by co.nombre
            """
        )).mappings().all()

        print(f"verificando {len(rows)} emails via Hunter email-verifier...\n")
        counts: dict[str, int] = {}
        deliverable = undeliverable = risky = 0

        with httpx.Client(timeout=30.0) as client:
            for r in rows:
                result, status, score = verify_one(r["email"], client)
                counts[result] = counts.get(result, 0) + 1
                print(f"  {r['email']:<42} -> {result:<13} ({status}, score={score})")

                if result == "deliverable":
                    s.execute(
                        text("update contacts set email_verified=true where id=cast(:i as uuid)"),
                        {"i": r["contact_id"]},
                    )
                    deliverable += 1
                elif result == "undeliverable":
                    s.execute(
                        text(
                            "update messages set status='cancelled', "
                            "research_snapshot = coalesce(research_snapshot,'{}'::jsonb) "
                            "|| jsonb_build_object('_cancelled_reason','hunter_undeliverable') "
                            "where id=cast(:i as uuid)"
                        ),
                        {"i": r["msg_id"]},
                    )
                    undeliverable += 1
                else:
                    risky += 1
                time.sleep(0.15)

        print("\n=== RESUMEN ===")
        print("por result:", counts)
        print(f"deliverable (email_verified=true):     {deliverable}")
        print(f"undeliverable (drafts CANCELADOS):     {undeliverable}")
        print(f"risky/unknown/error (en cola, revisar): {risky}")
        rem = s.execute(text("select count(*) from messages where status='drafted'")).scalar()
        print("drafts en cola tras verificacion:", rem)


if __name__ == "__main__":
    main()
