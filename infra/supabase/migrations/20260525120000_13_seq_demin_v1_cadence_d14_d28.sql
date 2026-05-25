-- ════════════════════════════════════════════════════════════════════════════
-- 20260525120000_13_seq_demin_v1_cadence_d14_d28.sql
--
-- Sesión 2026-05-25 — Lección 39. Recalibra la cadencia de la secuencia
-- 'demin_v1' de D+0/D+4/D+10 (seed migration 11) a D+0/D+14/D+28.
--
-- Origen del cambio: PM revisó los 12 primeros envíos productivos entre el
-- 14 y el 19 de mayo y detectó que el reframe había salido 5 días después
-- del opening (Jaime Nozaleda / Lena Construcciones: opening 14-may,
-- reframe 19-may). Esa cadencia ~D+5 es demasiado agresiva para B2B —
-- riesgo de quemar dominio y degradar deliverability si el sistema
-- escala a 20+/día con un pool pequeño. D+14/D+28 es más natural.
--
-- `outreach/follow_ups.py` lee `sequences.steps[].day` en runtime, así que
-- esta migración cierra el cambio sin necesidad de redeploy de workers.
--
-- Migración defensiva sobre messages.status='scheduled': si en algún
-- entorno (prod/dev) hay messages pre-programados con scheduled_for
-- calculado sobre la cadencia antigua, los recalcula a partir del
-- sent_at del step anterior. En la práctica el sistema no usa
-- pre-scheduling (status='scheduled' del schema §6.1 está definido pero
-- los workers crean 'drafted' y transitan a 'approved'→'sent'); el UPDATE
-- defensivo es a coste cero cuando count=0.
--
-- IDEMPOTENTE: el UPDATE de sequences.steps es JSONB literal sin lectura
-- previa, así que correr múltiples veces deja el estado final correcto.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── 1. Cadencia D+0/D+14/D+28 (Lección 39) ─────────────────────────────────
update sequences
set steps = '[
    {"day": 0,  "angle": "opening"},
    {"day": 14, "angle": "reframe"},
    {"day": 28, "angle": "closing"}
  ]'::jsonb,
    updated_at = now()
where nombre = 'demin_v1';

-- ─── 2. COMMENT actualizado (refleja Lección 39) ────────────────────────────
comment on table sequences is
  'Definición de cadencia. La secuencia "demin_v1" usa pasos D+0/D+14/D+28 (Lección 39, sesión 2026-05-25 — antes D+0/D+4/D+10 desde §9.2 pre-recalibración).';

-- ─── 3. Recalcular scheduled_for de messages 'scheduled' pendientes ──────────
-- Defensivo: si hay messages pre-programados con scheduled_for sobre la
-- cadencia vieja, se recalculan. Si count=0 (caso típico hoy), no-op.
--
-- Step 1 (reframe): scheduled_for = sent_at(step 0) + 14 days.
update messages m1
set scheduled_for = m0.sent_at + interval '14 days'
from messages m0
where m1.status = 'scheduled'
  and m1.step_index = 1
  and m0.contact_id = m1.contact_id
  and m0.step_index = 0
  and m0.status = 'sent'
  and m0.sent_at is not null;

-- Step 2 (closing): scheduled_for = sent_at(step 0) + 28 days.
update messages m2
set scheduled_for = m0.sent_at + interval '28 days'
from messages m0
where m2.status = 'scheduled'
  and m2.step_index = 2
  and m0.contact_id = m2.contact_id
  and m0.step_index = 0
  and m0.status = 'sent'
  and m0.sent_at is not null;
