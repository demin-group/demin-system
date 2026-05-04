"""Carga one-shot del KB v1 desde la sesión 1 con Gonzalo (2026-04-29).

Lee los 6 markdown de `apps/workers/kb/seed_v1/` y los inserta uno a uno
en `kb_documents` de Supabase, con `created_by = 'kb_session_1_2026_04_29'`.

NO genera embeddings ni encola jobs. La generación de `kb_chunks` queda
diferida a Fase 1, cuando se construya el worker `embed_documents.py`
(cliente Voyage `voyage-multilingual-2`, chunking ~500 tokens overlap 50).

Salvaguardas:

- Antes del primer INSERT verifica que `kb_documents` y `kb_chunks` están
  vacíos en el entorno indicado. Si hay filas previas, sale con error.
- Inserta uno a uno, con logging por documento. Si falla uno, aborta y
  reporta. La carga es atómica: o entran los 6, o ninguno.
- Tras la carga, verifica recuento (=6 docs, 0 chunks) y lista los 6 con
  (category, titulo, length(contenido)) para auditoría humana.

Uso:
    cd apps/workers
    uv run python scripts/load_kb_session_1.py --env prod
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
SEED_DIR = WORKERS_DIR / "kb" / "seed_v1"

CREATED_BY = "kb_session_1_2026_04_29"

# Mapeo (filename, category, titulo) — el orden define el orden de inserción.
# Filename relativo a SEED_DIR. Category debe estar en el CHECK de la migración
# 04_kb.sql. Titulo se toma del frontmatter del prompt original de carga.
DOCS = [
    (
        "servicios.md",
        "servicios",
        "Servicios — qué hace y qué no hace DEMIN",
    ),
    (
        "icp.md",
        "icp",
        "Cliente ideal — quiénes son los buenos y a quién no escribir",
    ),
    (
        "objeciones.md",
        "objeciones",
        "Objeciones reales y cómo las trabaja Gonzalo",
    ),
    (
        "casos_exito.md",
        "casos_exito",
        "Casos reales de DEMIN — material para correos y web (con permisos)",
    ),
    (
        "tono.md",
        "tono",
        "Tono de Gonzalo — cómo escribe y cómo NO escribe",
    ),
    (
        "diferenciador.md",
        "diferenciador",
        'Por qué DEMIN — el ángulo "pequeños y a vuestro favor", desarrollado',
    ),
]


def load_env(env: str) -> str:
    env_file = WORKERS_DIR / f".env.{env}"
    if not env_file.is_file():
        sys.exit(f"ERROR: missing {env_file}.")
    load_dotenv(env_file, override=True)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not db_url or db_url.startswith("<"):
        sys.exit(f"ERROR: DATABASE_URL not configured in {env_file}.")
    return db_url


def read_doc(filename: str) -> str:
    path = SEED_DIR / filename
    if not path.is_file():
        sys.exit(f"ERROR: missing seed file {path}.")
    return path.read_text(encoding="utf-8")


def assert_empty(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("select count(*) from kb_documents")
        n_docs = cur.fetchone()[0]
        cur.execute("select count(*) from kb_chunks")
        n_chunks = cur.fetchone()[0]
    if n_docs or n_chunks:
        sys.exit(
            f"ERROR: KB tables not empty (kb_documents={n_docs}, "
            f"kb_chunks={n_chunks}). Aborting to avoid duplicates."
        )
    print(f"  Pre-check: kb_documents=0, kb_chunks=0. OK.")


def insert_one(
    conn: psycopg.Connection, category: str, titulo: str, contenido: str
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into kb_documents (category, titulo, contenido, is_active, created_by)
            values (%s, %s, %s, true, %s)
            returning id, length(contenido)
            """,
            (category, titulo, contenido, CREATED_BY),
        )
        row = cur.fetchone()
    return f"id={row[0]} stored_length={row[1]}"


def list_loaded(conn: psycopg.Connection) -> list[tuple[str, str, int]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select category, titulo, length(contenido)
            from kb_documents
            where created_by = %s
            order by category
            """,
            (CREATED_BY,),
        )
        return cur.fetchall()


def count_chunks_for_loaded(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*) from kb_chunks
            where document_id in (
              select id from kb_documents where created_by = %s
            )
            """,
            (CREATED_BY,),
        )
        return cur.fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    args = parser.parse_args()

    print(f"[load_kb_session_1] env={args.env}")
    db_url = load_env(args.env)

    print(f"[load_kb_session_1] connecting to Supabase ({args.env})...")
    with psycopg.connect(db_url) as conn:
        # Manual transaction control: queremos atomicidad de los 6 INSERTs.
        conn.autocommit = False
        try:
            assert_empty(conn)

            print(f"[load_kb_session_1] inserting {len(DOCS)} documents...")
            for i, (filename, category, titulo) in enumerate(DOCS, start=1):
                contenido = read_doc(filename)
                file_size = len(contenido)
                info = insert_one(conn, category, titulo, contenido)
                print(
                    f"  [{i}/{len(DOCS)}] {category:15s} "
                    f"file_size={file_size:5d}  inserted: {info}"
                )

            conn.commit()
            print("[load_kb_session_1] commit OK.")

            print("[load_kb_session_1] verification:")
            rows = list_loaded(conn)
            assert len(rows) == len(DOCS), (
                f"expected {len(DOCS)} rows, got {len(rows)}"
            )
            for category, titulo, length_ in rows:
                print(f"  {category:15s} length={length_:5d}  '{titulo}'")

            n_chunks = count_chunks_for_loaded(conn)
            assert n_chunks == 0, f"unexpected chunks: {n_chunks}"
            print(f"  kb_chunks for this load: {n_chunks} (expected 0).")

        except Exception as exc:
            conn.rollback()
            print(f"[load_kb_session_1] ROLLBACK due to: {exc}", file=sys.stderr)
            raise

    print("[load_kb_session_1] done.")


if __name__ == "__main__":
    main()
