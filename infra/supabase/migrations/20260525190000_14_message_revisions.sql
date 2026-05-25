-- ════════════════════════════════════════════════════════════════════════════
-- 20260525190000_14_message_revisions.sql
--
-- Sesion 2026-05-25 -- Bloque 7 captura de aprendizaje HITL.
--
-- El sistema actual NO captura QUE edita Gonzalo en /approval-queue ni POR QUE
-- rechaza un draft. Sin esa senal estructurada no podemos mejorar prompts.
-- Esta migracion crea `message_revisions` para ese fin (tabla separada de
-- `messages` para soportar multiples revisiones por mensaje y mantener
-- `messages` limpia).
--
-- Tipos de revision:
-- - 'edit'   : Gonzalo editó subject/body antes de aprobar. body_before/after
--              + subject_before/after capturan el delta. PM analiza con SQL
--              que patrones emerge en sus ediciones.
-- - 'reject' : Gonzalo rechazó el draft. rejection_category + opcional
--              rejection_reason_text capturan el por qué. message queda
--              status='cancelled'.
--
-- Categorias de rechazo (limitadas; "otro" + textarea para edge cases):
--   tono                : tono del LLM no encaja con voz DEMIN.
--   datos_incorrectos   : research incorrecto, hooks alucinados.
--   no_icp              : empresa no es ICP (falso positivo de classify_descr).
--   longitud            : muy largo o muy corto.
--   asunto              : asunto malo (subject especifico).
--   duplicado_contacto  : ya hay otro contact del mismo dominio.
--   otro                : describe en rejection_reason_text.
--
-- Consulta tipica (PM ad-hoc): "ultimas 50 ediciones, ver patrones":
--   select revision_type, rejection_category, subject_before, subject_after,
--          body_before, body_after, rejection_reason_text, revised_by
--   from message_revisions
--   order by revised_at desc limit 50;
--
-- PM NO consulta esto en UI. Pantalla /learnings y metricas quedan para
-- Sprint posterior cuando haya volumen suficiente (>20-30 revisiones).
-- ════════════════════════════════════════════════════════════════════════════

create table if not exists message_revisions (
    id                    uuid primary key default gen_random_uuid(),
    message_id            uuid not null references messages(id) on delete cascade,
    revision_type         text not null check (revision_type in ('edit', 'reject')),
    -- Para 'edit': ambos campos rellenos (before del DB, after de la edicion).
    -- Para 'reject': before del DB, after null.
    body_before           text,
    body_after            text,
    subject_before        text,
    subject_after         text,
    -- Solo para 'reject':
    rejection_category    text check (
        rejection_category is null or rejection_category in (
            'tono', 'datos_incorrectos', 'no_icp', 'longitud',
            'asunto', 'duplicado_contacto', 'otro'
        )
    ),
    rejection_reason_text text,
    -- Email del humano que revisó (Gonzalo o Alberto o futuro user).
    revised_by            text not null,
    revised_at            timestamptz not null default now(),
    -- Consistencia tipo-categoria: edit no lleva categoria, reject sí.
    constraint chk_edit_no_category
        check (revision_type <> 'edit' or rejection_category is null),
    constraint chk_reject_has_category
        check (revision_type <> 'reject' or rejection_category is not null)
);

create index if not exists ix_message_revisions_message_id
    on message_revisions(message_id);
create index if not exists ix_message_revisions_revised_at
    on message_revisions(revised_at desc);
create index if not exists ix_message_revisions_rejection_category
    on message_revisions(rejection_category)
    where rejection_category is not null;

comment on table message_revisions is
    'Captura HITL para aprendizaje: que edito Gonzalo / por que rechazo. '
    'Bloque 7 sesion 2026-05-25. PM consulta con SQL ad-hoc; sin UI de '
    'agregados hasta volumen suficiente.';

-- GRANTs (alineado con Lección 7 -- service_role + authenticated)
grant all on table message_revisions to service_role, authenticated;
