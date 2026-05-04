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

## 2026-05-01 — Lección 7: en Supabase, RLS sin GRANT no es suficiente cuando se accede vía PostgREST

**Contexto:** primer smoke test del route handler `/api/contact` en Bloque C. La REST API de Supabase devolvía `403 — permission denied for table web_leads — Grant the required privileges to the current role with: GRANT SELECT ON public.web_leads TO service_role`. El bug afectaba a las 12 tablas, no solo `web_leads`.

**Causa raíz:** PostgreSQL separa dos capas de control de acceso:

1. **GRANT/REVOKE** — permiso de tabla a nivel de role.
2. **RLS policies** — permiso de fila dentro de la tabla.

RLS NO concede acceso por sí solo. Si no hay `GRANT` previo al role que viene en la conexión, Postgres devuelve `permission denied` antes incluso de evaluar la policy. Las migraciones 01–06 creaban tablas con owner `postgres` y habilitaban RLS, pero nunca hacían `GRANT ... TO service_role, authenticated` — y Postgres no concede privilegios automáticos a otros roles cuando la tabla la crea su owner.

PostgREST (la capa REST de Supabase) recibe la apikey, mapea al role (`anon` | `authenticated` | `service_role`) y hace `SET ROLE`. Sin GRANT, falla aunque el secret key supuestamente "bypassa RLS".

**Por qué `verify_migrations.py` no lo detectó:** ese script conecta como `postgres` directamente al session pooler usando el password de DB. `postgres` es owner y tiene privilegios implícitos. El gap solo aparece al cambiar al canal real de la app (apikey + REST + SET ROLE).

**Regla resultante:**

- **Toda nueva tabla en `public`** debe tener `GRANT ALL TO service_role, authenticated` después del `create table`. La migración `20260501000000_07_grants.sql` aplica esto a las tablas existentes y deja un `alter default privileges in schema public grant all on tables to service_role, authenticated` para que las futuras lo hereden sin tener que repetirlo por tabla.
- `anon` NO recibe grants por defecto. La web pública entra siempre vía `/api/contact` con service_role. Si en el futuro un endpoint sirve datos públicos, GRANT explícito a `anon` sobre la tabla concreta + RLS policy compatible.
- **Ampliar `verify_migrations.py`** con un check que use la REST API y la secret key — ese sería el chequeo que sí detecta este gap. Propuesta: añadir `check_rest_api_grants()` que haga `GET /rest/v1/<tabla>?select=id&limit=0` con `apikey: SUPABASE_SECRET_KEY` para 2-3 tablas representativas. Pendiente de añadir a la suite (anotado, no urgente).
- Tras aplicar GRANTs nuevos, hacer `notify pgrst, 'reload schema';` para refrescar el cache de PostgREST sin esperar el polling.

**Aplicado en:** `infra/supabase/migrations/20260501000000_07_grants.sql`. Aplicada a `demin-dev` y `demin-prod` el 2026-05-01. Ambos entornos verificados con `verify_migrations.py` (5/5) y smoke `curl` REST (HTTP 200 sobre `web_leads` con secret key + round-trip insert/select/delete en dev).

---

## 2026-05-01 — Lección 8: notificaciones tras escritura en BD — best-effort, nunca bloqueantes para la operación principal

**Contexto:** en `/api/contact`, la operación crítica es persistir el lead en `web_leads`. La notificación por email a `CONTACT_NOTIFICATION_EMAIL` vía Resend es valor añadido (Gonzalo se entera al instante en lugar de descubrir el lead horas después al revisar el dashboard) pero NO es la operación crítica.

Si la notificación falla por cualquier razón (timeout de Resend, dominio no verificado, `RESEND_API_KEY` ausente, error 5xx del SDK), el lead NO debe perderse. El cliente debe recibir `200 OK` como si todo hubiera ido bien — porque desde su perspectiva, sí ha ido bien (sus datos están seguros en BD).

**Regla resultante:** cualquier acción "post-escritura" que sea valor añadido pero no crítica (notificaciones, webhooks, llamadas a APIs externas, indexación en motor de búsqueda, etc.) se ejecuta DESPUÉS del INSERT/UPDATE/DELETE crítico, dentro de try/catch, con doble protección:

