"""Pipeline de embeddings del Knowledge Base (Fase 1, Sprint 1 paso 2).

API: ``embed_documents(env, document_ids=None, reembed=False) -> dict``

Modos:
- ``document_ids=None``: procesa todos los docs activos sin chunks
  (NOT EXISTS contra ``kb_chunks``).
- ``document_ids=[...]`` con ``reembed=False``: procesa los indicados;
  si alguno ya tiene chunks, lo loguea como skip y continua con el resto.
- ``document_ids=[...]`` con ``reembed=True``: borra chunks existentes
  de esos docs y vuelve a embedearlos.

Pipeline por doc: chunkea por chars (~2000 con overlap 200, respeta cierres
de parrafo \\n\\n hasta 300 chars antes del corte), embeda en batches de 32
con Voyage ``voyage-multilingual-2``, inserta filas en ``kb_chunks``
(``embedding`` casteada a ``vector`` desde literal ``[v1,v2,...]``).

Devuelve ``{"env","n_docs","n_chunks","elapsed_ms","skipped"}``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text

from shared.db import get_session
from shared.llm import embed

logger = logging.getLogger("demin.kb.embed")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

EnvName = Literal["prod", "dev"]

# Decisiones cerradas (ver prompt Sprint 1 paso 2 + plan §7.2):
CHUNK_CHARS = 2000
CHUNK_OVERLAP = 200
PARAGRAPH_LOOKBACK = 300
EMBED_BATCH = 32

# Voyage free tier sin payment method = 3 RPM (1 request cada 20s). Un sleep
# deliberado entre batches y otro inicial defensivo cubren tanto el ritmo
# normal como la posible ventana abierta de una ejecucion anterior. Los
# retries de tenacity en shared/llm.py (1+2+4 = 7s) absorben spikes pequenos.
# Si en el futuro se anade payment method en Voyage, ambas constantes a 0.
INTER_BATCH_SLEEP_S = 30
INITIAL_WARMUP_SLEEP_S = 25


def chunk_text(s: str) -> list[str]:
    """Trocea ``s`` en chunks de ~CHUNK_CHARS con overlap CHUNK_OVERLAP.

    Si el corte cae dentro de un parrafo y existe un ``\\n\\n`` en los
    PARAGRAPH_LOOKBACK chars previos, corta ahi para no partir parrafos.
    Texto vacio devuelve lista vacia; texto mas corto que CHUNK_CHARS se
    devuelve como un unico chunk.
    """
    s = s.strip()
    if not s:
        return []
    if len(s) <= CHUNK_CHARS:
        return [s]

    chunks: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        end = min(i + CHUNK_CHARS, n)
        if end < n:
            window_start = max(end - PARAGRAPH_LOOKBACK, i)
            window = s[window_start:end]
            idx = window.rfind("\n\n")
            if idx >= 0:
                end = window_start + idx
        chunk = s[i:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        next_i = end - CHUNK_OVERLAP
        i = next_i if next_i > i else end  # garantiza progreso
    return chunks


def _vector_literal(vec: list[float]) -> str:
    """pgvector acepta el literal '[v1,v2,...]' con cast '::vector'."""
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


def embed_documents(
    env: EnvName,
    document_ids: list[UUID] | None = None,
    reembed: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    skipped: list[str] = []

    # 1. Seleccionar docs a procesar.
    with get_session(env) as s:
        if document_ids is None:
            rows = [
                dict(r)
                for r in s.execute(
                    text(
                        """
                        select d.id, d.category, d.titulo, d.contenido
                        from kb_documents d
                        where d.is_active = true
                          and not exists (
                              select 1 from kb_chunks c where c.document_id = d.id
                          )
                        order by d.category, d.titulo
                        """
                    )
                ).mappings().all()
            ]
        else:
            ids_param = [str(i) for i in document_ids]
            rows = [
                dict(r)
                for r in s.execute(
                    text(
                        """
                        select id, category, titulo, contenido
                        from kb_documents
                        where id = any(:ids) and is_active = true
                        order by category, titulo
                        """
                    ),
                    {"ids": ids_param},
                ).mappings().all()
            ]
            if reembed:
                s.execute(
                    text("delete from kb_chunks where document_id = any(:ids)"),
                    {"ids": ids_param},
                )
            else:
                already = {
                    str(r[0])
                    for r in s.execute(
                        text(
                            "select distinct document_id from kb_chunks "
                            "where document_id = any(:ids)"
                        ),
                        {"ids": ids_param},
                    ).all()
                }
                kept = []
                for r in rows:
                    if str(r["id"]) in already:
                        logger.warning(
                            "embed_documents skip doc_id=%s titulo=%r (ya embebido, "
                            "reembed=False)",
                            r["id"],
                            r["titulo"],
                        )
                        skipped.append(str(r["id"]))
                        continue
                    kept.append(r)
                rows = kept

    # 2. Por cada doc: chunk, embed, insert.
    n_docs = 0
    n_chunks_total = 0

    if rows and INITIAL_WARMUP_SLEEP_S > 0:
        logger.info(
            "embed_documents warmup sleep %ds (Voyage free tier 3 RPM)",
            INITIAL_WARMUP_SLEEP_S,
        )
        time.sleep(INITIAL_WARMUP_SLEEP_S)

    for r in rows:
        doc_id = r["id"]
        titulo = r["titulo"]
        contenido = r["contenido"]
        doc_started = time.monotonic()

        chunks = chunk_text(contenido)
        if not chunks:
            logger.warning("embed_documents doc_id=%s sin contenido, skip", doc_id)
            continue

        vectors: list[list[float]] = []
        for k in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[k : k + EMBED_BATCH]
            if vectors or n_docs > 0:
                # Sleep entre batches (no antes del primero, ya cubierto por
                # el warmup inicial al entrar en el loop).
                time.sleep(INTER_BATCH_SLEEP_S)
            vectors.extend(embed(batch))

        with get_session(env) as s:
            for idx, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True)):
                s.execute(
                    text(
                        """
                        insert into kb_chunks
                            (document_id, chunk_index, contenido, embedding)
                        values
                            (:document_id, :chunk_index, :contenido,
                             cast(:embedding as vector))
                        """
                    ),
                    {
                        "document_id": str(doc_id),
                        "chunk_index": idx,
                        "contenido": chunk,
                        "embedding": _vector_literal(vec),
                    },
                )

        elapsed_ms = int((time.monotonic() - doc_started) * 1000)
        logger.info(
            "embed_documents doc_id=%s titulo=%r n_chunks=%d elapsed_ms=%d",
            doc_id,
            titulo,
            len(chunks),
            elapsed_ms,
        )
        n_docs += 1
        n_chunks_total += len(chunks)

    return {
        "env": env,
        "n_docs": n_docs,
        "n_chunks": n_chunks_total,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "skipped": skipped,
    }


if __name__ == "__main__":
    import os
    import sys

    target_env: EnvName = os.environ.get("ENV", "dev")  # type: ignore[assignment]
    print(f"embed_documents env={target_env}")
    stats = embed_documents(target_env)
    print(stats)
    sys.exit(0)
