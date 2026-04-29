"""Verifica que las migrations están aplicadas correctamente al entorno indicado.

Checks (per spec del Bloque B7):
  1. Extensiones `pgcrypto` y `vector` instaladas.
  2. Las 12 tablas esperadas existen en `public` (companies, contacts, mailboxes,
     sequences, campaigns, messages, replies, events, jobs, kb_documents,
     kb_chunks, web_leads).
  3. Insert + select + delete funciona en `companies` (la conexión usa
     service_role que bypassa RLS — esto valida que el schema responde a
     CRUD básico con datos reales).
  4. RLS habilitado en las 12 tablas (chequeo estructural via `pg_class.relrowsecurity`).
  5. RLS funcional: con `set role anon`, `select count(*) from companies`
     debe devolver 0 filas o levantar `InsufficientPrivilege`.

Exit code 0 si todo pasa, 1 si algo falla.

Uso:
    cd apps/workers
    uv run python scripts/verify_migrations.py --env dev
    uv run python scripts/verify_migrations.py --env prod
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

EXPECTED_TABLES = {
    "companies",
    "contacts",
    "mailboxes",
    "sequences",
    "campaigns",
    "messages",
    "replies",
    "events",
    "jobs",
    "kb_documents",
    "kb_chunks",
    "web_leads",
}
EXPECTED_EXTENSIONS = {"pgcrypto", "vector"}


def load_env(env: str) -> str:
    env_file = WORKERS_DIR / f".env.{env}"
    if not env_file.is_file():
        sys.exit(f"ERROR: missing {env_file}.")
    load_dotenv(env_file, override=True)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not db_url or db_url.startswith("<"):
        sys.exit(f"ERROR: DATABASE_URL not configured in {env_file}.")
    return db_url


def check_extensions(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "select extname from pg_extension where extname = any(%s)",
            (list(EXPECTED_EXTENSIONS),),
        )
        found = {row[0] for row in cur.fetchall()}
    missing = EXPECTED_EXTENSIONS - found
    if missing:
        print(f"  FAIL extensions missing: {sorted(missing)}")
        return False
    print(f"  OK extensions: {sorted(found)}")
    return True


def check_tables(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_type = 'BASE TABLE'"
        )
        found = {row[0] for row in cur.fetchall()}
    missing = EXPECTED_TABLES - found
    extra = found - EXPECTED_TABLES - {"_migrations"}  # _migrations es esperado también
    if missing:
        print(f"  FAIL tables missing: {sorted(missing)}")
        return False
    if extra:
        print(f"  WARN unexpected tables (no bloqueantes): {sorted(extra)}")
    print(f"  OK all {len(EXPECTED_TABLES)} expected tables present")
    return True


def check_insert_select(conn: psycopg.Connection) -> bool:
    """Insert a probe row in companies, select it back, then delete it."""
    test_nif = "__VERIFY_PROBE__"
    try:
        with conn.cursor() as cur:
            cur.execute("delete from companies where nif = %s", (test_nif,))
            cur.execute(
                "insert into companies (nif, nombre, tier) "
                "values (%s, %s, %s) returning id",
                (test_nif, "Verify Probe Inc", "descartado"),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                print("  FAIL insert returning no id")
                return False
            probe_id = row[0]
            cur.execute("select nombre from companies where id = %s", (probe_id,))
            result = cur.fetchone()
            cur.execute("delete from companies where id = %s", (probe_id,))
        conn.commit()
        if result and result[0] == "Verify Probe Inc":
            print("  OK insert + select + delete on companies works")
            return True
        print(f"  FAIL unexpected select result: {result}")
        return False
    except Exception as e:
        conn.rollback()
        print(f"  FAIL insert/select error: {e}")
        return False


def check_rls_structural(conn: psycopg.Connection) -> bool:
    """Verify pg_class.relrowsecurity = true for all expected tables."""
    with conn.cursor() as cur:
        cur.execute(
            "select c.relname from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relrowsecurity = true"
        )
        rls_enabled = {row[0] for row in cur.fetchall()}
    missing = EXPECTED_TABLES - rls_enabled
    if missing:
        print(f"  FAIL RLS NOT enabled on: {sorted(missing)}")
        return False
    print(f"  OK RLS enabled on all {len(EXPECTED_TABLES)} expected tables")
    return True


def check_rls_functional(db_url: str) -> bool:
    """Open a fresh connection, SET ROLE anon, try SELECT — expect 0 rows or error."""
    try:
        with psycopg.connect(db_url, autocommit=True) as anon_conn:
            with anon_conn.cursor() as cur:
                cur.execute("set role anon")
                try:
                    cur.execute("select count(*) from companies")
                    count_row = cur.fetchone()
                    count = count_row[0] if count_row else None
                    if count == 0:
                        print("  OK anon SELECT returns 0 rows on companies (RLS blocking)")
                        return True
                    print(f"  FAIL anon SELECT returned {count} rows — RLS NOT blocking")
                    return False
                except psycopg.errors.InsufficientPrivilege:
                    print("  OK anon SELECT raised InsufficientPrivilege (RLS blocking)")
                    return True
    except Exception as e:
        print(f"  FAIL anon RLS functional check error: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Supabase migrations applied.")
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    args = parser.parse_args()

    db_url = load_env(args.env)

    print(f"[{args.env}] verifying migrations...")
    with psycopg.connect(db_url) as conn:
        results = [
            check_extensions(conn),
            check_tables(conn),
            check_insert_select(conn),
            check_rls_structural(conn),
        ]
    # Functional anon check uses its own connection (separate session for SET ROLE).
    results.append(check_rls_functional(db_url))

    if all(results):
        print(f"[{args.env}] all checks passed.")
        return 0
    print(f"[{args.env}] some checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
