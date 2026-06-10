-- ════════════════════════════════════════════════════════════════════════════
-- 20260610120000_18_seq_demin_v1_cadence_d40_d80_d120.sql
--
-- Sesión 2026-06-10 — Lección 62. Decisión de producto (Alberto/Fernando):
-- espaciar mucho más los follow-ups a NO-respondedores y añadir un toque
-- adicional. La cadencia de 'demin_v1' pasa de 3 toques (D+0/D+14/D+28,
-- migration 13) a 4 toques: D+0/D+40/D+80/D+120.
--
--   step 0  opening   D+0     (sin cambios)
--   step 1  reframe   D+40    (era D+14)
--   step 2  value     D+80    (NUEVO ángulo — 3er follow-up, baja fricción)
--   step 3  closing   D+120   (era step 2 / D+28 — RE-INDEXADO a step 3)
--
-- Regla intacta: si el contacto responde en cualquier punto, la secuencia se
-- detiene (follow_ups.fetch_followup_candidates filtra NOT EXISTS reply).
--
-- ─── Semántica del scheduler (importante) ───────────────────────────────────
-- `outreach/follow_ups.py` lee `sequences.steps[].day` en runtime y programa
-- cada toque a `(day[N] - day[N-1])` días del `sent_at` REAL del paso previo
-- (no del opening). Con 0/40/80/120 el delta es 40 entre cada toque, así que
-- un contacto puntual recibe opening, +40, +80, +120 desde el opening. El
-- cambio de cadencia es solo este UPDATE en BD; no requiere redeploy de
-- workers. Lo único que NO es data-driven es la whitelist de `angle` válidos:
-- el ángulo nuevo `value` se añadió en el mismo cambio a follow_ups.py y
-- generate_draft.py (Literal + _STEP_BY_ANGLE) y a su prompt versionado
-- (apps/workers/shared/prompts/generate_email_value.md).
--
-- ─── Contactos en vuelo (decisión PM 2026-06-10: confiar + verificar) ───────
-- 1. Idempotencia: el scheduler no reprograma un (contact, step_index) que ya
--    existe (status <> 'cancelled'). CERO duplicados.
-- 2. Ampliar intervalos solo RETRASA el siguiente toque, nunca lo adelanta:
--    un contacto a mitad de secuencia ve su próximo correo más tarde, jamás
--    un toque inmediato inesperado.
-- 3. Re-indexación closing 2→3: los contactos que YA recibieron el closing
--    bajo la cadencia vieja lo tienen como step_index=2 + angle='closing'. El
--    campo `angle` (texto) es el dato autoritativo en todo el código que lo
--    lee; solo el step_index cambia de significado hacia adelante. Al día de
--    hoy (10-jun-2026, ~27 días de envíos productivos) NINGÚN contacto ha
--    completado aún el closing, así que el riesgo de un FU3/closing extra a
--    "ya completados" es nulo al aplicar ahora. Tras aplicar en prod, correr
--    `uv run python -m outreach.follow_ups --env prod --dry-run` para
--    confirmar que el primer batch de value/closing NO sale inmediato.
-- 4. Colisión step_index 3 (closing de cadencia vs re_engage_40 de
--    handle_actions): inocua. El dedup de re_engage es por `angle` (texto), y
--    un contacto que respondió (→ re_engage) nunca recorre la cadencia
--    (detenida en cualquier reply). classify_replies lee `messages.angle`
--    directo para no confundirlos.
--
-- IDEMPOTENTE: el UPDATE de sequences.steps es JSONB literal sin lectura
-- previa; correr múltiples veces deja el estado final correcto.
--
-- NO hace recálculo de messages.status='scheduled' (a diferencia de
-- migration 13): el sistema no usa pre-scheduling — los workers crean
-- 'drafted' y el scheduler recalcula el próximo toque en runtime sobre el
-- sent_at real, así que no hay timestamps pre-calculados que arreglar.
-- ════════════════════════════════════════════════════════════════════════════

-- ─── 1. Cadencia D+0/D+40/D+80/D+120 (Lección 62) ───────────────────────────
update sequences
set steps = '[
    {"day": 0,   "angle": "opening"},
    {"day": 40,  "angle": "reframe"},
    {"day": 80,  "angle": "value"},
    {"day": 120, "angle": "closing"}
  ]'::jsonb
where nombre = 'demin_v1';

-- ─── 2. COMMENT actualizado (refleja Lección 62) ────────────────────────────
comment on table sequences is
  'Definición de cadencia. La secuencia "demin_v1" usa pasos D+0/D+40/D+80/D+120 (Lección 62, sesión 2026-06-10 — antes D+0/D+14/D+28 [L39] y D+0/D+4/D+10 [seed]). 4 toques: opening/reframe/value/closing. La secuencia se detiene si el contacto responde.';

comment on column messages.step_index is
  '0=opening (D+0), 1=reframe (D+40), 2=value (D+80), 3=closing (D+120). Re-engages usan step_index propio (3=re_engage_40, 4=re_engage_90); conviven con la cadencia sin colisión real porque ésta se detiene en cualquier reply.';

comment on column messages.angle is
  'opening | reframe | value | closing | re_engage_40 | re_engage_90.';
