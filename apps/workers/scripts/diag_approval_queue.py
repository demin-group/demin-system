"""Diagnostico: por que esta vacia la Approval Queue.

Recorre el embudo completo (companies -> contacts -> messages) e imprime
conteos agregados. NO imprime datos personales ni credenciales: solo numeros
de estado.

Uso:
    ENV=dev  uv run python scripts/diag_approval_queue.py
    ENV=prod uv run python scripts/diag_approval_queue.py   (si existe ese env)
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Permite importar el paquete shared cuando se corre desde apps/workers/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV = os.environ.get("ENV", "dev")
# Override: si se pasa DIRECT_DATABASE_URL, se ignora el fichero de entorno y
# se conecta directo a esa URL (util para apuntar a prod sin crear el fichero
# de entorno local). Acepta postgres:// | postgresql:// | postgresql+psycopg://.
DIRECT_URL = os.environ.get("DIRECT_DATABASE_URL")


@contextmanager
def open_session():
    if DIRECT_URL:
        url = DIRECT_URL
        for pref in ("postgres://", "postgresql://"):
            if url.startswith(pref) and not url.startswith("postgresql+psycopg://"):
                url = "postgresql+psycopg://" + url[len(pref):]
                break
        eng = create_engine(url, pool_pre_ping=True, future=True)
        sm = sessionmaker(bind=eng, future=True)
        sess = sm()
        try:
            yield sess
        finally:
            sess.close()
            eng.dispose()
    else:
        from shared.db import get_session  # import perezoso: carga el env-file
        with get_session(ENV) as sess:  # type: ignore[arg-type]
            yield sess


def rows(session, sql: str):
    return session.execute(text(sql)).fetchall()


def main() -> None:
    target = "DIRECT_DATABASE_URL" if DIRECT_URL else f"ENV={ENV}"
    print(f"=== DIAGNOSTICO APPROVAL QUEUE — {target} ===\n")
    with open_session() as s:
        # 0. Identidad de la BD (sin secretos): host + nombre.
        ident = rows(
            s,
            "select current_database() as db, "
            "inet_server_addr()::text as host, "
            "current_setting('server_version') as pgver",
        )
        print("BD:", dict(ident[0]._mapping))

        # 1. COMPANIES
        print("\n--- companies ---")
        total_co = rows(s, "select count(*) c from companies")[0].c
        print(f"total: {total_co}")
        for label, sql in [
            ("por tier", "select coalesce(tier,'<null>') k, count(*) c from companies group by 1 order by 2 desc"),
            ("por ia_fit", "select coalesce(ia_fit,'<null>') k, count(*) c from companies group by 1 order by 2 desc"),
        ]:
            print(f"  {label}:")
            for r in rows(s, sql):
                print(f"    {r.k:>14}: {r.c}")

        # 2. CONTACTS
        print("\n--- contacts ---")
        total_ct = rows(s, "select count(*) c from contacts")[0].c
        opt = rows(s, "select count(*) c from contacts where is_optout")[0].c
        ver = rows(s, "select count(*) c from contacts where email_verified")[0].c
        print(f"total: {total_ct}  | opt-out: {opt}  | email_verified: {ver}")

        # 3. MESSAGES por estado
        print("\n--- messages por status ---")
        msg = rows(
            s,
            "select status, count(*) c from messages group by 1 order by 2 desc",
        )
        if not msg:
            print("  (CERO mensajes en la tabla)")
        for r in msg:
            flag = "   <-- ESTO es lo que muestra la Approval Queue" if r.status == "drafted" else ""
            print(f"    {r.status:>12}: {r.c}{flag}")

        # 4. MAILBOXES / modo HITL
        print("\n--- mailboxes (hitl_mode / status) ---")
        try:
            mb = rows(
                s,
                "select email, status, "
                "coalesce(hitl_mode::text,'<col?>') as hitl from mailboxes order by email",
            )
            if not mb:
                print("  (sin mailboxes configurados)")
            for r in mb:
                print(f"    {r.email} | status={r.status} | hitl_mode={r.hitl}")
        except Exception as e:  # columna puede no existir segun migracion aplicada
            print(f"  (no se pudo leer mailboxes.hitl_mode: {e})")

        # 5. SEQUENCES (cadencia activa)
        print("\n--- sequences (cadencia) ---")
        try:
            seq = rows(s, "select code, jsonb_array_length(steps) n_steps from sequences order by code")
            for r in seq:
                print(f"    {r.code}: {r.n_steps} pasos")
        except Exception as e:
            print(f"  (no se pudo leer sequences: {e})")

    print("\n=== fin ===")


if __name__ == "__main__":
    main()
