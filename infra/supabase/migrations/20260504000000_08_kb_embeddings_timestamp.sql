-- ════════════════════════════════════════════════════════════════════════════
-- 20260504000000_08_kb_embeddings_timestamp.sql
--
-- Anade `kb_documents.embeddings_updated_at` para que la pantalla KB del
-- dashboard pueda mostrar a Gonzalo cuando fue la ultima vez que se reembedo
-- cada documento, sin tener que abrir kb_chunks.
--
-- Fuente: Sprint 1 paso 4 (KB editor en dashboard), prompt 2026-05-04.
-- Necesidad operativa #4 del prompt: "que cuando Gonzalo edite un documento
-- pueda ver cuando fue la ultima vez que se embebio".
--
-- Decision de diseno:
--   - Columna en kb_documents (no en kb_chunks) porque interesa el timestamp
--     a nivel doc, no a nivel chunk. Un documento se reembedo "atomicamente"
--     desde la perspectiva de la UI: chunks viejos borrados + chunks nuevos
--     insertados + timestamp actualizado en una sola operacion del backend.
--   - NULL = nunca embebido. Distinto de "embebido y luego borrado":
--     ese caso no existe operativamente — borrar el doc hace CASCADE en
--     kb_chunks; borrar chunks sin borrar doc no es un flujo soportado.
--   - Backfill: los 6 docs cargados en sesiones 1+2 con Gonzalo y embebidos
--     en Sprint 1 paso 2 reciben now() como timestamp. La precision exacta
--     no importa — lo que la UI muestra es "hace X minutos/horas".
-- ════════════════════════════════════════════════════════════════════════════

alter table kb_documents
  add column if not exists embeddings_updated_at timestamptz;

comment on column kb_documents.embeddings_updated_at is
  'Timestamp del ultimo reembed exitoso. NULL = doc nunca embebido. '
  'Lo escribe el backend tras INSERT bulk en kb_chunks (Sprint 1 paso 4).';

-- Backfill para los docs que ya tienen chunks (cargados en Sprint 1 paso 2).
update kb_documents
set embeddings_updated_at = now()
where exists (
  select 1 from kb_chunks c where c.document_id = kb_documents.id
)
  and embeddings_updated_at is null;
