-- ════════════════════════════════════════════════════════════════════════════
-- 20260429120000_02_outreach.sql
--
-- Outreach core: buzones de envío, secuencias, campañas, mensajes (drafts y
-- enviados), respuestas recibidas y log de eventos.
--
-- Fuente: tasks/todo.md §6.1
-- ════════════════════════════════════════════════════════════════════════════

-- ─── mailboxes ──────────────────────────────────────────────────────────────
create table mailboxes (
  id                            uuid primary key default gen_random_uuid(),
  email                         text unique not null,
  display_name                  text,
  daily_cap                     int not null default 50,
  current_day_sent              int not null default 0,
  warmup_status                 text check (warmup_status in ('warming','ready','paused')),
  oauth_refresh_token_encrypted text,
  status                        text not null check (status in ('active','paused','disabled')) default 'active',
  pause_reason                  text
);

comment on table  mailboxes                                is 'Buzones de envío del dominio nuevo. La cadencia/caps reales viven en Lección 4 (1 buzón ahora; warm standby día 14).';
comment on column mailboxes.daily_cap                      is 'Tope diario de envíos. Lección 4: arrancar en 10, +5/sem, máximo 40.';
comment on column mailboxes.current_day_sent               is 'Contador rolling 24h. Resetea por worker outreach/send_gmail.';
comment on column mailboxes.warmup_status                  is 'Estado del warmup externalizado (Lemwarm).';
comment on column mailboxes.oauth_refresh_token_encrypted  is 'Refresh token Gmail cifrado vía Supabase Vault — nunca en plano.';
comment on column mailboxes.status                         is 'active=enviando; paused=auto-pausa por bounce/spam; disabled=retirado.';

-- ─── sequences ──────────────────────────────────────────────────────────────
create table sequences (
  id         uuid primary key default gen_random_uuid(),
  nombre     text not null,
  is_active  boolean not null default true,
  steps      jsonb not null
);

comment on table  sequences        is 'Definición de cadencia. La secuencia "demin_v1" usa pasos D+0/D+12/D+30 según Lección 4 (no D+0/D+4/D+10 del plan original).';
comment on column sequences.steps  is 'Array JSON de pasos. Ejemplo: [{"day":0,"angle":"opening"},{"day":12,"angle":"reframe"},{"day":30,"angle":"closing"}].';

-- ─── campaigns ──────────────────────────────────────────────────────────────
create table campaigns (
  id          uuid primary key default gen_random_uuid(),
  nombre      text not null,
  sequence_id uuid references sequences(id),
  status      text not null check (status in ('draft','running','paused','completed')) default 'draft',
  created_at  timestamptz not null default now()
);

comment on table campaigns is 'Un envío masivo a un conjunto de leads usando una secuencia.';

-- ─── messages ───────────────────────────────────────────────────────────────
create table messages (
  id                  uuid primary key default gen_random_uuid(),
  campaign_id         uuid references campaigns(id),
  contact_id          uuid references contacts(id),
  mailbox_id          uuid references mailboxes(id),
  step_index          int not null,
  angle               text not null,
  subject             text,
  body                text,
  status              text not null check (status in ('drafted','approved','scheduled','sent','bounced','failed','cancelled')) default 'drafted',
  scheduled_for       timestamptz,
  sent_at             timestamptz,
  gmail_message_id    text,
  approved_by         text,
  approved_at         timestamptz,
  edited              boolean not null default false,
  research_snapshot   jsonb,
  generation_cost_usd numeric,
  created_at          timestamptz not null default now()
);

comment on table  messages                       is 'Cada email a enviar o enviado. Estados: drafted (HITL pending) → approved → scheduled → sent. En modo autónomo se salta drafted/approved.';
comment on column messages.step_index            is '0=opening (D+0), 1=reframe, 2=closing. Re-engages usan step_index propio.';
comment on column messages.angle                 is 'opening | reframe | closing | re_engage_60 | re_engage_90.';
comment on column messages.gmail_message_id      is 'Message-ID que devuelve Gmail tras enviar; usado para match de respuestas via In-Reply-To/References.';
comment on column messages.approved_by           is 'Email del humano que aprobó (HITL). NULL si fue autónomo.';
comment on column messages.research_snapshot     is 'Copia del companies.research_data en el momento de la generación, para auditar reproducibilidad.';
comment on column messages.generation_cost_usd   is 'Coste de la llamada al LLM que generó este draft. Acumulable para métricas.';

create index messages_status_scheduledfor_idx on messages(status, scheduled_for);
create index messages_contactid_idx           on messages(contact_id);
create index messages_gmailmessageid_idx      on messages(gmail_message_id);  -- match In-Reply-To/References

-- ─── replies ────────────────────────────────────────────────────────────────
create table replies (
  id                       uuid primary key default gen_random_uuid(),
  message_id               uuid references messages(id),
  contact_id               uuid references contacts(id),
  received_at              timestamptz not null,
  raw_subject              text,
  raw_body                 text,
  category                 text check (category in ('interesado','pide_info','no_ahora','no_interesado','rebote','fuera_oficina','desconocido')),
  is_explicit_optout       boolean not null default false,
  ai_classification_reason text,
  ai_suggested_response    text,
  human_action             text not null check (human_action in ('pendiente','escalado','respondido','archivado','reprogramado')) default 'pendiente',
  created_at               timestamptz not null default now()
);

comment on table  replies                          is 'Respuestas recibidas. is_explicit_optout es transversal — fuerza opt-out permanente con independencia de category (Lección 1).';
comment on column replies.category                 is '6 categorías + desconocido. Acción por categoría en §11.2 + Lección 1.';
comment on column replies.is_explicit_optout       is 'Opt-out detectado por keywords (§11.3). Distinto de "no_interesado" que sí permite re-engage 90d.';
comment on column replies.ai_suggested_response    is 'Draft generado por classify_replies cuando aplica (interesado / pide_info).';
comment on column replies.human_action             is 'Acción humana sobre la respuesta en la bandeja (§12.3).';

create index replies_category_idx        on replies(category);                                  -- ordenación por urgencia en bandeja
create index replies_optout_partial_idx  on replies(contact_id) where is_explicit_optout = true; -- auditoría rápida de cumplimiento

-- ─── events ─────────────────────────────────────────────────────────────────
create table events (
  id         uuid primary key default gen_random_uuid(),
  type       text not null,
  message_id uuid references messages(id),
  contact_id uuid references contacts(id),
  payload    jsonb,
  created_at timestamptz not null default now()
);

comment on table  events       is 'Log append-only de eventos del pipeline. Fuente para métricas y debug.';
comment on column events.type  is 'message_sent | reply_received | bounce | classification_done | etc.';

create index events_type_createdat_idx on events(type, created_at);

-- ════════════════════════════════════════════════════════════════════════════
