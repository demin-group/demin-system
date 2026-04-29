# infra/supabase/migrations

Migraciones SQL del proyecto Supabase. Aplicadas vía
`apps/workers/scripts/apply_migrations.py` (psycopg + transacción por
fichero, tracking en tabla `_migrations`).

**Convención de nombrado:** `YYYYMMDDHHMMSS_NN_<descripcion>.sql`. Orden
lexicográfico = orden cronológico. Nunca reescribir migraciones aplicadas;
siempre crear una nueva que rectifique.

## Migraciones actuales (B6, 2026-04-29)

| # | Fichero | Contenido |
|---|---|---|
| 01 | `20260429120000_01_extensions_and_core.sql` | `pgcrypto`, `vector`, `companies`, `contacts` |
| 02 | `20260429120000_02_outreach.sql` | `mailboxes`, `sequences`, `campaigns`, `messages`, `replies`, `events` |
| 03 | `20260429120000_03_jobs.sql` | `jobs` (cola pull-based) |
| 04 | `20260429120000_04_kb.sql` | `kb_documents`, `kb_chunks` con `vector(1024)`, trigger `updated_at` |
| 05 | `20260429120000_05_web_leads.sql` | `web_leads` (inbound del sitio público) |
| 06 | `20260429120000_06_rls.sql` | `enable row level security` + política `authenticated_all` × 12 |

## Aplicación

```bash
cd apps/workers
uv run python scripts/apply_migrations.py --env dev
uv run python scripts/verify_migrations.py --env dev
uv run python scripts/apply_migrations.py --env prod   # pide 'yes' literal antes de tocar prod
uv run python scripts/verify_migrations.py --env prod
```

## Notas

- Las políticas RLS son intencionalmente permisivas en Fase 0
  ("authenticated puede todo"). Se refinarán en Fase 1 cuando haya roles
  diferenciados.
- La extensión `vector` viene preinstalada en Supabase pero `create extension
  if not exists` la activa para schema `public`.
- El índice `ivfflat` sobre `kb_chunks.embedding` rinde mal con tabla vacía;
  conviene reconstruirlo (`reindex index kb_chunks_embedding_idx`) cuando
  haya volumen real de chunks.
