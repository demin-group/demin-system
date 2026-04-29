"""Cliente Anthropic para clasificación, redacción y extracción.

Modelo: Claude Sonnet 4.5 (default según `tasks/todo.md` §4). Configurable vía
`shared.config`. Centraliza retries, backoff exponencial, conteo de tokens y
trazabilidad de coste por llamada (para acumular en `messages.generation_cost_usd`).

Los prompts se cargan desde `shared/prompts/*.md` — versionados en repo
(regla nº 8 del Apéndice A), nunca inline.

Pendiente de implementar en Fase 1.
"""
