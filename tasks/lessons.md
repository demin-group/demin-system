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

## 2026-04-29 — Lección 6: Supabase Direct Connection es IPv6-only en free tier — usar Session Pooler para psycopg desde Windows

**Contexto:** al aplicar las migrations de B7 desde Windows, `db.<project-ref>.supabase.co:5432` falló con `getaddrinfo failed` (DNS no resuelve). Causa raíz: Supabase deprecó IPv4 para direct connections en el free tier; solo publican AAAA (IPv6). El Windows 11 del dev no tiene routing IPv6 funcional hacia internet, así que la resolución cae.

**Corrección humana:** [implícita por la propia documentación de Supabase] — cambiar a Session pooler (puerto 5432 con hostname `aws-N-<region>.pooler.supabase.com`, que sí publica A records).

**Regla resultante:**

- **Para psycopg / SQLAlchemy en local:** usar siempre **Session pooler** (no Direct, no Transaction). Formato:
  ```
  postgresql://postgres.<project-ref>:<password>@aws-N-<region>.pooler.supabase.com:5432/postgres
  ```
- **NO usar Transaction pooler (puerto 6543):** rompe `SET ROLE`, prepared statements y otras features de sesión que `verify_migrations.py` necesita.
- **NO usar Direct connection (`db.<ref>.supabase.co:5432`):** IPv6-only, falla desde redes sin ruta v6.
- Las regiones varían por proyecto: dev (`oribmklyxzhpqcpmqsce`) está en `aws-0-eu-west-1`, prod (`stxicalzpwrcjpaqdkdb`) está en `aws-1-eu-west-3`. Se obtienen del Dashboard → Connect → Session pooler.
- El placeholder `[YOUR-PASSWORD]` que Supabase mete en la URL del Dashboard hay que sustituirlo manualmente por el password real (literal entre corchetes, no es interpolación).

**Aplicado en:** B7 — `apps/workers/.env.dev` y `.env.prod` configurados con Session pooler. 5/5 checks pasaron en ambos entornos.

---

## 2026-04-29 — Lección 9: el KB capturado en sesión 1 desvía del plan en 6 puntos — la realidad de Gonzalo manda

**Contexto:** sesión de KB con Gonzalo (29 abr 2026, 32 min de entrevista efectiva).
Tras procesar la transcripción y construir los 6 documentos del KB inicial, se han
detectado seis puntos en los que el plan §1, §11, §13 y §15 contienen supuestos
que no se sostienen contra la realidad operativa que Gonzalo verbalizó. La regla
del proyecto es clara: **el KB refleja la realidad de DEMIN, no el supuesto del
plan**. Cuando hay conflicto, se actualiza el plan, no el KB.

**Desviaciones detectadas y resueltas en el KB:**

1. **Sweet spot de presupuesto**. Plan §1.2: 25k-50k€. Realidad de Gonzalo: 5k€
   compensa y hasta 100k€ es cómodo. Por encima de 100k€ "habría que estudiarlo"
   (con flexibilidad confirmada — caso Montalbán de 230k€ en seguimiento activo).
   El KB recoge 5k-100k€ como rango operativo.

2. **ICP — perfiles respaldados por experiencia**. Plan §1.3: 5 perfiles
   (constructoras, promotoras, arquitectos que ejecutan, reformistas medianos,
   administradores de fincas). Realidad: cuando se le pregunta a Gonzalo por sus
   mejores clientes y su cliente ideal, **menciona solo constructoras**. No
   descarta los demás, pero no los respalda. El KB es honesto sobre esto. El
   sistema puede seguir prospectando a los 5 perfiles en Fase 1, pero los correos
   no fingen experiencia con perfiles donde no la hay.

3. **Sectores excluidos**. Plan §1.3 solo veta instaladores especialistas como
   out-of-ICP. Gonzalo añade tres exclusiones por política propia: obras
   públicas (trabas documentales), demoliciones de fachadas (no monta
   andamios), obras que requieran plantilla > 20 personas. El KB lo recoge en
   `servicios` y `icp`. El prompt `classify_descr.md` debe incorporar estas
   tres exclusiones cuando se construya en Fase 1.

4. **Capacidad operativa NO es restricción del embudo**. Plan §15.2 implica que
   el objetivo "≥3-5 reuniones cerradas/mes" alinea con la capacidad operativa
   de obra (3 obras/mes según Gonzalo). Decisión actualizada del usuario:
   **el sistema persigue maximizar reuniones cerradas, sin techo**. La
   capacidad operativa de obra es restricción aguas abajo gestionada por
   Gonzalo (rechazar, posponer, subcontratar parcialmente, crecer en plantilla),
   nunca por el sistema. El sistema no modula caps de envío, cadencias ni
   ángulos en función de obras absorbidas/mes.

