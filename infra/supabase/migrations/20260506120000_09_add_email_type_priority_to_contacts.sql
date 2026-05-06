-- ════════════════════════════════════════════════════════════════════════════
-- 20260506120000_09_add_email_type_priority_to_contacts.sql
--
-- Sprint 4 paso 1 — añade email_type y email_priority a contacts y revisa
-- el CHECK de email_source para incluir 'hunter' y 'skrapp'.
--
-- Fuente: tasks/todo.md §6.1 y §14 paso 1. Decisiones D19, D20, D21.
-- ════════════════════════════════════════════════════════════════════════════

-- email_source revisado (D19): añade 'hunter' y 'skrapp', conserva
-- 'sabi', 'web_scrape', 'apollo', 'manual'. 'rocketreach' queda fuera
-- (D19 supersede D17, ver Lección 21).
alter table contacts
  drop constraint if exists contacts_email_source_check;

alter table contacts
  add constraint contacts_email_source_check
  check (email_source in ('sabi','web_scrape','apollo','hunter','skrapp','manual'));

-- email_type (D20): tipo del email según política tier-segmentada.
alter table contacts
  add column if not exists email_type text
    check (email_type in ('decisor','nominal','corporativo_pequeno','descartado'))
    default 'descartado';

-- email_priority (D20): orden de envío cuando hay varios contacts por empresa.
alter table contacts
  add column if not exists email_priority int
    check (email_priority between 1 and 4)
    default 4;

comment on column contacts.email_type is
  'Tipo de email según D20 (decisor/nominal/corporativo_pequeno/descartado). '
  'Default conservador descartado. Lo rellena find_contacts.py.';

comment on column contacts.email_priority is
  '1..4 (1 = mejor candidato, 4 = peor / default conservador). '
  'Lo rellena find_contacts.py al insertar, ver §8.5.';
