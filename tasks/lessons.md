# DEMIN — Lecciones capturadas

> Aquí se registran patrones que hemos aprendido tras correcciones humanas o errores. La idea es no repetirlos. Claude Code lee este archivo al inicio de cada sesión.

---

## 2026-04-29 — Lección 1: un "no" del prospecto NO es definitivo

**Contexto:** en el diseño inicial de la matriz de acciones por categoría de respuesta, propuse marcar como excluido permanente al prospecto que respondiera "no interesado".

**Corrección humana:** un "no" hoy ≠ "no" para siempre. Las personas cambian de empresa, los proyectos cambian, las prioridades cambian. Excluir permanentemente al primer rechazo es perezoso comercialmente y deja oportunidades sobre la mesa.

**Regla resultante:**

- `no_interesado` → re-engage automático a +90 días con ángulo distinto (`re_engage_90`).
- `no_ahora` → re-engage automático a +60 días con ángulo `re_engage_60`.
- Solo el **opt-out explícito** (palabras tipo "no me escribáis más", "stop", "RGPD", "AEPD", "denuncia") fuerza exclusión permanente.
- Tras 2 re-engages fallidos: archivo frío con re-intento a +12 meses (no insistir más durante un año).

**Por qué la excepción del opt-out:** legal (LSSI/RGPD: el interés legítimo cae cuando el destinatario manifiesta voluntad contraria; AEPD multa a empresas pequeñas) y reputacional (insistir tras petición de cese genera denuncias de spam que queman la deliverability del dominio).

**Aplicado en:** §11.2 y §11.3 de `tasks/todo.md`. Esquema de BD refleja con `contacts.is_optout` separado de la categoría de respuesta.

---

## 2026-04-29 — Lección 2: drivers y librerías deprecadas — elegir la versión mantenida activamente, no la más conocida del plan

**Contexto:** al definir las dependencias de `apps/workers/pyproject.toml` durante la Fase 0, había que elegir driver de Postgres. El plan §4 / §6 no fija uno concreto, solo dice "SQLAlchemy hacia Supabase". El default mental por costumbre sería `psycopg2`, pero `psycopg2` está en modo mantenimiento desde hace tiempo.

**Decisión:** usar `psycopg3` vía `psycopg[binary]>=3.2.0`, que es la recomendada por el equipo de SQLAlchemy 2.0 y la que recibe desarrollo activo.

**Regla resultante:** cuando el plan no fija una librería concreta y existen alternativas vigentes, elegir la mantenida activamente y dejar nota explícita en el commit o en `lessons.md`. No asumir el default histórico solo porque sea el más conocido. Aplicable más allá de psycopg: cualquier driver, ORM, cliente HTTP, o librería de scraping en la que el plan no se moje.

**Aplicado en:** `apps/workers/pyproject.toml` (Fase 0, B5).

---

## 2026-04-29 — Lección 3: selección de modelo LLM por tipo de tarea — Haiku para clasificación, Sonnet para razonamiento, nunca Opus por defecto

**Contexto:** el plan en `tasks/todo.md` §4 (Stack técnico) dice "Anthropic Claude Sonnet 4.5 (clasificación + redacción + extracción)". Esto es subóptimo en coste — Haiku es ~12× más barato que Sonnet y rinde de sobra en tareas simples de clasificación. Opus es ~5× más caro que Sonnet y reservado para tareas que requieran razonamiento profundo, no para uso operativo. Alberto contrató $25 de créditos en Anthropic Console y queremos optimizar consumo.

**Regla resultante:** en `apps/workers/shared/llm.py` debe existir un mapeo `MODEL_FOR_TASK` que asigne explícitamente el modelo correcto a cada worker. Cualquier llamada a la API debe pasar por ese mapeo — no hardcodear el modelo en cada worker. La configuración también debe ser parametrizable vía `.env` (ej. `ANTHROPIC_MODEL_CLASSIFY`, `ANTHROPIC_MODEL_GENERATE`) para poder cambiar modelos sin redeploy.

Mapeo inicial recomendado:

- `classify_descr` (filtro IA por descripción de empresa) → **Haiku**
- `research_prospect` (extracción JSON de webs) → **Sonnet 4.5**
- `generate_draft` (redacción de correos personalizados) → **Sonnet 4.5**
- `classify_reply` (clasificación de respuestas en 6 categorías) → **Haiku**
- `suggest_response` (redacción sugerida para interesados) → **Sonnet 4.5**
- Cualquier worker nuevo → por defecto Sonnet; justificar en commit si necesita Opus, justificar en commit si baja a Haiku

Estimación de coste mensual con este mapeo en régimen producción (1.500 envíos/mes + research previo + clasificación de respuestas): **~$50/mes**.

**Aplicado en:** pendiente. Se aplicará al construir **B2 (`.env.example`)** y **B5/`shared/llm.py`**. La regla queda registrada ahora para no olvidarla cuando llegue ese momento.

---

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
