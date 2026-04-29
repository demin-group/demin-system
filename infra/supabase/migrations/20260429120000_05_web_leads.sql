-- ════════════════════════════════════════════════════════════════════════════
-- 20260429120000_05_web_leads.sql
--
-- Leads inbound desde el formulario de contacto del sitio público
-- (demingroupmadrid.com). NO se mezclan con outbound de Sabi — visibles en
-- una sección separada del dashboard.
--
-- Fuente: tasks/todo.md §13.4
-- ════════════════════════════════════════════════════════════════════════════

create table web_leads (
  id         uuid primary key default gen_random_uuid(),
  nombre     text,
  empresa    text,
  telefono   text,
  email      text,
  mensaje    text,
  origen     text not null default 'web_form',
  status     text not null default 'nuevo',
  created_at timestamptz not null default now()
);

comment on table  web_leads         is 'Leads inbound del sitio público. Insertados por el route handler /api/contact con bypass de RLS (visitante anónimo).';
comment on column web_leads.origen  is 'Canal de origen. v1: web_form. Futuro: whatsapp, instagram.';
comment on column web_leads.status  is 'Estado en pipeline. nuevo | contactado | descartado.';

create index web_leads_createdat_idx on web_leads(created_at desc);

-- ════════════════════════════════════════════════════════════════════════════
