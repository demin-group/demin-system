-- ════════════════════════════════════════════════════════════════════════════
-- 20260512120000_10_email_priority_extend_to_5.sql
--
-- Sprint 4 paso 6.6 — extiende `contacts.email_priority` de 1..4 a 1..5 para
-- introducir el sub-bucket "nominal SIN cargo" (priority=4) entre "nominal
-- CON cargo" (priority=3) y "corporativo_pequeno" (priority=5, antes 4).
--
-- NO toca datos. El reordenamiento de valores existentes (4 antiguo →
-- 5 cuando es corporativo_pequeno; resto sin cambio) lo hace
-- `apps/workers/scripts/recompute_priorities_paso66.py`.
--
-- Fuente: tasks/todo.md §8.5 punto 4 + §19 paso 6.6 + Lección 29 (refinamiento
-- de D18 sobre selección y priorización dentro del bucket nominal).
-- ════════════════════════════════════════════════════════════════════════════

-- Suelta el CHECK 1..4 nombrado `contacts_email_priority_check` (heredado de
-- migration 09, ADD COLUMN ... CHECK auto-nombra <tabla>_<col>_check).
alter table contacts
  drop constraint if exists contacts_email_priority_check;

alter table contacts
  add constraint contacts_email_priority_check
  check (email_priority between 1 and 5);

-- Default conservador "peor candidato" pasa de 4 a 5. find_contacts.py
-- siempre especifica priority en el INSERT, así que el default es defensivo
-- para inserts futuros que pudieran omitirlo.
alter table contacts
  alter column email_priority set default 5;

-- COMMENT actualizado con la nueva enumeración 1..5.
comment on column contacts.email_priority is
  '1..5 (1 = mejor candidato; 5 = peor / default conservador). '
  '1 = decisor confidence>=80; 2 = decisor confidence<80; '
  '3 = nominal CON cargo identificado; 4 = nominal SIN cargo; '
  '5 = corporativo_pequeno. Lo rellena find_contacts.py al insertar, ver §8.5 punto 4.';
