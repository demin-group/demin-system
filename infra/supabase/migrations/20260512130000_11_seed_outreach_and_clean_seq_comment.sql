-- ════════════════════════════════════════════════════════════════════════════
-- 20260512130000_11_seed_outreach_and_clean_seq_comment.sql
--
-- Sprint 4 paso 7 — seeds idempotentes de outreach (mailbox + sequence
-- demin_v1 + campaign T3 Semana 1) y limpieza del comentario obsoleto en
-- `sequences` que referenciaba D+0/D+12/D+30 (heredado del Bloque A pre-D22).
--
-- NO añade 'paused' al CHECK de messages.status. Decisión PM 2026-05-12
-- (opción A): auto-pausa solo cambia `mailboxes.status='paused'`; los
-- workers de envío comprueban `mailbox.status='active'` antes de procesar.
-- Reversible sin schema change.
--
-- Fuente: tasks/todo.md §9.2 (cadencia D+0/D+4/D+10) + §9.3 (cap 20/día
-- Semana 1, refinado tras Lemwarm score 92) + §14 paso 7.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── 1. Mailbox sender principal ────────────────────────────────────────────
-- gonzalo.perez@demingroupmadrid.com con cap 20/día (decisión PM 2026-05-12,
-- supersede al "10/día Semana 1" del plan original §9.3). Lemwarm score 92 +
-- reply rate 80% tras 2 semanas justifica arrancar más alto.
--
-- oauth_refresh_token_encrypted queda NULL hasta que el bloqueador humano
-- B1 (Gmail OAuth en Google Cloud Console, coordinación PM + Gonzalo) se
-- resuelva. send_gmail.py aborta si encuentra mailbox activo sin refresh
-- token, así que estado parcial no envía nada accidentalmente.
insert into mailboxes (email, display_name, daily_cap, warmup_status, status)
select 'gonzalo.perez@demingroupmadrid.com', 'Gonzalo Pérez', 20, 'ready', 'active'
where not exists (
  select 1 from mailboxes where email = 'gonzalo.perez@demingroupmadrid.com'
);

-- ─── 2. Sequence demin_v1 (D+0/D+4/D+10) ────────────────────────────────────
-- Pasos alineados con §9.2: opening (D+0), reframe (D+4), closing (D+10).
-- generate_draft.py + prompts paso 5 ya usan estos tres angles.
insert into sequences (nombre, is_active, steps)
select
  'demin_v1',
  true,
  '[
    {"day": 0,  "angle": "opening"},
    {"day": 4,  "angle": "reframe"},
    {"day": 10, "angle": "closing"}
  ]'::jsonb
where not exists (select 1 from sequences where nombre = 'demin_v1');

-- ─── 3. Campaign T3 Semana 1 ────────────────────────────────────────────────
-- Primera campaña productiva (D22 roll-out escalonado). Status='draft'
-- hasta que el primer batch HITL-aprobado entre a 'running'.
insert into campaigns (nombre, sequence_id, status)
select
  'T3 Semana 1',
  (select id from sequences where nombre = 'demin_v1'),
  'draft'
where not exists (select 1 from campaigns where nombre = 'T3 Semana 1');

-- ─── 4. Limpieza comentarios obsoletos migration 02 ─────────────────────────
-- El comentario original de `sequences` referenciaba D+0/D+12/D+30 según
-- una versión temprana del plan (Bloque A). El plan §9.2 fijó D+0/D+4/D+10
-- en sesión 2026-04-29 y se ha mantenido desde entonces. Limpiamos para
-- evitar que la próxima persona que lea el schema crea que la cadencia es
-- D+12/D+30.
comment on table sequences is
  'Definición de cadencia. La secuencia "demin_v1" usa pasos D+0/D+4/D+10 según §9.2.';

-- Comentario daily_cap también heredaba el "arrancar en 10" del plan
-- pre-warmup. Cap inicial real Semana 1 = 20 (Lección 30).
comment on column mailboxes.daily_cap is
  'Tope diario de envíos por buzón. Rampa §9.3 (paso 7+): Sem1=20, Sem2=25, Sem3=30, Sem4+=40 (max 50 por §9.1).';
