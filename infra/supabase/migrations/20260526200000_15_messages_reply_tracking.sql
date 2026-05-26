-- ════════════════════════════════════════════════════════════════════════════
-- 20260526200000_15_messages_reply_tracking.sql
--
-- Sesion 2026-05-26 -- Bloque D.1 captura de senal sobre respuestas.
--
-- Anade dos columnas a `messages`:
--
--   `reply_received_at timestamptz` -- timestamp de la primera respuesta
--     valida (NO bounce, NO OOO) recibida para este mensaje concreto. El
--     match lo hace poll_imap.py via In-Reply-To / References header
--     contra messages.gmail_message_id (logica ya existente en
--     replies.poll_imap._normalize_message_id_header).
--
--   `reply_category text` -- espejo de replies.category para queries
--     rapidos en /metrics: reply rate por angulo, distribucion por
--     categoria, sin necesidad de join a replies.
--
-- Las dos columnas son nullable -- la mayoria de messages NO recibira
-- respuesta. Solo se rellenan cuando llega un reply matched.
--
-- Quien las escribe: poll_imap (o handle_actions tras clasificar) hara
-- UPDATE messages SET reply_received_at = replies.received_at,
-- reply_category = replies.category WHERE messages.id = replies.message_id.
-- Esto se aplica desde el siguiente turno cuando OAuth B7 se resuelva.
--
-- Por ahora: la migracion solo crea el schema. El backfill (poblar
-- columnas para mensajes ya respondidos antes de este cambio) no aplica
-- todavia porque NO hay replies en BD (0 filas al cierre 26-may). Cuando
-- haya volumen y se decida backfill, sera UPDATE messages FROM replies
-- WHERE messages.id = replies.message_id.
-- ════════════════════════════════════════════════════════════════════════════

alter table messages
  add column if not exists reply_received_at timestamptz,
  add column if not exists reply_category    text;

-- CHECK constraint para reply_category espejo del replies.category enum.
-- Valores tomados de classify_replies.md / replies.category enum implicito.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'messages_reply_category_check'
  ) then
    alter table messages
      add constraint messages_reply_category_check check (
        reply_category is null or reply_category in (
          'interesado', 'pide_info', 'no_ahora', 'no_interesado',
          'rebote', 'fuera_oficina', 'desconocido'
        )
      );
  end if;
end $$;

-- Index parcial: filas con reply_received_at NOT NULL son el subset que
-- /metrics consulta para reply rate. Sin filas vacias indexadas.
create index if not exists ix_messages_reply_received_at
  on messages(reply_received_at)
  where reply_received_at is not null;

-- Index parcial para distribucion por categoria.
create index if not exists ix_messages_reply_category
  on messages(reply_category)
  where reply_category is not null;

comment on column messages.reply_received_at is
  'Timestamp del primer reply valido (no bounce, no OOO) matched por '
  'In-Reply-To al gmail_message_id de este envio. Rellenado por '
  'poll_imap/handle_actions cuando OAuth B7 este resuelto. NULL si nadie '
  'respondio o si la respuesta era bounce/OOO.';

comment on column messages.reply_category is
  'Espejo de replies.category para queries de /metrics sin join. '
  'Mismos valores que classify_replies. NULL coherente con '
  'reply_received_at IS NULL.';
