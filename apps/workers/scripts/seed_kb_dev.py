"""Replica los 6 kb_documents de prod a dev (UPSERT idempotente por id).

UNICA EXCEPCION donde un script de desarrollo lee de prod: los 6 docs
del KB son contenido de negocio (servicios, ICP, objeciones, etc.) que
Gonzalo cargo directamente en prod en la sesion 1. Replicarlos a dev
permite iterar el embedding y el retrieval sin tocar prod hasta que
estemos seguros del pipeline.

NO copia kb_chunks: los regenera embed_documents(env="dev") en B.
NO copia leads, mailboxes ni nada operativo: solo el KB.

Reentrante: ON CONFLICT (id) DO UPDATE — volver a ejecutarlo refresca
los docs en dev sin duplicar.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ENV", "dev")

WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from sqlalchemy import text  # noqa: E402

from shared.db import get_session  # noqa: E402

SELECT_PROD = text("""
    select id, category, titulo, contenido, is_active, created_by, created_at, updated_at
    from kb_documents
    order by category, titulo
""")

UPSERT_DEV = text("""
    insert into kb_documents
        (id, category, titulo, contenido, is_active, created_by, created_at, updated_at)
    values (:id, :category, :titulo, :contenido, :is_active, :created_by, :created_at, :updated_at)
    on conflict (id) do update set
        category   = excluded.category,
        titulo     = excluded.titulo,
        contenido  = excluded.contenido,
        is_active  = excluded.is_active,
        created_by = excluded.created_by,
        created_at = excluded.created_at
""")
# Nota: no se actualiza updated_at via UPSERT — el trigger
# kb_documents_updated_at lo pone a now() en cada UPDATE, lo cual basta
# para auditar cuando se sincronizo dev. La fuente de verdad del
# contenido sigue siendo prod.


def main() -> int:
    print("seed_kb_dev: replicando kb_documents prod -> dev")

    with get_session("dev") as s:
        before = s.execute(text("select count(*) from kb_documents")).scalar_one()
    print(f"  dev count antes:    {before}")

    with get_session("prod") as s:
        rows = [dict(r) for r in s.execute(SELECT_PROD).mappings().all()]
    print(f"  prod docs leidos:   {len(rows)}")

    with get_session("dev") as s:
        for row in rows:
            s.execute(UPSERT_DEV, row)

    with get_session("dev") as s:
        after = s.execute(text("select count(*) from kb_documents")).scalar_one()
        breakdown = s.execute(
            text("select category, count(*) from kb_documents group by category order by category")
        ).all()
    print(f"  dev count despues:  {after}")
    print(f"  dev breakdown:      {breakdown}")

    print("seed_kb_dev OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
