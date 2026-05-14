"""apply_migration_12.py -- aplicar migration 12 en dev y prod.

Lee infra/supabase/migrations/20260514120000_12_mailboxes_hitl_mode.sql
y la ejecuta en BD dev y BD prod usando shared.config + psycopg.
"""
import os
import sys
from pathlib import Path
from typing import Literal

import psycopg

from shared.config import load_settings

MIGRATION_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "infra"
    / "supabase"
    / "migrations"
    / "20260514120000_12_mailboxes_hitl_mode.sql"
)

EnvName = Literal["dev", "prod"]


def apply(env: EnvName) -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    os.environ["ENV"] = env
    s = load_settings(env)
    url = s.DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    print(f"=== {env} ===")
    print(f"URL prefix: {url[:50]}...")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print(f"[OK] migration 12 aplicada en {env}")

    # Verificacion: la columna existe + default true en filas existentes.
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "select id::text, email, hitl_mode from mailboxes order by email"
        )
        for row in cur.fetchall():
            print(f"  mailbox {row[1]}: hitl_mode={row[2]}")


def main() -> int:
    if not MIGRATION_PATH.exists():
        print(f"ERROR: migration no encontrada en {MIGRATION_PATH}")
        return 1
    for env in ("dev", "prod"):
        try:
            apply(env)  # type: ignore[arg-type]
        except Exception as e:
            print(f"FALLO en {env}: {type(e).__name__}: {e}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
