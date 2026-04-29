-- ════════════════════════════════════════════════════════════════════════════
-- 20260429120000_04_kb.sql
--
-- Knowledge Base con RAG en pgvector. kb_documents son los markdown que
-- aporta Gonzalo; kb_chunks son los trozos embebidos para retrieval.
--
-- Embedding dim 1024 = voyage-multilingual-2 (decidido en Bloque A).
-- Fuente: tasks/todo.md §6.2
-- ════════════════════════════════════════════════════════════════════════════

-- ─── kb_documents ───────────────────────────────────────────────────────────
create table kb_documents (
  id         uuid primary key default gen_random_uuid(),
  category   text check (category in ('servicios','icp','objeciones','casos_exito','tono','diferenciador','correos_gonzalo','otro')),
  titulo     text not null,
  contenido  text not null,
  is_active  boolean not null default true,
  created_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table  kb_documents           is 'Documentos del Knowledge Base. Editables desde el dashboard (§12.4). Trigger auto-update updated_at on row change.';
comment on column kb_documents.category  is 'Una de 8 categorías: servicios | icp | objeciones | casos_exito | tono | diferenciador | correos_gonzalo | otro.';
comment on column kb_documents.is_active is 'Soft delete. Inactivos no entran en retrieval pero quedan para auditar.';

-- Trigger auto-update de updated_at on UPDATE (decisión Q6 aprobada).
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger kb_documents_updated_at
  before update on kb_documents
  for each row
  execute function set_updated_at();

-- ─── kb_chunks ──────────────────────────────────────────────────────────────
create table kb_chunks (
  id          uuid primary key default gen_random_uuid(),
  document_id uuid not null references kb_documents(id) on delete cascade,
  chunk_index int not null,
  contenido   text not null,
  embedding   vector(1024),
  created_at  timestamptz not null default now()
);

comment on table  kb_chunks            is 'Chunks ~500 tokens con overlap 50. Embedding dim 1024 = voyage-multilingual-2.';
comment on column kb_chunks.embedding  is 'Vector cosine. Si se cambia de modelo de embeddings, hay que reembedar todo (no se pueden mezclar dims).';

create index kb_chunks_embedding_idx on kb_chunks using ivfflat (embedding vector_cosine_ops);

-- ════════════════════════════════════════════════════════════════════════════
