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
- `research_prospect` (extracción JSON de webs) → **Sonnet 4.6**
- `generate_draft` (redacción de correos personalizados) → **Sonnet 4.6**
- `classify_reply` (clasificación de respuestas en 6 categorías) → **Haiku**
- `suggest_response` (redacción sugerida para interesados) → **Sonnet 4.6**
- Cualquier worker nuevo → por defecto Sonnet; justificar en commit si necesita Opus, justificar en commit si baja a Haiku

Estimación de coste mensual con este mapeo en régimen producción (1.500 envíos/mes + research previo + clasificación de respuestas): **~$50/mes**.

**Aplicado en:** pendiente. Se aplicará al construir **B2 (`.env.example`)** y **B5/`shared/llm.py`**. La regla queda registrada ahora para no olvidarla cuando llegue ese momento.

---

## 2026-04-29 — Lección 4: decisiones operativas de outreach en Bloque A — 1 buzón inicial + warm standby, cadencia espaciada, caps conservadores, Postmaster Tools como monitor oficial

**Contexto:** durante el setup del Bloque A, tras analizar trade-offs de coste, gestión y deliverability, se han revisado varias decisiones del plan §9 (Sistema de envío). El plan original era ambicioso (3 buzones desde día 1, cadencia D+0/D+4/D+10, cap 50/día). La realidad operativa que se ha decidido es más conservadora.

**Decisiones aplicables cuando se construya B2 (`.env.example`) y la Fase 2 (envío real):**

### 1. Buzones (modifica §9.1 cuando se actualice el plan)

- **Activo desde día 1:** `gonzalo.perez@demingroupmadrid.com`
- **Warm standby (crear el día 14):** `contacto@demingroupmadrid.com` con warmup en background, sin envíos en frío hasta que degrade el principal
- **Eliminado del plan:** `hola@` (no se crea salvo crecimiento futuro)

### 2. Cadencia (modifica §9.2)

Pasos de la sequence `demin_v1`:

```json
[
  {"day": 0,  "angle": "opening"},
  {"day": 12, "angle": "reframe"},
  {"day": 30, "angle": "closing"}
]
```

Razón: 1 buzón único soporta cadencia más lenta sin saturarse ni perder coherencia de remitente.

### 3. Caps (modifica §9.3)

- Cap inicial post-warmup: **10/día** semana 1
- Rampa: **+5/semana**
- Cap máximo: **40/día** (no 50)

### 4. Monitorización (modifica §9.4)

- **Google Postmaster Tools** como fuente oficial de deliverability del dominio. Configuración: registro TXT en DNS de Namecheap para verificar el dominio en Postmaster.
- **Lemwarm** sigue siendo el monitor operativo continuo.
- Auto-pausa thresholds sin cambios respecto al plan: bounce >2%, spam >0.1%, score amarillo en Lemwarm.

### 5. Notación del remitente

Las referencias en plantillas, prompts y firma deben usar **`gonzalo.perez@demingroupmadrid.com`** (con punto, no `gonzalo@` ni `g.perez@`). Display name **"Gonzalo Pérez"**.

**Aplicado en:** pendiente. Se aplicará al construir **B2** y después en Fase 2 (Sistema de envío). La regla queda registrada ahora para no olvidarla.

---

## 2026-04-29 — Lección 5: warnings de Lemwarm (A record + reverse DNS) confirman que la web pública es prerequisito real para Fase 2, no nice-to-have

**Contexto:** al activar Lemwarm para `gonzalo.perez@demingroupmadrid.com`, los DNS checks dieron MX/SPF/DMARC en verde y tres warnings:

- **A record:** "No web server is responding" — el dominio apunta al parking de Namecheap (IP `192.64.119.212`).
- **Reverse DNS:** `ENOTFOUND` para esa misma IP.
- **Custom Tracking Domain:** not configured.

**Regla resultante:**

- **Bloque C** (web pública en `demingroupmadrid.com` vía Vercel) deja de ser opcional. Es prerequisito de Fase 2 — sin web viva, A record y rDNS quedan rotos y degradan trust signals con los proveedores de email. Vercel resolverá ambos automáticamente al desplegar.
- **Custom Tracking Domain NO se configura:** no aplica a Lemwarm puro (sin links rastreados) ni a nuestro envío real, que va por Gmail API directo (no vía Lemlist). Decisión cerrada.
- El warmup de Lemwarm corre en paralelo durante las 2-3 semanas de maduración; al final, la web debe estar ya desplegada.

**Aplicado en:** pendiente — Bloque C entra al hot path tras este handoff.

---

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