1. La función helper (`sendLeadNotification`, etc.) tiene su propio try/catch interno y NUNCA lanza — devuelve `null` y loguea con `console.error('[servicio]', error)`.
2. La llamada desde el route handler ENVUELVE de nuevo en try/catch como cinturón-y-tirantes, por si algo escapa (errores de import, runtime errors fuera del SDK, etc.).
3. Cualquier estado de error/warning se loguea con prefijo identificable (ej. `[resend]`, `[webhook]`) para fácil filtrado en logs.
4. Variables de entorno requeridas para la notificación deben validarse al inicio de la función helper. Si falta cualquiera → log warning + return `null` silencioso. NO lanzar excepción. La aplicación debe funcionar aunque el operador no haya configurado todavía las credenciales del servicio de notificación.

**Aplicable a futuras integraciones:** webhooks de eventos, notificaciones a Slack, envíos a sistemas analíticos, llamadas a APIs de terceros (Apollo, etc.) en los workers de Fase 1, escalado de leads a CRM externo si se añade en Fase 2.

**Sub-regla — providers de email transaccional con dominio verificado:** la dirección `From` DEBE coincidir con el dominio donde la API key está autorizada. Si la key está vinculada a `demingroupmadrid.com` (raíz), enviar desde `@send.demingroupmadrid.com` devuelve `403 — API key not authorized to send emails from X`. La aparente flexibilidad de subdominios solo aplica al envelope-from y al SPF/return-path, no al header `From` visible. Revisar la pantalla "API Keys" del provider para verificar la restricción de dominio antes de configurar el remitente. Aplicado tras fallo en primer envío real desde `/api/contact`: el `CONTACT_FROM_EMAIL` pasó de `noreply@send.demingroupmadrid.com` a `noreply@demingroupmadrid.com` el 2026-05-01.

**Sub-regla relacionada:** NO ejecutar `npm run build` mientras el dev server (`npm run dev`) esté corriendo en otra terminal — rompe los archivos temporales de `.next/` y deja la web con `Internal Server Error` hasta que se borra `.next/` y se reinicia. Verificar build en sesión separada o tras parar el dev. Para chequeo de tipos sin tocar `.next/`: `npx tsc --noEmit`.

**Aplicado en:** `apps/web/lib/resend.ts` (helper con try/catch interno + validación de env vars con warn-and-return-null) + `apps/web/app/api/contact/route.ts` (caller, líneas 76-86, try/catch externo y siempre 200 al cliente si el INSERT en `web_leads` fue OK).

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

## 2026-05-04 — Lección 11: los correos archivados de un humano pueden NO reflejar su voz auténtica si son plantilla SaaS genérica — la entrevista verbalizada manda

**Contexto:** tras cargar el KB v1 en sesión 1 (29 abr 2026, basada en
entrevista oral con Gonzalo) quedó en gap el doc 7 (`correos_gonzalo`)
porque Gonzalo no había aportado correos reales. En sesión 2 (4 may 2026)
aporta 10 capturas de correos reales suyos: cold outreach previo al sistema
DEMIN + respuestas reales de prospectos.

Al revisar el material, se detecta que **los correos en frío que Gonzalo
mandaba antes son SOLO 2 plantillas genéricas repetidas sin personalización
por prospecto**. Tienen marcas claras de copy genérico de SaaS de outreach
(probablemente generadas con IA genérica tipo ChatGPT o copiadas de
plantilla de mailchimp/lemlist):

- Asuntos largos con paréntesis del nombre comercial.
- Vocabulario corporativo enlatado: "partner técnico", "fase cero",
  "Cumplimiento Normativo" con mayúscula.
- Bullets en negrita con palabras clave.
- Promesas operativas sin matiz ("retirada y limpieza en el día").
- Sin personalización real al prospecto (solo cambia "[EMPRESA]").
- Sin firma de texto, solo logo de imagen al cierre.

