"""Aplica migrations SQL al proyecto Supabase del entorno indicado.

Lee `apps/workers/.env.{dev|prod}` (gitignored) para obtener `DATABASE_URL`
y aplica todos los `.sql` de `infra/supabase/migrations/` en orden lexicográfico.
Cada fichero corre en su propia transacción; falla rápido si error y deja la BD
en estado consistente. Las migraciones aplicadas se registran en la tabla
`_migrations` para que rerun sea idempotente (skip de las ya aplicadas).

Safety check: con `--env prod` el script pide confirmación interactiva y
SOLO procede si se teclea exactamente `yes` (case-sensitive, sin espacios).
Cualquier otra entrada — incluido `y`, `YES`, enter vacío o EOF — aborta sin
tocar la BD. `--env dev` ejecuta sin prompt.

Uso:
    cd apps/workers
    uv run python scripts/apply_migrations.py --env dev
    uv run python scripts/apply_migrations.py --env prod
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
WORKERS_DIR = SCRIPT_DIR.parent
ROOT_DIR = WORKERS_DIR.parent.parent
MIGRATIONS_DIR = ROOT_DIR / "infra" / "supabase" / "migrations"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply SQL migrations to Supabase.")
    parser.add_argument(
        "--env",
        choices=["dev", "prod"],
        required=True,
        help="Target environment: dev or prod.",
    )
    return parser.parse_args()


def load_env(env: str) -> str:
    env_file = WORKERS_DIR / f".env.{env}"
    if not env_file.is_file():
        sys.exit(
            f"ERROR: missing {env_file}. Copy .env.example to .env.{env} and fill it."
        )
    load_dotenv(env_file, override=True)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not db_url:
        sys.exit(f"ERROR: DATABASE_URL not set in {env_file}.")
    if db_url.startswith("<"):
        sys.exit(
            f"ERROR: DATABASE_URL in {env_file} still has placeholder <...>. Fill it."
        )
    return db_url


def list_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def ensure_migrations_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists _migrations (
                filename   text primary key,
                applied_at timestamptz not null default now()
            );
            """
        )
    conn.commit()


def list_applied(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("select filename from _migrations")
        return {row[0] for row in cur.fetchall()}


def confirm_prod(pending_count: int) -> None:
    """Block until user types exactly 'yes', otherwise abort."""
    print(
        f"About to apply {pending_count} migrations to PRODUCTION (demin-prod).",
        flush=True,
    )
    print("Type 'yes' to continue, anything else aborts: ", end="", flush=True)
    try:
        response = input()
    except EOFError:
        response = ""
    if response != "yes":
        print(f"Aborted (got {response!r}).")
        sys.exit(1)


def apply_one(conn: psycopg.Connection, path: Path) -> None:
    """Run the migration file and record it in _migrations atomically."""
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "insert into _migrations (filename) values (%s)",
            (path.name,),
        )
    conn.commit()


def main() -> int:
    args = parse_args()
    db_url = load_env(args.env)

    files = list_migration_files()
    if not files:
        print(f"No .sql files in {MIGRATIONS_DIR}.")
        return 0

    print(f"[{args.env}] connecting to database...")
    with psycopg.connect(db_url, autocommit=False) as conn:
        ensure_migrations_table(conn)
        applied = list_applied(conn)
        pending = [f for f in files if f.name not in applied]

        if not pending:
            print(
                f"[{args.env}] all {len(files)} migrations already applied. Nothing to do."
            )
            return 0

        if args.env == "prod":
            confirm_prod(len(pending))

        print(f"[{args.env}] {len(pending)} pending of {len(files)} total.")
        for path in pending:
            print(f"[{args.env}] applying {path.name} ...")
            try:
                apply_one(conn, path)
                print(f"[{args.env}] OK {path.name}")
            except Exception as e:
                conn.rollback()
                print(f"[{args.env}] FAIL {path.name}: {e}", file=sys.stderr)
                return 1

        print(f"[{args.env}] all {len(pending)} migrations applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
