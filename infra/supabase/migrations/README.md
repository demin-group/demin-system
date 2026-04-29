# infra/supabase/migrations

Migraciones SQL del proyecto Supabase.

**Convención de nombrado:** `YYYYMMDDHHMMSS_<descripcion_breve>.sql`. Orden cronológico estricto. No reescribir migraciones aplicadas; siempre crear una nueva que rectifique.

Pendiente de poblar en **B6** (Bloque B del plan de Fase 0): schema completo de `tasks/todo.md` §6 (companies, contacts, mailboxes, sequences, campaigns, messages, replies, events, jobs, kb_documents, kb_chunks, web_leads) + RLS + extensión `vector` para pgvector.