**Comparado con la entrevista verbalizada del 29 abr 2026, todo lo anterior
está en directa contradicción** con cómo Gonzalo dijo que quiere escribir
("ir al grano, sin floruras, sin emojis, sin signos de exclamación, sin
'increíble' ni 'sinergias', referencias concretas al prospecto, no
genéricas").

**Tres lecturas posibles:**

1. Gonzalo escribe diferente de cómo dice que escribe.
2. Estos correos los escribió otra persona o IA por él.
3. Gonzalo cambió de estilo entre los correos archivados y la entrevista.

Sin más información, las tres son posibles. **Independientemente de
cuál sea verdad, la decisión correcta es la misma**: la entrevista
verbalizada deliberadamente con preguntas guiadas y reflexión vale más
como fuente de tono que correos archivados que pudieron escribirse con
prisa, copiarse de plantilla o generarse con IA genérica.

**Decisión aplicada:**

- El doc `tono` del KB v1 NO se actualiza con estos correos. La
  entrevista verbalizada manda.
- El doc 7 (`correos_gonzalo`) NO se construye con estos correos como
  modelo positivo. Sigue en standby permanente.
- Los correos archivados se conservan como **referencia interna**
  (`tasks/correos_referencia_v1.md`), explícitamente marcados como
  referencia negativa: el "antes" del sistema, lo que el proyecto viene
  a desplazar — no modelo a clonar.
- El sistema sigue cumpliendo la decisión D8 del plan §3: redacción IA
  completa por correo, alimentada por KB + research previo, NUNCA
  copia de plantilla.

**Donde SÍ es valioso el material:** las **respuestas reales de prospectos**
a las plantillas de Gonzalo. Esas respuestas son datos de campo no
inventados, especialmente útiles para alimentar `frases_gatillo` del
clasificador `classify_replies.py` en Fase 3. La revisión enriquece
`tasks/kb_objeciones_v1.json` con 7 variantes textuales reales de
"no_ahora amable" y descubre una nueva categoría intermedia
(`obj_interesado_condicional`) que el plan §11.2 no contemplaba.

**Regla resultante:** cuando un humano aporta correos archivados como
material de tono, no se asume automáticamente que esos correos son su
voz auténtica. Hay que revisar si tienen marcas de plantilla genérica,
copy SaaS, IA genérica, o intervención de terceros. Si las tienen, el
material vale como **referencia negativa** y como **patrones de respuesta
del mercado** (cuando incluya respuestas reales de interlocutores), pero
NO como modelo de tono para entrenar al sistema. La fuente autoritativa
de tono sigue siendo la entrevista verbalizada deliberadamente con el
humano, donde se le pregunta cómo QUIERE escribir y se captura su
respuesta consciente.

**Aplicado en:**

- `tasks/correos_referencia_v1.md` (creado en sesión 2, marcado como
  referencia interna, NO contenido de KB).
- `tasks/kb_objeciones_v1.json` (parche en sesión 2: 7 frases gatillo
  nuevas + 1 categoría nueva + 1 acción nueva en tabla_acciones).
- Ningún cambio al doc `tono` ni al `diferenciador` del KB v1.

**Métrica que confirma o desmiente esta decisión:** cuando el sistema
arranque en Fase 2 y mande sus primeros correos generados por LLM,
medir reply rate vs. el reply rate histórico de las plantillas archivadas
de Gonzalo (si hay datos). Si el reply rate del sistema mejora
significativamente, la decisión está validada. Si empeora, revisar si la
entrevista verbalizada tampoco era buen tono y hay que recalibrar
(escenario poco probable pero auditable).

---

## 2026-05-04 — Lección 12: GitHub Organizations + Vercel Hobby = repo público obligatorio

**Contexto:** al conectar el repo `demin-group/demin-system` a Vercel para el primer deploy del Bloque C, Vercel rechaza la conexión porque el repo es privado y vive en una GitHub Organization. Vercel Hobby (plan gratuito) acepta repos privados solo desde cuentas personales individuales; los repos privados de GitHub Organizations requieren Vercel Pro (€20/mes). El techo presupuestario del proyecto (150€/mes) excluye este coste recurrente sin justificación operativa fuerte.

**Regla resultante:** antes del primer deploy a Vercel desde un repo en una GitHub Organization, evaluar:

- **(a) Hacer público el repo** — única alternativa gratis cuando el repo está en una org. Solo seguro si las credenciales viven exclusivamente en variables de entorno y archivos `.env.local` (gitignored), nunca en commits. Verificar con `git log -p | grep -iE 'secret|key|password|token'` antes de cambiar visibilidad. En este proyecto se hizo público por esta razón; las credenciales viven en `apps/web/.env.local` (gitignored vía `.env.*` con whitelist `!.env.example`) y en variables de entorno de Vercel.
- **(b) Migrar el repo a una cuenta personal** de GitHub — mantiene el repo privado en Vercel Hobby. Coste: pierdes la pertenencia a la organización y los permisos compartidos.
- **(c) Pagar Vercel Pro** — €20/mes adicionales, solo si el repo DEBE seguir privado en una org.

**Por qué importa anticiparlo:** descubrirlo durante el deploy detiene el flujo y obliga a tomar una decisión bajo presión. Si la decisión correcta para el proyecto es (a), es preferible haber hecho la auditoría de secretos en el repo con calma antes, no en mitad del deploy.

**Aplicado en:** `demin-group/demin-system` cambiado a público el 2026-05-04 antes del deploy.

---

## 2026-05-04 — Lección 13: coordinación DNS Vercel ↔ proveedor de dominio (Namecheap)

**Contexto:** al apuntar `demingroupmadrid.com` a Vercel, los registros DNS existentes (URL Redirect `@` → parking de Namecheap, CNAME `www` → `parkingpage.namecheap.com`) chocaban con los que Vercel pide (A Record `@` → IP de Vercel, CNAME `www` → `cname.vercel-dns.com`). Vercel mostraba "Invalid Configuration" hasta que los registros viejos se borraron y los nuevos propagaron.

**Regla resultante:** para apuntar un dominio a Vercel desde un proveedor distinto (Namecheap, GoDaddy, Cloudflare, etc.) seguir esta secuencia:

1. **Antes de añadir nada:** identificar y borrar registros existentes que choquen con la configuración pedida por Vercel (típicamente: URL Redirect del apex, CNAME `www` apuntando a parking del proveedor, A Records apuntando a IPs del proveedor).
2. **Añadir los registros nuevos** que Vercel especifica para el dominio concreto. La IP de Vercel para A Records cambia ocasionalmente — siempre copiar la que muestra la pantalla de Domains del proyecto, no fijarla a memoria.
3. **NO mezclar registros viejos y nuevos en paralelo:** algunos proveedores aplican el orden lexicográfico o el primero que respondió, lo que produce resultados intermitentes.
4. **SAVE ALL CHANGES** explícitamente en Namecheap (botón verde arriba a la derecha del panel de DNS). Editar registros sin pulsar Save no aplica los cambios; es un fallo silencioso fácil de pasar.
5. **Verificar propagación con `dnschecker.org/#A/<dominio>`** ANTES de pulsar Refresh en Vercel. La propagación tarda 5-30 min según TTL del registro previo. Refrescar Vercel antes de tiempo entra en bucle de "Invalid Configuration" que confunde sin razón.
6. **Mantener intactos los registros DNS no-web del dominio:** SPF / DKIM / DMARC / MX de Workspace (correo) y registros de Resend (envío transaccional). Solo se tocan los registros que sirven HTTP del apex y `www`.

**Aplicado en:** DNS de `demingroupmadrid.com` reconfigurado en Namecheap el 2026-05-04. Resto de registros (Workspace + Resend `send.demingroupmadrid.com`) intactos. Smoke test E2E del formulario validó que el correo transaccional de Resend siguió funcionando tras el cambio.

---

## 2026-05-04 — Lección 14: variables de entorno en Vercel — Production-only por defecto cuando apuntan a infra real

**Contexto:** al configurar las 6 env vars del proyecto Vercel `demin-web`, el dropdown "Environments" permite marcar `Production` / `Preview` / `Development` independientemente. La tentación cómoda es marcar las tres para que "funcione en todos lados". Esto es incorrecto cuando los valores apuntan a infra real (Supabase prod, Resend con dominio verificado, claves con permisos de escritura).

**Regla resultante:** el toggle Production / Preview / Development debe configurarse intencionalmente, no por defecto:

- **Production-only** es lo correcto cuando las credenciales apuntan a la BD de producción y/o a servicios externos con efectos visibles (envío de emails reales, escrituras en BD prod, llamadas con coste a APIs). Razón: si se activa Preview con los mismos valores, cualquier branch deploy escribiría leads reales en la BD prod y dispararía emails reales a producción desde URLs `*.vercel.app`. No es riesgo teórico — basta que alguien empuje una rama experimental con el formulario auto-rellenado para meter ruido en `web_leads` de prod o spamear al destinatario de notificaciones.
- **Preview / Development separadas** solo si se proveen credenciales independientes (proyecto Supabase de dev, API key de Resend de sandbox/dominio aparte, etc.). Esto multiplica la matriz de configuración por entorno; vale la pena solo cuando se va a usar de verdad.

**Por qué surge el malentendido:** la mayoría de tutoriales online asumen entornos de juguete o usan una sola key para todo. La distinción importa cuando hay infra real detrás. La pregunta correcta a hacerse al marcar el toggle es: "si esta variable se filtra en un branch deploy efímero accesible por URL pública, ¿pasa algo malo?". Si la respuesta es sí, scope Production-only.

**Aplicado en:** las 6 env vars del proyecto Vercel `demin-web` están en scope Production exclusivamente. Cuando se despliegue el dashboard (Bloque B, `app.demingroupmadrid.com`) la decisión se reevaluará: si se quiere un entorno de staging real para probar cambios del dashboard antes de mergear, se creará un set separado apuntando a `demin-dev`.

---

## 2026-05-04 — Lección 15: el nombre de la variable de entorno lo manda el código, no el plan

**Contexto:** durante la configuración de env vars en Vercel se intentó (por inercia del plan inicial y por consejo erróneo de una fuente externa) registrar la URL de Supabase como `SUPABASE_URL`. El código real en `apps/web/lib/supabase.ts:8` lee `process.env.NEXT_PUBLIC_SUPABASE_URL`. Si la variable hubiera quedado como `SUPABASE_URL`, el route handler `/api/contact` habría tirado el error literal "Missing Supabase env vars: set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local" en cuanto recibiera el primer formulario en producción. El error se evitó verificando el código antes de pulsar Save.

**Regla resultante:**

- **Antes de configurar variables en cualquier provider externo (Vercel, Render, Fly, Railway, etc.) verificar el nombre exacto que el código real lee.** Mecánica: `grep -rn "process.env\." apps/web/lib apps/web/app` (o el pattern equivalente del lenguaje) y comparar con la lista de variables que se va a registrar.
- **Documentación, plan, `.env.example` y código pueden divergir.** El código es la fuente de verdad: es lo que se ejecuta en producción. Plan y docs reflejan lo que se quería hacer en algún momento; pueden estar desactualizados.
- **El prefijo `NEXT_PUBLIC_` no es decorativo en Next.js:** determina si la variable se inyecta en el bundle del navegador (con prefijo) o solo está disponible en server (sin prefijo). `NEXT_PUBLIC_SUPABASE_URL` y `SUPABASE_URL` son nombres distintos para Next.js, no alias. La URL de Supabase necesita prefijo `NEXT_PUBLIC_` porque el cliente del navegador puede necesitarla en futuras features (auth, realtime); el `SUPABASE_SERVICE_ROLE_KEY` NO lo lleva nunca porque bypassa RLS y no debe filtrarse al cliente.
- **Cuando una fuente externa (humana o LLM) propone renombrar una env var "porque así es la convención", verificar contra el código antes de aplicar.** Las convenciones varían entre frameworks y entre versiones; el código del repo concreto manda.

**Aplicado en:** durante el deploy del 2026-05-04 se mantuvo `NEXT_PUBLIC_SUPABASE_URL` como Key en Vercel tras verificación con `grep` contra `apps/web/lib/supabase.ts`. El smoke test E2E posterior confirmó que el formulario escribe en `web_leads` de prod sin error.

---

## 2026-05-04 — Lección 16: antes de definir variables de configuración nuevas, leer `.env.example` y la convención que dejó la fase anterior. El código se adapta a la convención del repo, no la convención al código.

**Contexto:** el prompt de Fase 1 — Sprint 1 paso 1 (cimientos `apps/workers/shared/`) especificaba 4 variables de configuración (`SUPABASE_URL_DEV`, `SUPABASE_URL_PROD`, `SUPABASE_DB_PASSWORD_DEV`, `SUPABASE_DB_PASSWORD_PROD`) en un único `.env`, con un helper que reconstruía el connection string a partir de host + password por separado. La auditoría previa a la implementación detectó que la convención ya validada en B7 era distinta: dos ficheros separados (`apps/workers/.env.dev` y `.env.prod`, ambos gitignored), cada uno con `DATABASE_URL` completa (Session pooler con password embebida, Lección 6) más `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y `SUPABASE_ENV` discriminador. `apps/workers/.env.example` documenta este patrón en sus líneas 12-26.

**Corrección humana:** se paró antes de implementar y se propusieron dos opciones — (A) adaptar el spec del prompt a la convención existente, (B) migrar la convención al patrón del prompt. Alberto eligió (A) explícitamente: "Opción A confirmada. Adelante con la implementación bajo la convención existente del repo".

**Regla resultante:** cualquier fichero que toque configuración (`shared/config.py` especialmente, pero también helpers de `db`, `llm` o cualquier worker que lea variables) se diseña LEYENDO primero `apps/workers/.env.example` y los `.env.{ENV}` reales antes de escribir una sola línea de código. Si el spec de un prompt pide una convención distinta a la ya validada, la regla nº 9 del Apéndice A obliga a parar y proponer alternativa antes de reescribir la convención. Aplicable también a otras estructuras consolidadas: schema de BD (§6 todo.md), prompts versionados (`shared/prompts/*.md`, regla nº 8), naming de variables en frontend (Lección 15 ya lo cubre para Next.js / Vercel) y ficheros gitignored ya validados.

**Por qué la regla se sostiene en el tiempo:** las convenciones de configuración se validan UNA vez (en este proyecto, durante B7) y luego cualquier worker, smoke o script confía en que esa forma se mantiene. Romperla obligaría a actualizar `verify_migrations.py`, `.env.example`, los `.env.{dev,prod}` reales en Bitwarden, y cualquier futuro prompt que asuma el patrón viejo. El coste de la migración es mayor que el de adaptar el spec entrante. La regla aplica simétricamente: si en algún momento la convención existente se demuestra mala, se documenta el cambio de forma explícita, se actualiza `.env.example` primero, y luego el código.

**Aplicado en:** `apps/workers/shared/config.py` de Fase 1 — Sprint 1 paso 1. `Settings` carga `apps/workers/.env.{ENV}` según la variable de entorno `ENV` (default `"dev"`). `get_db_url(env)` devuelve la `DATABASE_URL` ya construida con prefijo `postgresql+psycopg://` (SQLAlchemy 2.0 + psycopg3 lo requiere explícito, mientras que el `.env` lo guarda como `postgresql://`). Validación cruzada al cargar: si `SUPABASE_ENV` dentro del fichero no coincide con el `env` solicitado, `ValueError`. Smoke `apps/workers/scripts/smoke_shared.py` valida los 4 pasos (config, db, llm, embed) contra `demin-dev` con la convención existente intacta.

---

## 2026-05-04 — Lección 17: el criterio de validación de un smoke se diseña leyendo el contenido real, no a priori. Si el criterio falla y el contenido es útil, el criterio era el problema.

**Contexto:** primer smoke retrieval del KB en Sprint 1 paso 2. El criterio que dicté al diseñarlo fue "top-1 chunk debe pertenecer a una categoría coherente", con un set de categorías esperadas por query (`expected_cats`) escogidas a priori sin leer los 6 documentos del KB cargados en sesiones 1+2 con Gonzalo. Resultado: VEREDICTO AMARILLO con 0/3 top-1 dentro del set esperado. Inspeccionando los chunks devueltos, eran semánticamente útiles para responder cada query — el RAG funcionaba bien; la categoría no era el indicador correcto. Los 6 docs del KB se solapan temáticamente: el doc `casos_exito` cubre m² y plazos, el doc `diferenciador` cubre tamaño de cliente, el doc `servicios` cubre coordinación con gremios. Ningún top-1 cae limpiamente en una sola categoría porque la realidad del KB no está particionada por categorías sino por temas transversales.

**Corrección humana:** Alberto asumió que el criterio era estrecho y autoría suya, no fallo del RAG. Pidió rediseñar el criterio leyendo qué contienen los 6 docs y construyendo signals desde ese material, no desde la intuición.

**Regla resultante:** cuando se escriba un smoke o un test de validación que evalúa output semántico (retrieval, clasificación, redacción), el criterio se diseña en dos fases:

1. **Fase de lectura del material real.** Antes de escribir una sola línea del criterio, leer los datos contra los que se va a validar — sea KB, fixtures, ground truth, o la realidad operativa que el sistema modela. El criterio se escribe **a posteriori** del material, no a priori.
2. **Fase de diseño del criterio.** El criterio mide la **utilidad** del output para responder al caso de uso real (en RAG: ¿este chunk ayuda al LLM a redactar una respuesta correcta?), no la coincidencia con una etiqueta arbitraria. Mecánicas concretas:
   - **Signals contextuales** (palabras-clave/cifras/términos que cualquier respuesta útil contendría) en lugar de etiquetas categóricas.
   - **Salida auditable**: el smoke debe imprimir preview suficiente del output (~400 chars) + qué signals matchearon, para que un humano pueda validar sin abrir la BD ni el sistema bajo test.
   - **Veredicto cuantitativo + apertura humana**: VERDE/AMARILLO/ROJO con condiciones explícitas (ej. ≥N signals en top-K), pero el log debe permitir al humano cuestionar el veredicto leyendo las trazas.

**Por qué esto no es "tunear el test al resultado":** la diferencia es de qué fuente bebe el criterio. Tunear sería ajustar el threshold para que pase justo este caso. Lo correcto es derivar el threshold del material real una vez, antes de cualquier ejecución, y mantenerlo estable. En este Sprint, los signals por query se escribieron leyendo los 6 docs (no leyendo los outputs del run anterior), y el threshold ≥2 se fijó como mínimo razonable; los runs posteriores podrían fallar y el criterio seguiría intacto.

**Cuándo aplica esta lección además del smoke retrieval:**
- Validación post-generación de correos en Fase 2 (`generate_draft.py` debe rechazar borradores que NO contengan ciertos signals derivados del KB del prospecto, no que coincidan con una plantilla a priori).
- Clasificación de respuestas en Fase 3 (`classify_replies.py` validar contra frases gatillo reales del campo, no contra categorías intuidas — `tasks/kb_objeciones_v1.json` ya sigue este patrón con las 7 frases gatillo de respuestas reales).
- Cualquier test de retrieval que se añada en Fase 4+ con datos reales de prospectos.

**Aplicado en:** `apps/workers/scripts/smoke_kb_retrieval.py` de Fase 1 — Sprint 1 paso 2. Criterio rediseñado tras leer los 6 docs cargados en `kb_documents` (servicios, ICP, objeciones, casos_éxito, tono, diferenciador). Cada query expone `signals: list[str]` (lowercased, sin acentos, prefijos para tolerar variaciones tipo `peque` → pequeña/pequeñas/pequeño) derivados del contenido real. Veredicto: VERDE con 3/3 top-1 superando threshold ≥2 signals; distancias 0.64–0.71. Pivot técnico complementario aplicado en mismo paso: `shared.llm.embed()` añade parámetro `input_type: Literal["document","query"]` para usar embeddings asimétricos del SDK Voyage (ver Lección 16 + ajuste asociado en commit del paso).

---

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
