# apps/workers

Workers Python que componen el pipeline de captación: ingesta, filtrado, research, redacción, envío, polling de respuestas, clasificación, follow-ups, monitorización y embedding del KB.

Despliegue final: VPS Hetzner CX22 con cron + systemd (ver `infra/systemd/`). Hasta Fase 1 se desarrolla y prueba en local.

## Setup local

Desde `apps/workers/`:

```bash
uv sync          # instala Python 3.11 managed + crea venv + instala deps + escribe uv.lock
uv run pytest    # corre tests (cuando los haya)
uv run ruff check .
uv run mypy .
```

Para ejecutar un worker concreto:

```bash
uv run python -m pipeline.ingest_sabi
uv run python -m kb.embed_documents
```

## Estructura

Cada subdirectorio agrupa workers de una fase del pipeline (ver `tasks/todo.md` §5):

- `pipeline/` — ingesta, filtrado, research y enriquecimiento de leads
- `outreach/` — generación, envío y follow-ups de correos
- `replies/` — polling de respuestas, clasificación y acciones
- `monitoring/` — auto-pausa por bounce/spam
- `kb/` — pipeline de embeddings del Knowledge Base
- `shared/` — DB (SQLAlchemy), cliente LLM, config y prompts versionados

Los prompts viven en `shared/prompts/*.md` por la regla nº 8 del Apéndice A: prompts versionados en repo, no hardcoded en el código.
