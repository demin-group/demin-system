-- ════════════════════════════════════════════════════════════════════════════
-- 20260527113000_17_rfc_message_id_and_replies_dedup.sql
--
-- Sesion 2026-05-27 -- Fix bugs encadenados en poll_imap (replies table 0 filas
-- pese a OAuth desbloqueado). Diagnostico completo: matcher RFC stubeado,
-- filtro is:unread con race con lectura humana, dedup por header inexistente.
--
-- Anade dos columnas:
--
--   `messages.rfc_message_id text` -- RFC 5322 Message-ID generado por
--     gmail_adapter.send_email (make_msgid). El reply In-Reply-To /
--     References apunta a ESTE valor (no a gmail_message_id que es el id
--     interno Gmail). Sin esta columna find_matching_message_by_rfc_id
--     no podia hacer su trabajo y caia al fallback subject+from que falla
--     en 4/4 casos reales (forwards internos, dominios .com vs .es, etc).
--
--   `replies.gmail_message_id text UNIQUE` -- id interno Gmail de la
--     respuesta. Permite dedup natural sin depender de marcar-leido en
--     Gmail. Decision PM: bot ya NO marca leidos en Gmail (asi Gonzalo
--     conserva la senal humana "que he visto"). UNIQUE constraint impide
--     doble insert si poll_imap procesa el mismo mensaje dos veces.
--     Nullable para tolerar replies historicos sin gmail_message_id
--     conocido (no aplica hoy -- 0 filas en replies -- pero queda abierto).
--
-- Backfill: tabla replies tiene 0 filas verificado al cierre 27-may pre-fix.
-- No requiere UPDATE de filas existentes.
-- ════════════════════════════════════════════════════════════════════════════

alter table messages
  add column if not exists rfc_message_id text;

create index if not exists ix_messages_rfc_message_id
  on messages(rfc_message_id)
  where rfc_message_id is not null;

comment on column messages.rfc_message_id is
  'RFC 5322 Message-ID header generado por gmail_adapter al enviar '
  '(make_msgid con SENDING_DOMAIN). poll_imap.find_matching_message_by_rfc_id '
  'matchea esto contra In-Reply-To / References de los replies recibidos. '
  'Distinto de gmail_message_id (id interno Gmail). NULL para messages '
  'enviados antes de migration 17 (gestionados via fallback subject+from).';

alter table replies
  add column if not exists gmail_message_id text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'replies_gmail_message_id_unique'
  ) then
    alter table replies
      add constraint replies_gmail_message_id_unique unique (gmail_message_id);
  end if;
end $$;

comment on column replies.gmail_message_id is
  'Id interno Gmail del mensaje de respuesta recibido. Dedup primario de '
  'poll_imap: si ya existe, skip silencioso. Permite que el bot NO marque '
  'leidos en Gmail (decision PM 2026-05-27) sin riesgo de doble insert.';
