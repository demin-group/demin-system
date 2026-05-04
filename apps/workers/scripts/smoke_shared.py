"""Smoke ejecutable de apps/workers/shared/.

Uso desde apps/workers/:
    uv run python scripts/smoke_shared.py

`ENV` se hardcodea a `"dev"` ANTES de importar `shared.config`. Para forzar
otro entorno hay que editar este script y exportar `ENV=prod` manualmente
fuera de él — el smoke nunca toca prod por sí solo.

Ejecuta 4 pasos contra demin-dev y reporta:
    1) Config cargado y modelos seleccionados.
    2) SELECT 1 + count(kb_documents) sobre Postgres.
    3) call_llm(task="classify_descr") con system+user mínimos.
    4) embed(["test de embedding"]) — valida dim 1024.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Hardcodeado a dev: el smoke nunca toca prod.
os.environ.setdefault("ENV", "dev")

# Permitir `from shared...` aunque el script no se ejecute como módulo.
WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from sqlalchemy import text  # noqa: E402

from shared.config import ACTIVE_ENV_FILE, settings  # noqa: E402

SEP = "-" * 64


def step1_config() -> None:
    print(SEP)
    print("[1/4] config")
    print(f"  ENV cargado: {settings.SUPABASE_ENV} (desde {ACTIVE_ENV_FILE.name})")
    print(f"  ANTHROPIC_MODEL_CLASSIFY: {settings.ANTHROPIC_MODEL_CLASSIFY}")
    print(f"  ANTHROPIC_MODEL_GENERATE: {settings.ANTHROPIC_MODEL_GENERATE}")
    print(f"  ANTHROPIC_MODEL_RESEARCH: {settings.ANTHROPIC_MODEL_RESEARCH}")
    print(f"  ANTHROPIC_MODEL_REPLY:    {settings.ANTHROPIC_MODEL_REPLY}")
    print(f"  VOYAGE_MODEL:             {settings.VOYAGE_MODEL}")
    print(f"  VOYAGE_EMBEDDING_DIM:     {settings.VOYAGE_EMBEDDING_DIM}")
    print(f"  LOG_LEVEL:                {settings.LOG_LEVEL}")


def step2_db() -> None:
    from shared.db import get_session

    print(SEP)
    print("[2/4] db")
    env = settings.SUPABASE_ENV
    with get_session(env) as s:
        one = s.execute(text("select 1")).scalar_one()
        cnt = s.execute(text("select count(*) from kb_documents")).scalar_one()
    print(f"  SELECT 1                  -> {one}")
    print(f"  count(kb_documents)       -> {cnt}")


def step3_llm() -> None:
    from shared.llm import call_llm

    print(SEP)
    print("[3/4] llm - call_llm(task='classify_descr')")
    txt, meta = call_llm(
        task="classify_descr",
        system="Eres un test",
        user="Responde 'OK' y nada más",
        max_tokens=10,
    )
    print(f"  respuesta: {txt!r}")
    print(f"  meta:      {meta}")


def step4_embed() -> None:
    from shared.llm import embed

    print(SEP)
    print("[4/4] embed - embed(['test de embedding'])")
    vecs = embed(["test de embedding"])
    print(f"  n_vectores: {len(vecs)}")
    print(f"  dim:        {len(vecs[0])}")
    print(f"  primeros 4 valores: {vecs[0][:4]}")


def main() -> int:
    if settings.SUPABASE_ENV != "dev":
        print(
            f"  ABORT: SUPABASE_ENV={settings.SUPABASE_ENV!r}; smoke solo corre "
            f"contra dev."
        )
        return 1
    try:
        step1_config()
        step2_db()
        step3_llm()
        step4_embed()
    except Exception as e:
        print(f"\n  FALLO: {type(e).__name__}: {e}")
        raise
    print(SEP)
    print("smoke_shared OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
