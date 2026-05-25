"""Bloque 5.2 sesion 2026-05-25 -- cancela los 8 drafts viejos en prod.

7 reframes pendientes (drafted, step=1, angle=reframe, cadencia agresiva D+4
del seed migration 11) -> cancelled con evento motivo "regenerar con prompts
v2026-05-25 + cadencia D+14". Con migration 13 ya aplicada (D+0/D+14/D+28)
y follow_ups.py modificado para excluir status='cancelled' del NOT EXISTS,
estos contacts regeneraran reframe automaticamente cuando llegue su D+14
desde el opening (entre 28-may y 02-jun segun cuando se envio el opening
original).

1 closing pendiente para Jaime Nozaleda (LENA, step=2, angle=closing, asunto
"Ultimo correo de mi parte") -> cancelled con evento motivo "tono
pasivo-agresivo + email remitente alucinado". NO regenerar. Jaime queda
marcado is_primary=false + evento contact_cooling con until=2026-06-25 para
trazabilidad. PM debe re-evaluar manualmente esa fecha (tarea humana
pendiente reportada).

Idempotente: solo cancela drafts que ESTAN en status='drafted' al momento
de ejecucion. Si re-ejecutas, los segundos UPDATE matchean 0 filas. Los
eventos no se duplican porque el WHERE m.status='drafted' es la guarda.

Uso:
    cd apps/workers
    PYTHONPATH=. uv run python scripts/cancel_drafts_2026_05_25.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("ENV", "prod")

import psycopg

from shared.config import load_settings


REASON_REFRAMES = (
    "regenerar con prompts v2026-05-25 + cadencia D+14 "
    "(migration 13 + Lecciones 39/41/42 sesion 2026-05-25)"
)
REASON_JAIME_CLOSING = (
    "tono pasivo-agresivo + email remitente alucinado en cuerpo "
    "(Lecciones 40+42 sesion 2026-05-25)"
)
JAIME_COOLING_UNTIL = "2026-06-25"
JAIME_COOLING_REASON = (
    "Lena Construcciones / Jaime Nozaleda recibio opening D+0 + reframe D+5 "
    "(cadencia agresiva pre-migration 13) + draft closing con tono "
    "pasivo-agresivo y email remitente alucinado. Dejar enfriar 30+ dias "
    "para no quemar relacion antes de proximo intento, ya con prompts v2."
)


def main() -> int:
    s = load_settings("prod")
    url = s.DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        # ── 1. Cancelar los 7 reframes pendientes ──────────────────────────
        cur.execute(
            """
            select m.id, m.contact_id, ct.email, co.nombre as empresa
            from messages m
            join contacts ct on ct.id = m.contact_id
            join companies co on co.id = ct.company_id
            where m.status = 'drafted'
              and m.step_index = 1
              and m.angle = 'reframe'
            """
        )
        reframes = cur.fetchall()
        print(f"Reframes drafted a cancelar: {len(reframes)}")
        for r in reframes:
            print(f"  msg_id={r[0]}  contact={r[2]}  empresa={r[3]}")

        if reframes:
            cur.execute(
                """
                update messages
                set status = 'cancelled'
                where id = any(%s)
                """,
                ([r[0] for r in reframes],),
            )
            print(f"  -> UPDATE messages SET status='cancelled' rows={cur.rowcount}")
            for r in reframes:
                cur.execute(
                    """
                    insert into events (type, message_id, contact_id, payload)
                    values ('message_cancelled', %s, %s, %s::jsonb)
                    """,
                    (
                        r[0],
                        r[1],
                        '{"reason": "%s", "source": "cancel_drafts_2026_05_25"}'
                        % REASON_REFRAMES,
                    ),
                )

        # ── 2. Cancelar el closing pendiente de Jaime Nozaleda (LENA) ──────
        cur.execute(
            """
            select m.id, m.contact_id, ct.email, co.nombre as empresa
            from messages m
            join contacts ct on ct.id = m.contact_id
            join companies co on co.id = ct.company_id
            where m.status = 'drafted'
              and m.step_index = 2
              and m.angle = 'closing'
              and ct.email ilike '%nozaleda%'
            """
        )
        closings_jaime = cur.fetchall()
        print(f"\nClosing drafted Jaime/Lena a cancelar: {len(closings_jaime)}")
        for r in closings_jaime:
            print(f"  msg_id={r[0]}  contact={r[2]}  empresa={r[3]}")

        if closings_jaime:
            cur.execute(
                """
                update messages
                set status = 'cancelled'
                where id = any(%s)
                """,
                ([r[0] for r in closings_jaime],),
            )
            print(f"  -> UPDATE messages SET status='cancelled' rows={cur.rowcount}")
            for r in closings_jaime:
                cur.execute(
                    """
                    insert into events (type, message_id, contact_id, payload)
                    values ('message_cancelled', %s, %s, %s::jsonb)
                    """,
                    (
                        r[0],
                        r[1],
                        '{"reason": "%s", "source": "cancel_drafts_2026_05_25"}'
                        % REASON_JAIME_CLOSING,
                    ),
                )

        # ── 3. Enfriar Jaime: is_primary=false + evento contact_cooling ────
        cur.execute(
            """
            select id, email, is_primary
            from contacts
            where email ilike '%nozaleda%'
            """
        )
        jaime_rows = cur.fetchall()
        print(f"\nContact(s) Jaime a enfriar: {len(jaime_rows)}")
        for r in jaime_rows:
            print(f"  id={r[0]}  email={r[1]}  is_primary={r[2]}")

        for r in jaime_rows:
            contact_id = r[0]
            if r[2]:  # solo flip si esta is_primary=true
                cur.execute(
                    """
                    update contacts
                    set is_primary = false
                    where id = %s
                    """,
                    (contact_id,),
                )
                print(f"  -> contacts.is_primary -> false (rows={cur.rowcount})")
            cur.execute(
                """
                insert into events (type, contact_id, payload)
                values ('contact_cooling', %s, %s::jsonb)
                """,
                (
                    contact_id,
                    '{"until": "%s", "reason": "%s", "source": '
                    '"cancel_drafts_2026_05_25"}'
                    % (JAIME_COOLING_UNTIL, JAIME_COOLING_REASON),
                ),
            )

        # ── 4. Verificar estado final antes de commit ──────────────────────
        cur.execute("select status, count(*) from messages group by status order by 1")
        print("\nEstado final messages.status:")
        for r in cur.fetchall():
            print(f"  {r[0]:15s} {r[1]}")

        conn.commit()
        print("\nCommit OK.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
