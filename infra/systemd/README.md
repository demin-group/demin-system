# infra/systemd

Unidades systemd para los workers Python desplegados en Hetzner.

Pendiente de poblar en **Fase 1**, cuando se arranque la VPS. Una unidad por worker (`*.service` + posiblemente `*.timer` para cron-like). Los workers se especifican en `tasks/todo.md` §5 (`apps/workers/pipeline/`, `outreach/`, `replies/`, `monitoring/`, `kb/`).
