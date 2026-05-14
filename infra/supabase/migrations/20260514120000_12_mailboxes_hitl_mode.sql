-- Migration 12 -- Sprint 6 Fase 3
-- Anade columna mailboxes.hitl_mode boolean (default true).
-- Cuando hitl_mode=true: drafts esperan aprobacion humana en /approval-queue
-- (cadencia actual). Cuando hitl_mode=false: worker auto_approve.py aprueba
-- drafts automaticamente y pasan a status='approved' -> envio via send_gmail.
--
-- Apendice A regla 1: nunca enviar sin pasar por HITL. Cuando hitl_mode=false,
-- el sistema sigue pasando por cola HITL (status='drafted' -> 'approved'),
-- pero el "aprobador" es el worker auto_approve.py en lugar de Gonzalo.
-- Esto permite cumplir la regla 1 a nivel arquitectonico (cola HITL existe)
-- mientras el modo autonomo automatiza el step humano.
--
-- Decision PM: tras 7 dias piloto con bounce <2%, spam <0.1%, sin escalados
-- graves -> activar autonomo via UI /settings (toggle con doble confirm).
-- Default seguro: HITL=true. Sprint 6 deja la infra construida pero NO activa.

alter table mailboxes
  add column if not exists hitl_mode boolean not null default true;

comment on column mailboxes.hitl_mode is
  'true=cadencia HITL (drafts esperan Gonzalo en /approval-queue). false=modo '
  'autonomo (auto_approve.py aprueba drafts automaticamente sin intervencion). '
  'Default true. Cambiar a false requiere UI /settings con doble confirm + '
  'paper trail en events. Decision PM tras piloto HITL 7 dias.';

-- Para auditoria: cuando cambie hitl_mode, insertar evento en events.
-- El UI lo hace via Server Action settings/actions.ts.
