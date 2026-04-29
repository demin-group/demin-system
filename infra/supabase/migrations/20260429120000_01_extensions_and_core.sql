-- ════════════════════════════════════════════════════════════════════════════
-- 20260429120000_01_extensions_and_core.sql
--
-- Extensiones necesarias y tablas core del pipeline de captación:
--   companies: empresas que vienen de Sabi + enriquecimiento
--   contacts:  decisores dentro de cada empresa
--
-- Fuente: tasks/todo.md §6.1
-- ════════════════════════════════════════════════════════════════════════════

create extension if not exists pgcrypto;  -- gen_random_uuid()
create extension if not exists vector;    -- embeddings del KB (uso en migration 04)

-- ─── companies ──────────────────────────────────────────────────────────────
create table companies (
  id               uuid primary key default gen_random_uuid(),
  nif              text unique not null,
  nombre           text not null,
  localidad        text,
  descripcion      text,
  web              text,
  rev_y0_keur      numeric,
  rev_y1_keur      numeric,
  rev_growth_pct   numeric,
  tier             text check (tier in ('T1','T2','T3','T4','descartado')),
  ia_fit           text check (ia_fit in ('fit','no_fit','dudoso','pendiente')) default 'pendiente',
  ia_fit_reason    text,
  research_done_at timestamptz,
  research_data    jsonb,
  created_at       timestamptz not null default now()
);

comment on table  companies                  is 'Empresas candidatas. Origen: Excel de Sabi (5.619) + enriquecimiento (Apollo Tier 4). Filtradas por reglas de tier y clasificador IA antes de pasar al outreach.';
comment on column companies.nif              is 'Identificador fiscal único; clave de upsert al ingestar Sabi.';
comment on column companies.descripcion      is 'Descripción de actividad de Sabi; input del filtro IA classify_descr.';
comment on column companies.web              is 'Web pública de la empresa (Sabi o enriquecida). Input de research_prospect.';
comment on column companies.rev_y0_keur      is 'Ingresos último año disponible, en miles de euros (k€).';
comment on column companies.rev_growth_pct   is 'Crecimiento de ingresos y0 vs y1 en porcentaje.';
comment on column companies.tier             is 'T1-T4 según reglas §8.2 (revenue + has_web). "descartado" si fuera de rango operativo.';
comment on column companies.ia_fit           is 'Resultado del filtro IA classify_descr (§8.3). "pendiente" hasta que el worker lo procese.';
comment on column companies.ia_fit_reason    is 'Una frase de auditoría que justifica el ia_fit (devuelta por el LLM).';
comment on column companies.research_data    is 'JSON estructurado del worker research_prospect (§8.4); hooks de personalización + señales de la web.';

create index companies_tier_iafit_idx on companies(tier, ia_fit);

-- ─── contacts ───────────────────────────────────────────────────────────────
create table contacts (
  id              uuid primary key default gen_random_uuid(),
  company_id      uuid not null references companies(id) on delete cascade,
  email           text not null,
  email_verified  boolean not null default false,
  email_source    text check (email_source in ('sabi','web_scrape','apollo','manual')),
  nombre          text,
  cargo           text,
  linkedin_url    text,
  is_primary      boolean not null default false,
  is_optout       boolean not null default false,
  optout_at       timestamptz,
  optout_reason   text,
  created_at      timestamptz not null default now(),
  unique (company_id, email)
);

comment on table  contacts                is 'Decisores dentro de cada empresa. is_optout transversal sobrevive a cambios de categoría de respuesta (Lección 1).';
comment on column contacts.email_source   is 'De dónde salió el email: sabi, scraping de web, Apollo, o entrada manual.';
comment on column contacts.is_primary     is 'Indica el destinatario principal por empresa cuando hay varios contactos.';
comment on column contacts.is_optout      is 'Opt-out PERMANENTE. Regla nº 2 del Apéndice A — exclusión definitiva. Distinto de la categoría "no_interesado" que sí permite re-engage.';

create index contacts_emailverified_optout_idx on contacts(email_verified, is_optout);
create index contacts_email_idx                on contacts(email);  -- lookup rápido en match de respuestas y rebotes

-- ════════════════════════════════════════════════════════════════════════════
