# DEMIN System

Sistema de captación comercial automatizada para **DEMIN Group**, empresa de demoliciones interiores en Madrid.

Un agente de IA actuando como SDR: investiga prospectos, redacta correos genuinamente personalizados (no plantillas), gestiona secuencias y follow-ups, clasifica respuestas y escala lo importante a Gonzalo Pérez (responsable). Bajo identidad de Gonzalo, con dashboard custom para operarlo y web pública institucional. Empieza con humano-en-el-loop, evoluciona a autónomo.

## Documentos clave

Antes de tocar código, leer en este orden:

1. **[`CLAUDE.md`](CLAUDE.md)** — Reglas operativas del proyecto. Se carga automáticamente en cada sesión de Claude Code.
2. **[`tasks/todo.md`](tasks/todo.md)** — Plan completo. Arquitectura, decisiones cerradas, esquema de BD, prompts, fases. Es la fuente de verdad arquitectónica.
3. **[`tasks/lessons.md`](tasks/lessons.md)** — Lecciones capturadas tras correcciones humanas. Patrones a no repetir.
4. **[`docs/dossier_demin.pdf`](docs/dossier_demin.pdf)** — Cómo se presenta DEMIN al mercado.
5. **`onboarding_demin.pdf`** — Información del negocio, comisiones, reglas operativas. **Vive fuera del repo** (un nivel por encima) por contener datos confidenciales y credenciales. Pedir acceso al responsable del proyecto.

## Estructura

```
demin-system/
├── CLAUDE.md                   # Reglas operativas (carga automática)
├── README.md                   # Este archivo
├── apps/
│   ├── web/                    # Sitio público — demingroup.es (Next.js 15)
│   ├── dashboard/              # Panel autenticado — app.demingroup.es (pendiente B3)
│   └── workers/                # Pipeline Python (uv + Python 3.11)
├── infra/
│   ├── supabase/migrations/    # Schema SQL (pendiente B6)
│   └── systemd/                # Worker units (Fase 1)
├── tasks/
│   ├── todo.md                 # Plan maestro
│   └── lessons.md              # Lecciones capturadas
└── docs/
    ├── dossier_demin.pdf
    ├── leads_demin_segmentados.xlsx
    ├── logo_demin_group.jpg
    └── sabi_export.xlsx
```

## Stack

- **Frontend** (web pública + dashboard): Next.js 15 + TypeScript + Tailwind CSS v4 + shadcn/ui (solo dashboard)
- **Backend / DB**: Supabase Postgres con `pgvector` para RAG · Supabase Auth (magic link) · Supabase Edge Functions
- **Workers**: Python 3.11 con `uv` · SQLAlchemy + psycopg3 hacia Supabase · cola de jobs en Postgres (sin Redis)
- **LLM**: Anthropic Claude Sonnet 4.5 (clasificación + redacción + extracción)
- **Embeddings**: Voyage AI `voyage-multilingual-2` (1024 dim)
- **Email**: Gmail API + Google Workspace + dominio propio · warmup vía Lemwarm
- **Scraping**: `httpx` + `selectolax` + `tldextract` · Playwright como fallback JS
- **Enriquecimiento**: Apollo.io API (Tier 4 sin web)
- **Hosting**: Vercel (web + dashboard) · Hetzner CX22 (workers, Fase 1+)
- **Coste objetivo**: ~110-130€/mes (techo 150€)

## Setup local

### Requisitos

- Node.js ≥ 20 (probado con v24)
- npm ≥ 10
- [`uv`](https://docs.astral.sh/uv/) ≥ 0.5 (gestor de Python)
- Git

uv instala Python 3.11 managed automáticamente la primera vez que se hace `uv sync`; no hace falta instalar Python a mano.

### Web pública (`apps/web/`)

```bash
cd apps/web
npm install
npm run dev          # http://localhost:3000 (Turbopack)
npm run build        # build de producción
npm run lint
```

### Workers (`apps/workers/`)

```bash
cd apps/workers
uv sync              # crea venv + instala Python 3.11 managed + deps + lockfile
uv run pytest        # tests (cuando los haya)
uv run ruff check .  # linter
uv run mypy .        # type check

# Ejecutar un worker concreto:
uv run python -m pipeline.ingest_sabi
uv run python -m kb.embed_documents
```

### Variables de entorno

Cada subproyecto tiene su propio `.env.example` versionado en repo:

- **`apps/workers/.env.example`** — Supabase + Anthropic (mapeo de modelo por tarea según Lección 3 de `tasks/lessons.md`) + Voyage + Apollo + Gmail OAuth + mailbox config + Postmaster.
- **`apps/dashboard/.env.example`** — Supabase (publishable + secret) + URL pública del panel + `ALLOWED_EMAILS` para auth allowlist.
- **`apps/web/.env.example`** — Supabase (publishable + secret) + email de notificación del formulario de contacto.

Convención: cada entorno copia su `.env.example` a `.env.dev` o `.env.prod` localmente y rellena los placeholders con valores reales tomados de **Bitwarden**. Nunca commitees `.env`, `.env.dev`, `.env.prod` ni cualquier `.env.*` que no sea el template — el `.gitignore` lo enforce con `.env / .env.* / !.env.example` en raíz, `apps/web/` y (cuando exista) `apps/dashboard/`. La regla nº 5 del Apéndice A es no negociable: variables de entorno o Supabase Vault.

## Estado actual

**Fase 0 en curso.** Avance:

- [x] Estructura del repo y reorganización inicial
- [x] B1 — placeholders de monorepo (`apps/dashboard/`, `infra/`)
- [x] B4 — `apps/web/` con Next.js 15.5.15 + TS + Tailwind v4 (sin shadcn)
- [x] B5 — `apps/workers/` con `uv` + Python 3.11 + estructura de módulos completa
- [x] B8 — este README
- [ ] A1-A11 — Bloque A (cuentas externas, dominio, DNS, warmup) — bloqueado por humanos
- [ ] B2 — `.env.example` (depende de A)
- [ ] B3 — `apps/dashboard/` (depende de A7 Supabase + decisión de monorepo workspaces)
- [ ] B6/B7 — Migrations Supabase (depende de A7)
- [ ] B9 — GitHub remote + Vercel (depende de A9)
- [ ] Bloque C — Web pública (depende de A1, A2, A4)
- [ ] Bloque D — Contenido KB de Gonzalo (depende de sesión con Gonzalo)

Ver `tasks/todo.md` §14 para el detalle de fases (Fase 0 setup → Fase 1 pipeline → Fase 2 envío + HITL → Fase 3 respuestas + autonomía).
