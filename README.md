# DEMIN System

Sistema de captación comercial automatizada para **DEMIN Group**, empresa de demoliciones interiores en Madrid.

Un agente de IA actuando como SDR: investiga prospectos, redacta correos genuinamente personalizados (no plantillas), gestiona secuencias y follow-ups, clasifica respuestas y escala lo importante a Gonzalo Pérez (responsable). Bajo identidad de Gonzalo, con dashboard custom para operarlo y web pública institucional. Empieza con humano-en-el-loop, evoluciona a autónomo.

## Documentos clave

Antes de tocar código, leer en este orden:

1. **[`CLAUDE.md`](CLAUDE.md)** — Reglas operativas del proyecto. Se carga automáticamente en cada sesión de Claude Code.
2. **[`tasks/todo.md`](tasks/todo.md)** — Plan completo. Arquitectura, decisiones cerradas, esquema de BD, prompts, fases. Es la fuente de verdad arquitectónica.
3. **[`tasks/lessons.md`](tasks/lessons.md)** — Lecciones capturadas tras correcciones humanas. Patrones a no repetir.
4. **[`docs/dossier_demin.pdf`](docs/dossier_demin.pdf)** — Cómo se presenta DEMIN al mercado.
5. **[`docs/onboarding_demin.pdf`](docs/onboarding_demin.pdf)** — Información del negocio, comisiones, reglas operativas.

## Estructura

```
demin-system/
├── CLAUDE.md               # Reglas operativas (carga automática)
├── README.md               # Este archivo
├── apps/
│   ├── web/                # Sitio público — demingroup.es
│   ├── dashboard/          # Panel autenticado — app.demingroup.es
│   └── workers/            # Pipeline Python (Hetzner)
├── infra/
│   ├── supabase/migrations/
│   └── systemd/
├── tasks/
│   ├── todo.md
│   └── lessons.md
└── docs/
    ├── dossier_demin.pdf
    ├── onboarding_demin.pdf
    └── sabi_export.xlsx
```

## Stack

Next.js 15 + Supabase (Postgres + pgvector + Auth) + Python workers + Gmail API + Anthropic API.

## Estado actual

`Pre-Fase 0`. Plan v1.1 validado (incluye sitio web público en Fase 0). Pendiente de iniciar setup de infra.
