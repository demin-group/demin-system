-- ════════════════════════════════════════════════════════════════════════════
-- 20260526230000_16_auto_switch_autonomous.sql
--
-- Sesion 2026-05-26 -- Fase 5 sistema de auto-switch a autonomo.
--
-- Anade dos columnas a `mailboxes`:
--
--   `auto_switch_enabled boolean default true` -- PM puede desactivar
--     el switch automatico desde /settings sin tocar la lógica del worker.
--     Si false: el worker auto_switch_to_autonomous.py evalua condiciones
--     y notifica "cumplidas, activa manualmente" pero NO hace switch.
--     Si true (default): cuando 7/7 condiciones (Bloque 6) verdes, schedule
--     switch para +24h con email previo a PM + Gonzalo.
--
--   `scheduled_autonomous_switch_at timestamptz null` -- timestamp al
--     que se programa el switch hitl_mode=false. NULL = sin switch
--     programado. Cuando el worker detecta condiciones verdes, lo setea
--     a now()+24h y manda email. Al disparar (>=ahora), worker hace
--     UPDATE hitl_mode=false + email confirmacion + NULL este campo.
--
-- Tabla `settings` NO existe en este schema -- las dos columnas viven en
-- mailboxes (donde ya esta hitl_mode). Decision: mantener toda la
-- configuracion de modo por-mailbox para que en futuro multi-buzon cada
-- uno pueda tener su propia regla.
--
-- Default seguro: auto_switch_enabled=true, scheduled_autonomous_switch_at=null.
-- Cambio de hitl_mode requiere QUE las 7 condiciones se cumplan Y que
-- transcurra la ventana 24h con email previo. NUNCA es flip directo.
-- ════════════════════════════════════════════════════════════════════════════

alter table mailboxes
  add column if not exists auto_switch_enabled boolean not null default true,
  add column if not exists scheduled_autonomous_switch_at timestamptz;

comment on column mailboxes.auto_switch_enabled is
  'true (default): worker auto_switch_to_autonomous.py puede programar el '
  'switch hitl_mode=false cuando se cumplan las 7 condiciones del Bloque 6. '
  'false: worker solo evalua y notifica, sin programar. PM cambia desde '
  '/settings con doble confirm si quiere desactivar.';

comment on column mailboxes.scheduled_autonomous_switch_at is
  'Timestamp programado del switch a autonomo. NULL: sin switch programado. '
  'Se setea a now()+24h cuando el worker detecta 7/7 condiciones verdes Y '
  'auto_switch_enabled=true. Email previo a albertobueno10@gmail.com + '
  'gonzalo.perez@demingroupmadrid.com. Al pasar el timestamp y si '
  'condiciones siguen verdes, worker hace UPDATE hitl_mode=false + NULL '
  'aqui. Si alguna condicion se rompe antes, cancela y NULL aqui + email.';

-- Index sobre scheduled_autonomous_switch_at para que el worker pueda
-- buscar pendientes rapido (1 row hoy, pero buena higiene si crece).
create index if not exists ix_mailboxes_scheduled_autonomous_switch_at
  on mailboxes(scheduled_autonomous_switch_at)
  where scheduled_autonomous_switch_at is not null;