5. **Empresa joven vs. dossier "años de experiencia"**. El dossier comercial
   (página 2) afirma "años de experiencia en el sector". La realidad según
   Gonzalo: empresa creada en 2020, él como autónomo desde 2024 — ~2 años de
   actividad real con su propia operación, con parones. El KB (`tono` y
   `diferenciador`) capitaliza esta juventud como activo, en línea con la
   frase real del cliente que cerró: "la confianza que veía en un chico joven
   lanzándose". **Tensión a resolver con Gonzalo**: o se actualiza el dossier
   para alinearse con el KB, o se ajusta el KB. Mi recomendación es lo primero:
   el dossier es texto cerrado y reescribible; el KB tiene que reflejar la
   realidad operativa. Pendiente de decisión humana.

6. **Objetivo de tiempo de Gonzalo en Fase 3 autónoma**. Plan §15.2:
   "<30 min/día". Realidad operativa con HITL amplio permanente: ~60
   min/día. El sistema persigue maximizar reuniones cerradas, no minimizar
   tiempo de Gonzalo. La métrica §15.2 se ajusta cuando se actualice el plan.

**Reglas resultantes (aplicables en sesiones futuras y al construir Fases 1-3):**

- **Cuando el plan y el KB diverjan, manda el KB**, salvo que la divergencia
  introduzca un riesgo (legal, operativo, de coste) que el KB no haya considerado.
  En ese caso: parar y preguntar a humano.
- **Antes de construir un prompt o un worker**, contrastar contra el KB
  capturado en sesiones de entrevista, no solo contra `todo.md`. Si el KB
  contradice el plan, aplicar el KB y registrar la desviación.
- **El KB es la fuente de verdad de la realidad de DEMIN**. El plan es la
  fuente de verdad de la arquitectura técnica. Son capas distintas. El plan
  debe actualizarse cuando el KB revele realidad contradictoria.

**Aplicado en:** los 6 documentos del KB inicial generados el 2026-04-29
(servicios, icp, objeciones, casos_exito, tono, diferenciador). Documento 7
(correos_gonzalo) en standby permanente hasta que Gonzalo aporte material por
iniciativa propia.

**Acciones derivadas pendientes:**

- Actualizar `tasks/todo.md` §1.2, §1.3, §11.2, §15.2, §13 y log §19 con las
  seis desviaciones de arriba — al cerrar la carga de KB en sesión específica
  (paso 8 del prompt `claude_code_prompt_kb_carga.md`).
- **Decisión operativa del humano (2026-04-29):** NO habrá 2ª ronda de captura
  con Gonzalo. El KB v1 se cierra con el material de la sesión 1. Los gaps
  quedan documentados en `tasks/gaps_conocidos_kb_v1.md` para trazabilidad y
  por si en algún momento Gonzalo aporta material por iniciativa propia, pero
  NO son un to-do activo.
- Decisión humana sobre dossier comercial vs. línea editorial del KB
  (punto 5 de las desviaciones).

---

## 2026-04-29 — Lección 10: la cola de respuestas en v1 será mayoritariamente HITL — es la consecuencia honesta de tener objeciones poco trabajadas

**Contexto:** al construir el JSON estructurado de objeciones para
`classify_replies.py` (Fase 3), se observa que solo 2 de 9 objeciones
clásicas tienen respuesta validada por Gonzalo (precio y presupuesto sin
visita). Las otras 7 quedan sin respuesta tipo. La tentación pereza-comercial
sería rellenar los huecos con respuestas plausibles inventadas por el LLM
basándose en el resto del KB.

**Decisión:** **NO se rellenan**. Las 7 objeciones sin respuesta validada se
marcan en el JSON como `tiene_respuesta_validada: false` con
`accion_sistema: "escalar_a_gonzalo"` o equivalente. Esto significa que en la
Fase 3 inicial, ~80% de la cola de respuestas pasará por HITL en lugar del
~30% que sugiere el plan §11.2.

**Por qué la regla:**

- **Apéndice A regla nº 3**: "Nunca inventes datos del prospecto. Si el
  research no lo dice, no lo digas." Aplicable también al revés: si Gonzalo
  no dijo cómo responde a una objeción, el sistema no la inventa.
- **Apéndice A regla nº 4**: "Nunca prometas plazos, precios o disponibilidad
  en nombre de DEMIN." Una respuesta inventada a "no sé si encajáis con
  nuestro tamaño" puede contener implícitamente compromisos no validados.
- **Coste de error operativo**: una respuesta automática mal calibrada en
  frío es indistinguible de spam corporativo. Mejor escalar de más que
  generar fricción que queme la deliverability del dominio.

**Regla resultante:** cuando el material capturado del humano sea
insuficiente para responder con criterio, el sistema escala. NO improvisa
para "rellenar" el flujo automático. La carga de HITL es una métrica que
baja cuando se hacen sesiones de captura adicionales con Gonzalo, no
cuando el LLM redacta más confiado.

**Aplicado en:** JSON estructurado de objeciones (`tasks/kb_objeciones_v1.json`)
generado el 2026-04-29. Implementación en
`apps/workers/replies/classify_replies.py` y `handle_actions.py` cuando se
construya Fase 3.

**Métrica a vigilar:** porcentaje de respuestas escaladas a HITL en las
primeras 4 semanas de Fase 3. Si sigue por encima del 60% de forma
sostenida, NO relajar la regla — escalar es el comportamiento correcto
cuando no hay material validado.

---

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
