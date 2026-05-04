-- ════════════════════════════════════════════════════════════════════════════
-- 20260501000000_07_grants.sql
--
-- Grants explícitos sobre `public.*` para los roles que PostgREST mapea a
-- partir de las API keys (`service_role`, `authenticated`). Sin estos GRANT,
-- las migraciones 01-06 dejan las tablas con RLS habilitada pero
-- `permission denied for table ...` cuando el acceso entra vía REST API.
--
-- Por qué hace falta este parche:
--   - PostgreSQL separa "permiso de tabla" (GRANT) de "permiso de fila" (RLS
--     policy). RLS no concede acceso si antes no hay GRANT al role.
--   - El owner de las tablas creadas en 01-05 es `postgres` (la cuenta del
--     session pooler usada por apply_migrations.py). Por defecto Postgres NO
--     hace public-grant al resto de roles.
--   - PostgREST recibe la apikey, mapea a service_role | authenticated | anon
--     y ejecuta SET ROLE — momento en el que el Postgres exige el GRANT.
--   - El script `verify_migrations.py` no detectó este gap porque conecta
--     como `postgres` (owner) y tiene grants implícitos.
--
-- Diagnóstico: detectado en Bloque C al primer smoke test de /api/contact.
-- Ver `tasks/lessons.md` Lección 7.
-- ════════════════════════════════════════════════════════════════════════════

-- service_role: control total. Lo usa el route handler /api/contact y los
-- workers Python que necesitan bypass de RLS por diseño (research_prospect,
-- send_gmail, etc.). El bypass de RLS por service_role solo es real cuando
-- también tiene los GRANTs.
grant usage on schema public to service_role;
grant all privileges on all tables    in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant all privileges on all functions in schema public to service_role;

-- authenticated: control total dentro de las RLS policies de 06_rls.sql
-- (`authenticated_all` con `using (true) with check (true)`). Esto es lo que
-- el dashboard, una vez logueado vía supabase-js, usará para CRUD desde el
-- cliente del navegador.
grant usage on schema public to authenticated;
grant all privileges on all tables    in schema public to authenticated;
grant all privileges on all sequences in schema public to authenticated;
grant all privileges on all functions in schema public to authenticated;

-- anon: NO recibe grants. El visitante no autenticado no debe acceder
-- directamente a la BD. La web pública entra vía /api/contact (server-side,
-- service_role). Si en el futuro se necesitara endpoint público, añadir
-- grant SELECT explícito sobre la tabla concreta + RLS policy compatible.

-- Default privileges para tablas/secuencias/funciones creadas en futuras
-- migraciones, para no tener que repetir este parche por tabla.
alter default privileges in schema public
  grant all on tables    to service_role, authenticated;
alter default privileges in schema public
  grant all on sequences to service_role, authenticated;
alter default privileges in schema public
  grant all on functions to service_role, authenticated;

-- Forzar reload del schema cache de PostgREST para que los grants surtan
-- efecto sin esperar el polling periódico.
notify pgrst, 'reload schema';

-- ════════════════════════════════════════════════════════════════════════════
