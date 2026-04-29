-- ════════════════════════════════════════════════════════════════════════════
-- 20260429120000_06_rls.sql
--
-- Habilita Row Level Security en las 12 tablas y aplica política inicial
-- "authenticated puede todo". El role anon queda implícitamente denegado
-- (sin política aplicable).
--
-- Notas:
--   - Los workers Python conectan con la service_role key, que bypassa RLS
--     automáticamente — no necesitan policies.
--   - El route handler /api/contact (sitio público) también usa service_role
--     para insertar en web_leads (visitante anónimo no puede tener sesión).
--     La RLS en web_leads protege contra acceso directo desde el navegador
--     usando solo la anon key.
--
-- Fuente: tasks/todo.md §6.3 — "políticas en Fase 0 son simples (solo
-- usuarios autenticados leen/escriben)". Refinarán en Fase 1 con roles.
-- ════════════════════════════════════════════════════════════════════════════

-- Habilitar RLS en las 12 tablas.
alter table companies     enable row level security;
alter table contacts      enable row level security;
alter table mailboxes     enable row level security;
alter table sequences     enable row level security;
alter table campaigns     enable row level security;
alter table messages      enable row level security;
alter table replies       enable row level security;
alter table events        enable row level security;
alter table jobs          enable row level security;
alter table kb_documents  enable row level security;
alter table kb_chunks     enable row level security;
alter table web_leads     enable row level security;

-- Política única por tabla: authenticated puede hacer todo.
-- Sintaxis: "for all" cubre SELECT/INSERT/UPDATE/DELETE.
create policy authenticated_all on companies     for all to authenticated using (true) with check (true);
create policy authenticated_all on contacts      for all to authenticated using (true) with check (true);
create policy authenticated_all on mailboxes     for all to authenticated using (true) with check (true);
create policy authenticated_all on sequences     for all to authenticated using (true) with check (true);
create policy authenticated_all on campaigns     for all to authenticated using (true) with check (true);
create policy authenticated_all on messages      for all to authenticated using (true) with check (true);
create policy authenticated_all on replies       for all to authenticated using (true) with check (true);
create policy authenticated_all on events        for all to authenticated using (true) with check (true);
create policy authenticated_all on jobs          for all to authenticated using (true) with check (true);
create policy authenticated_all on kb_documents  for all to authenticated using (true) with check (true);
create policy authenticated_all on kb_chunks     for all to authenticated using (true) with check (true);
create policy authenticated_all on web_leads     for all to authenticated using (true) with check (true);

-- ════════════════════════════════════════════════════════════════════════════
