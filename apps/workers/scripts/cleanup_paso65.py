"""Cleanup paso 6.5 — cancela messages pre-envío cuyo contact NO es is_primary.

Tras el fix del bug de envío simultáneo (paso 6.5 — `fetch_pending_contacts`
ahora filtra por `is_primary=true`), los messages ya generados que
pertenecían a contacts no-primary tienen que cancelarse explícitamente
para que NO entren al envío real del paso 7.

Estados pre-envío que el cleanup ataca:
- `drafted`: drafts pendientes de aprobar.
- `approved`: drafts ya aprobados por humano. **Confirmación PM**: las
  aprobaciones humanas del paso 6 fueron de calidad de prosa, no de
  coherencia operativa — el bug de envío múltiple se detectó DESPUÉS
  de aprobar. Las 4 aprobaciones se preservan en event trail con
  status='cancelled' + razón 'paso65_fix_solo_primary'.

NO toca:
- `scheduled` / `sent` / `bounced` / `failed`: no aplica en paso 6
  (envío real arranca en paso 7); si llega a aplicar en futuro, decisión
  separada.
- contacts: no opt-out, no delete — los no-primary siguen en BD como
  respaldo manual visible en /pipeline/[id].

Idempotente: corre dos veces y la segunda vez no afecta nada (no quedan
drafts/approved no-primary tras la primera).
"""
from __future__ import annotations

import argparse
import sys
from typing import Literal

from sqlalchemy import text

from shared.db import get_session

EnvName = Literal["dev", "prod"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="Solo muestra qué se cancelaría, sin modificar BD.")
    args = p.parse_args(argv)
    env: EnvName = args.env

    with get_session(env) as s:
        rows = s.execute(
            text(
                """
                SELECT m.id, m.status AS prev_status, m.subject, ct.email,
                       ct.is_primary, c.nif, c.nombre AS company_nombre
                FROM messages m
                JOIN contacts ct ON ct.id = m.contact_id
                JOIN companies c ON c.id = ct.company_id
                WHERE m.status IN ('drafted', 'approved')
                  AND ct.is_primary = false
                ORDER BY c.nif, ct.email_priority
                """
            )
        ).mappings().all()

    print("=" * 76)
    print(f"cleanup_paso65  env={env}  dry_run={args.dry_run}")
    print("=" * 76)
    if not rows:
        print("No hay messages pre-envío no-primary. Nada que cancelar.")
        return 0

    print(f"{len(rows)} messages a cancelar:")
    for r in rows:
        print(
            f"  {r['nif']} {r['company_nombre'][:30]:<30}  "
            f"{r['email']:<40}  prev_status={r['prev_status']:<10}  msg={str(r['id'])[:8]}"
        )
    print()

    if args.dry_run:
        print("(dry-run — no se modifica nada)")
        return 0

    payload = [{"id": str(r["id"]), "prev": r["prev_status"]} for r in rows]
    with get_session(env) as s:
        for p in payload:
            # Guardamos el status anterior además de la razón para que el
            # event trail conserve si fue cancelado desde drafted o approved.
            s.execute(
                text(
                    """
                    UPDATE messages
                    SET status='cancelled',
                        research_snapshot = jsonb_set(
                            jsonb_set(
                                coalesce(research_snapshot, '{}'::jsonb),
                                '{_cancelled_reason}',
                                to_jsonb('paso65_fix_solo_primary'::text)
                            ),
                            '{_cancelled_from_status}',
                            to_jsonb(cast(:prev as text))
                        )
                    WHERE id = cast(:id as uuid)
                    """
                ),
                p,
            )
    print(
        f"OK — {len(payload)} messages cancelados con "
        f"_cancelled_reason='paso65_fix_solo_primary' "
        f"+ _cancelled_from_status preservado"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
