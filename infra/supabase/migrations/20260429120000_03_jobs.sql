-- ════════════════════════════════════════════════════════════════════════════
-- 20260429120000_03_jobs.sql
--
-- Cola de jobs en Postgres (sin Redis). Workers Python hacen pull, procesan,
-- marcan como done/failed.
--
-- Fuente: tasks/todo.md §6.1
-- ════════════════════════════════════════════════════════════════════════════

create table jobs (
  id            uuid primary key default gen_random_uuid(),
  type          text not null,
  payload       jsonb,
  status        text not null check (status in ('pending','running','done','failed')) default 'pending',
  attempts      int not null default 0,
  last_error    text,
  scheduled_for timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  completed_at  timestamptz
);

comment on table  jobs           is 'Cola de tareas de los workers Python. Implementación pull-based: worker selecciona pending con scheduled_for <= now() y status="pending".';
comment on column jobs.type      is 'research_prospect | classify_descr | generate_draft | send_email | classify_reply | embed_document | etc.';
comment on column jobs.attempts  is 'Contador de reintentos. Workers aplican backoff exponencial.';

create index jobs_status_scheduledfor_idx on jobs(status, scheduled_for);

-- ════════════════════════════════════════════════════════════════════════════
