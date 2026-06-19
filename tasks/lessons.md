# DEMIN — Lecciones capturadas

> Aquí se registran patrones que hemos aprendido tras correcciones humanas o errores. La idea es no repetirlos. Claude Code lee este archivo al inicio de cada sesión.

> **Convención de fechas:** la fecha en la cabecera de cada Lección N es la **fecha del evento documentado**, NO la fecha de captura en el archivo. Por eso una Lección con fecha posterior puede aparecer físicamente antes que otra con fecha anterior (ej. Lecciones 7-8 con fecha 2026-05-01 aparecen antes que Lecciones 9-10 con fecha 2026-04-29 — las 9-10 se añadieron en sesión posterior pero documentan eventos anteriores). El orden lineal del archivo es siempre por número de Lección.

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

## 2026-05-04 — Lección 18: SABI exporta cuentas consolidadas + individuales para algunas empresas; deduplicar por "tier más alto gana"

**Contexto:** primera ingesta del Excel `docs/sabi_export.xlsx` durante Sprint 2 paso 1 (ingest_sabi). El plan §6.1 declara `nif unique not null` en `companies`. Auditoría previa a la implementación detectó **41 NIFs duplicados** en las 5.619 filas brutas (5.578 únicos). Los 41 son siempre exactamente 2 ocurrencias y la misma empresa aparece con cifras radicalmente distintas en cada fila — ej. ACCIONA SA: 19.190M€ vs 489M€; FERROVIAL INVERSIONES: 3.635M€ vs 1.17M€. Hipótesis: SABI exporta cuentas consolidadas (grupo) + cuentas individuales (filial operativa) para empresas que han presentado ambos tipos de depósito contable.

**Decisión humana (2026-05-04):** Opción A confirmada — heurística "tier más alto gana, empate → primera ocurrencia". La cifra individual de filial pesa más que la consolidada del grupo para un B2B local como DEMIN: la filial es la entidad que decide y firma una contratación de obra; la consolidada es contabilidad agregada del grupo y normalmente cae fuera de rango (>20M€) por tamaño total acumulado.

**Regla resultante:**

- **Cuando un export externo declarado `unique` no lo es**, parar antes de tocar BD y diagnosticar el patrón: número de duplicados, si son filas idénticas (deduplicación trivial) o filas distintas (decisión sensible), e impacto sobre la salida del worker (en este caso: ¿cuántos duplicados afectan al tier final?).
- **Deduplicar con criterio operativo, no técnico**. "Quedarse con la primera fila" o "última fila" son criterios técnicos arbitrarios; "tier más alto gana" deriva del objetivo del worker (encontrar empresas accionables) y produce salidas explicables.
- **Documentar la decisión en código** con función dedicada (`dedup_by_nif()`) que devuelva trazabilidad de las decisiones tomadas (qué tier conservó vs cuál descartó por NIF) — útil para auditar después si Gonzalo pregunta por una empresa concreta.
- **Idempotencia y heurística determinista van juntas**: la heurística debe ser estable entre ejecuciones (mismo Excel → misma salida). Si la heurística usa orden de aparición como tiebreaker, el orden de iteración del Excel se respeta.
- **El plan se actualiza con el dato real** (§8.1 pasa de "5.619 filas" a "5.619 filas brutas → 5.578 NIFs únicos tras dedup") en lugar de fingir que el dato bruto es la realidad. La actualización del plan refleja el conocimiento adquirido.

**Aplicado en:** `apps/workers/pipeline/ingest_sabi.py` función `dedup_by_nif()` con tabla `TIER_PRIORITY` (T1=4, T2=3, T3=2, T4=1, descartado=0). Smoke `apps/workers/scripts/smoke_ingest_sabi.py` valida que (a) ingesta limpia produce 5.578 filas, (b) distribución por tier dentro de ±20% del plan §8.2, (c) re-ejecutar no cambia counts (idempotencia). Aplicado a `demin-dev` y `demin-prod` el 2026-05-04. Distribución final ambos entornos: T1=455, T2=171, T3=252, T4=855, descartado=3.845. Diferencias máximas con plan §8.2 (±20% tolerancia): -1.2% en T2, -0.2% en T4 — el resto exacto.

**Métrica que confirma o desmiente la decisión:** cuando arranque `classify_descr.py` en Sprint 3, los ~1.733 leads accionables pasarán a Haiku para filtro IA. Si las empresas grandes (ACCIONA, FERROVIAL, DRAGADOS y similares afectadas por el dedup) caen como `no_fit` por tamaño, la decisión está validada — son el tipo de empresa que NO encaja en el ICP de Gonzalo (sweet spot 5k-100k€ según KB sesión 1) ni siquiera en su versión filial. Si caen como `fit`, revisar.

---

## 2026-05-04 — Lección 19: antes de construir Sprint X, revisar si las decisiones tomadas en Sprints previos siguen siendo válidas dado lo aprendido

**Contexto:** Sprint 2 paso 1 (ingesta SABI) arrancó y se cerró con plan §8 original intacto. Solo después, durante la discusión arquitectónica del 2026-05-04 sobre cómo extraer emails (que abre el camino al Sprint 4), se hizo evidente que el §8 original tenía tres asunciones invalidadas por aprendizajes acumulados: (a) `scrape_emails.py` desde web genérico apunta a buzones `info@` con reply rate sostenidamente bajo en cold outreach B2B; (b) Apollo tiene cobertura mediocre en PYME construcción España (sector poco indexado en bases anglo); (c) el modelo company-first puro choca con D8 (redacción IA completa por correo, no plantillas) cuando no hay nombre del decisor. El refactor del §8 (D7 → D16/D17/D18, scrape_emails+apollo → Hunter Domain Search + interfaz `EmailFinder`) debió hacerse al **cierre de Sprint 1**, no a mitad de Sprint 2 — al cerrar Sprint 1 ya teníamos KB cargado, dossier de Gonzalo procesado y experiencia operativa de Lemwarm/web pública suficientes para detectar el desalineamiento. En su lugar, el Sprint 2 arrancó con un plan §8 estructuralmente desfasado y solo lo descubrimos al planificar Sprint 4.

**Corrección humana:** refactor de §8/§14/§16/§17/§18 + decisiones nuevas D16/D17/D18 antes de tocar una sola línea de código de Sprint 3 o Sprint 4. Captura explícita de la regla de revisión de plan al cierre de cada Sprint para que el desfase no se repita.

**Regla resultante:**

- **Al cerrar cada Sprint**, antes de arrancar el siguiente, hacer una pasada sistemática por `tasks/todo.md` §8 (pipeline operativo) y §14 (fases) contrastando contra: (a) las lecciones acumuladas desde el último refactor de plan, (b) las decisiones cerradas (§3) que el Sprint cerrado pudo haber invalidado, (c) los aprendizajes operativos del Sprint (qué funcionó, qué se descartó, qué emergió como restricción nueva).
- **Si hay desfase, refactor de plan ANTES de código.** Aplicar el principio "el plan refleja la realidad operativa actual" — si los Sprints futuros se construyen sobre suposiciones desfasadas, se gasta esfuerzo en código que se tirará. La auditoría de plan post-Sprint cuesta 1-2h; reescribir un Sprint mal planteado cuesta días.
- **El refactor de plan es trabajo de planificación, NO de implementación**: solo toca documentación (`tasks/todo.md`, `tasks/lessons.md`). Si emergen cambios de schema o de código que el refactor implica, se anotan como TODO en el plan (ej. "ALTER constraint en migration X") y se consultan con el humano antes de migrar (regla 9 del Apéndice A).
- **Trigger explícito:** al añadir la entrada de cierre de Sprint en §19 del plan, incluir un sub-bloque "**Revisión de plan post-Sprint**" con respuesta a tres preguntas: ¿alguna decisión de §3 quedó invalidada?, ¿alguna sección de §8 ya no refleja la arquitectura objetivo?, ¿algún Sprint pendiente de §14 está construido sobre suposiciones que este Sprint ha tumbado? Si las tres respuestas son "no", se loggea explícitamente. Si alguna es "sí", refactor antes de continuar.
- **Aplicación generalizable más allá de Sprints**: la misma rutina aplica a cierres de Bloque, Fase y release v1 → v2. La cadencia de refactor de plan es proporcional al ritmo de aprendizaje del proyecto.

**Aplicado en:** `tasks/todo.md` 2026-05-04, refactor §8 + decisiones D16/D17/D18 + actualización §4/§6.1/§14/§16/§17/§18 + entrada §19 "Refactor a modelo híbrido SABI-first + Hunter como email finder". El trigger explícito (sub-bloque "Revisión de plan post-Sprint" en cada futura entrada §19 de cierre de Sprint) entra en vigor desde el próximo cierre de Sprint.

---

## 2026-05-06 — Lección 20: número saltado por error de numeración

Hueco intencional documentado. El refactor §8 + Lecciones 21/22/23 (commit `794b0db`, 2026-05-06) saltó del número 19 directamente al 21. Probablemente confusión con la decisión D20 que se añadió en el mismo commit. Sin referencias rotas a "Lección 20" en el repo (auditoría posterior commit pendiente).

No se renumera el resto (21→20, 22→21, …) para no invalidar las ~12 referencias externas a Lecciones 21-27 que ya viven en `tasks/todo.md`, `tasks/lessons.md` (auto-referencias internas) y entradas §19 que NO se reescriben.

**Regla resultante:** al añadir lecciones nuevas, verificar el último número usado con `grep '^## .*Lecci[oó]n \d+' tasks/lessons.md` antes de elegir el siguiente. La decisión D-N y la Lección N pueden coincidir en una misma sesión sin que sean lo mismo — son dos series numéricas independientes.

**Aplicado en:** este placeholder. La regla pasa a aplicarse desde la próxima Lección que se añada (Lección 28 cuando llegue).

---

## 2026-05-06 — Lección 21: validar pricing y disponibilidad de API en free tier ANTES de fijar un proveedor en el plan

**Contexto:** la decisión D17 (2026-05-04) eligió Hunter como email finder primario y RocketReach como adapter de respaldo, asumiendo que RocketReach tenía API accesible en su plan inferior. Verificación posterior (2026-05-06), tras cerrar la prueba experimental de Hunter: la API de RocketReach NO está disponible en planes inferiores a Ultimate ($2.484/año, ~207€/mes), excediendo el techo D15 del proyecto (150€/mes) por sí solo. Mantener RocketReach como adapter de respaldo en el plan no tenía sentido — activarlo nos saca del presupuesto.

**Corrección humana:** descartar RocketReach explícitamente (D19) y reescribir §4, §6.1, §8.5, §8.6, §16, §17 y §18 para reflejar el cambio. Pivote a Skrapp y Apollo, ambos con free tier accesible para la prueba comparativa.

**Regla resultante:** antes de fijar cualquier proveedor en el plan, verificar tres condiciones:

1. **Existe API pública** documentada (no solo UI o exportación manual).
2. **El free tier permite probar la API significativamente** — no basta con que exista plan gratuito si la API está bloqueada hasta plan superior.
3. **El plan más barato con API cabe en presupuesto** — incluyendo todos los costes recurrentes ya comprometidos del proyecto.

Si las tres no se cumplen, el proveedor NO entra al plan ni siquiera como adapter de respaldo. La abstracción `EmailFinder` (D17, mantenida en D19) sigue siendo la decisión correcta, pero los adapters concretos detrás de la interfaz se eligen tras validar los tres puntos arriba, no antes.

**Aplicable a futuros proveedores externos en el proyecto:** análisis pre-Bitwarden de cualquier alta de servicio (CRM, enriquecimiento, verificación de email, scraping as-a-service, gateway de IA alternativo, etc.). El error es transversal — no es específico de email finders.

**Aplicado en:** `tasks/todo.md` 2026-05-06 (D19 + revisión §4 / §6.1 / §8.5 / §8.6 / §16 / §17 / §18) y entrada §19 "Hunter AMARILLO + RocketReach descartado + …". Skrapp y Apollo entran a la prueba comparativa de Sprint 4 paso 1 con la regla aplicada (free tier + API + presupuesto verificados antes).

---

## 2026-05-06 — Lección 22: el hit rate de email finders en construcción España PYME puede ser estructuralmente bajo — probar al menos 2-3 adapters antes de comprometer plan pagado

**Contexto:** la prueba experimental de Hunter sobre 25 empresas SABI (5/5/5/10 por tier, sample diverso por localidad y descripción) terminó con VEREDICTO AMARILLO al 8% hit rate decisor (T1=0%, T2=20%, T3=20%, T4=0%). El threshold §16 que justificaba elegir Hunter como primario era 30%. Cuando Hunter cubría, los datos eran excelentes (cargos directamente accionables: Director Técnico, Project Manager, Director of Procurement; confidence 96-99). El problema no era señal/ruido sino **cobertura del índice** — el sector construcción PYME España no está bien indexado por Hunter.

**Hipótesis razonable:** otros email finders globales (Skrapp, Apollo, Lusha, Cognism…) pueden tener el mismo gap estructural por la misma razón (sector poco internacional, empresas pequeñas que no aparecen en bases de datos anglo-céntricas, web pública limitada o ausente). El gap NO es bug del proveedor concreto — es característica del sector.

**Corrección humana:** no escalar el problema con dinero. La decisión correcta es:

1. **Probar al menos 2-3 adapters** sobre el mismo sample antes de comprometer plan pagado de cualquiera.
2. **Si todos dan hit rate bajo** (<30% decisor), no se trata de elegir el "menos malo" pagando por él — la cobertura del sector está limitada estructuralmente.
3. **La respuesta correcta a cobertura estructuralmente baja** es replantear la estrategia (en este proyecto: D20 — política de aceptación ampliada por tier acepta `info@` en T1/T3 además de decisor).

**Regla resultante:** ante un proveedor de datos externo cuyo hit rate validado es bajo en el sector objetivo, NO escalar a plan pagado del mismo proveedor — primero confirmar si el bajo hit rate es del proveedor concreto (otro adapter dará >30%) o estructural del sector (todos darán <30%). Si es estructural, replantear estrategia aguas arriba (criterio de aceptación, segmentación por subgrupo, fuentes alternativas) en lugar de comprar más volumen.

**Aplicable a futuros proveedores de datos del proyecto:** verificadores de email, scrapers, fuentes de noticias del prospecto, plataformas de research B2B. La regla aplica más allá de email finders.

**Aplicado en:** `tasks/todo.md` 2026-05-06 (§14 Sprint 4 paso 1 = prueba comparativa Skrapp + Apollo sobre el mismo sample 25 empresas con criterio dual D20; §16 riesgo nuevo "cobertura email finders estructuralmente baja"; §19 entrada "Hunter AMARILLO + …"). La regla queda capturada para futuras decisiones de proveedor.

---

## 2026-05-06 — Lección 23: el criterio "solo decisor estricto vale" es demasiado restrictivo en B2B España PYME — política de aceptación de emails segmentada por tier de empresa

**Contexto:** la decisión D18 (2026-05-04) limitaba el universo de contacts útil a "2-3 decisores reales por empresa" (gerente, jefe de obra, responsable compras). Lectura inicial: cualquier email que no fuera de uno de esos cargos quedaba descartado. La prueba experimental de Hunter sobre 25 empresas SABI (2026-05-06) reveló que **9 de 25 empresas devolvían emails con NOMBRE pero SIN cargo identificado** (patrón típico PYME ES: Hunter indexa el dominio y captura `nombre@empresa.es` pero no la web/LinkedIn donde aparece el cargo). Aplicar el filtro estricto descartaba todos esos contacts, dejando hit rate efectivo en 8% — muy por debajo del 30% del threshold §16.

Inspección manual de los 9 casos: empresas T1 (1k-5k k€) y T3 (0.5k-1k k€), microempresas o muy pequeñas, mostraban patrón claro — `info@empresa.es`, `contacto@empresa.es`, `gerencia@empresa.es` son leídos directamente por el gerente sin filtro humano intermedio. NO son buzones desatendidos; son la vía estándar de contacto en empresas de 1-10 empleados. Empresas T2 (5k-20k k€), en cambio, sí tienen filtros administrativos que descartan correos cold a `info@`.

**Corrección humana:** ampliar D18 con D20 — política de aceptación de emails segmentada por tier de empresa, con whitelist positiva por prefijo y whitelist negativa global.

**Regla resultante:** en B2B PYME España, la utilidad de un email para outreach NO depende solo del cargo identificado del destinatario. Depende del cruce **(cargo / tipo de email) × (tamaño de la empresa)**:

- En empresas micro/pequeñas (1-10 empleados, T1 y T3 en SABI), los buzones genéricos de la whitelist positiva (`info@`, `contacto@`, `hola@`, `gerencia@`, `obras@`, `proyectos@`, `comercial@`, `direccion@`, `oficina@`, `administracion@`) son leídos por el gerente — outreach útil.
- En empresas medianas (T2: 5k-20k k€), los buzones genéricos sí tienen filtro administrativo — outreach a `info@` con reply rate sostenidamente bajo. Allí mantenemos exigencia de decisor o nominal con cargo identificable.
- En todos los tiers, la **whitelist negativa global** descarta `marketing@`, `rrhh@`, `prensa@`, `comunicacion@`, `noreply@`, `facturas@`, `contabilidad@`, `webmaster@`, `soporte@`, etc. — esos buzones no llevan a un decisor en ningún tamaño de empresa.

Implementación técnica: campo `contacts.email_type` (enum: `decisor` | `nominal` | `corporativo_pequeno` | `descartado`) + campo `email_priority` (1-4) para ordenar candidatos cuando hay varios por empresa. La política se aplica en el worker `find_contacts.py` (renombrado desde `find_decisors_hunter.py`) y se lee en el prompt de redacción §10.2 para adaptar apertura/llamada al destinatario según el tipo de email.

**Aplicable más allá de DEMIN:** cualquier outreach B2B en sectores con prevalencia de PYME pequeña debe contemplar la asimetría tamaño-empresa × utilidad-de-email-genérico. La regla NO es "no escribir a info@ nunca" (regla común en cold outreach US) ni "escribir a cualquier email vale" (queda gente molesta). Es segmentar por tier y aplicar criterio diferenciado.

**Aplicado en:** `tasks/todo.md` 2026-05-06 (D20 nueva en §3, §6.1 columnas `email_type` + `email_priority` pendientes Sprint 4, §8.5 reescrito con jerarquía decisor > nominal > corporativo_pequeno por tier + whitelists, §10.2 regla "variantes por email_type" pendiente prompt completo, §14 Sprint 4 paso 4 worker `find_contacts.py` con política tier-segmentada, §19 entrada "Hunter AMARILLO + …"). La implementación de campo + worker + prompt queda agendada para Sprint 4 o 5 según orden final.

---

## 2026-05-06 — Lección 24: el universo accionable PYME construcción ES está dominado por empresas SIN web (T4 = 55.6%) — validar input mínimo de cada tier ANTES de comprometer arquitectura

**Contexto:** durante Frente E (sesión 2026-05-06) se hicieron queries directas a `companies` en demin-prod tras Sprint 3 cerrado (`ia_fit='fit'` por tier). La distribución real del universo accionable es:

| Tier | Total SABI | `ia_fit='fit'` | % universo accionable |
|------|------------|----------------|---|
| T1 (con web, 1k-5k €) | 455 | 118 | 22.8% |
| T2 (con web, 5k-20k €) | 171 | 48  | 9.3%  |
| T3 (con web, 0.5k-1k €) | 252 | 64  | 12.4% |
| T4 (sin web, 0.5k-20k €) | 855 | **288** | **55.6%** |
| **Total accionable** | 1.733 | **518** | 100% |

El plan original (§8.5 anterior, D17 antes de superseder) asumía que la mayoría tendría web indexable y por eso eligió Hunter Domain Search como adapter primario. La realidad PYME construcción ES es la opuesta: **más de la mitad del universo accionable carece de web** y por tanto carece del input mínimo de cualquier email finder convencional (incluyendo Hunter, Apollo, Skrapp, RocketReach).

**Corrección humana:** decisión D21 (arquitectura híbrida por tier) reconoce que ningún email finder convencional cubre T4 sin tener dominio primero, por lo que T4 requiere estrategia diferenciada — Opción C en Sprint 5 (research IA + permutación + verificación + empresite/einforma como fuente complementaria de email visible).

**Regla resultante:** antes de elegir arquitectura/proveedor para procesar el universo de leads, **medir la distribución por tier y verificar que cada tier tiene el input mínimo que el proveedor exige**. En el caso de email finders por dominio, el input mínimo es el dominio web. Si un % significativo del universo no lo tiene, la arquitectura debe contemplar un sub-flujo distinto para ese segmento desde el día 1, no como excepción tardía.

**Aplicable más allá de DEMIN:** cualquier proceso B2B que dependa de un identificador externo (dominio, LinkedIn URL, NIF, teléfono móvil…) — verificar la distribución del identificador en el universo objetivo ANTES de comprometer el proveedor que lo consume. La omisión es de "supuesto del plan" tipo Lección 9 (KB manda sobre plan en divergencias) extendida a inputs operativos.

**Aplicado en:** `tasks/todo.md` 2026-05-06 — D21 reparte cobertura por tier, §4 distingue email finder primario (T2/T3) de Opción C (T1/T4), §8.5 documenta T4 con `empresite.com` complementario, §14 Sprint 4 cubre solo T3+T2, §14 Sprint 5 (T1+T4) en planificación posterior, §17 estima coste extra Sprint 5 +50-80€/mes para infraestructura adicional.

---

## 2026-05-06 — Lección 25: flujo profesional B2B M&A para encontrar decisores — LinkedIn → URL del perfil → email finder con URL como input (hit rate típico 60-80%)

**Contexto:** discusión arquitectónica durante sesión 2026-05-06, Alberto aporta experiencia industrial M&A donde el flujo estándar para encontrar decisores B2B es:

1. Buscar en LinkedIn por filtros (cargo + sector + ubicación + tamaño de empresa).
2. Obtener URL del perfil del decisor.
3. Pasar la URL a un email finder que devuelve email a partir de URL LinkedIn (no a partir de dominio web).

Hit rate típico de este flujo: **60-80%**, sustancialmente mejor que email finders por dominio (Hunter dio 8% decisor estricto, 20% con D20 sobre PYME ES). La razón estructural es que LinkedIn indexa decisores con mayor cobertura que las webs corporativas, especialmente en empresas pequeñas que no listan equipo en su web.

Coste estimado para DEMIN: Phantombuster (~$60/mes) para automatizar la búsqueda LinkedIn + email finder por URL (~$50/mes). Total ~$110/mes — entra en el techo D15 (150€/mes) si se desactivan otras palancas (warm standby Lemwarm, lotes Hunter mensuales).

**Riesgos identificados:**

1. **TOS de LinkedIn prohíbe scraping automatizado** (incluso de datos públicos). Cuentas que automatizan via Phantombuster, Lemlist Sales Engine, etc., pueden ser baneadas. Contramedida: usar cuenta dedicada sin valor personal de Gonzalo, rate-limit conservador, solo búsquedas (no scraping de mensajería), accept ban como coste hundido.
2. **RGPD aplicable a procesamiento de datos personales públicos**. Aunque el dato sea público, automatizar su recolección + uso comercial requiere base legal documentada (interés legítimo B2B + balance test + información clara al titular en el primer contacto). El proyecto ya tiene base legal para email outreach B2B (interés legítimo) — extender a LinkedIn requiere actualizar la política de privacidad y el aviso legal.

**Corrección humana:** apuntar el flujo como opción Sprint 5+ pero NO comprometer en Sprint 4. La decisión de activarlo depende de los reply rates reales de Sprint 4 con Hunter+D20 sobre T2+T3.

**Regla resultante:** cuando un humano aporta una práctica industrial validada en otro contexto (en este caso M&A), capturarla como opción documentada con su coste, hit rate típico y riesgos, pero NO ejecutarla sin validar empíricamente sobre el dataset propio. La diferencia entre 60-80% en M&A y 60-80% en construcción ES PYME es desconocida hasta medirla. Pre-requisito de activación: TOS check + cuenta Phantombuster de prueba + medición de hit rate sobre 25 empresas comparable a Frente C.

**Aplicado en:** `tasks/todo.md` 2026-05-06 §18 (dependencia humana Sprint 5 — evaluación operativa flujo LinkedIn), §17 (coste estimado +$60+$50/mes si se activa), §19 entrada "Sesión exploratoria intensiva 2026-05-06". Implementación NO entra en Sprint 4 — depende de medición empírica post-Sprint 4.

---

## 2026-05-06 — Lección 26: fuentes públicas españolas (empresite.com, einforma.com, axesor.es) tienen email visible para subset de PYMEs T4 sin web — fuente complementaria útil pero no resuelve T4 sola

**Contexto:** búsqueda manual durante sesión 2026-05-06 sobre 3 empresas T4 sin web del universo SABI. Resultado: email visible en `empresite.com` en **3/3** casos. N=3 es ruido estadístico, pero la calidad observada es desigual y hace falta un mini-experimento estructurado:

- **Helian:** email mostrado pertenece a una persona física, registrado bajo dominio de OTRA empresa (probablemente la del administrador). Email real pero ¿es el correcto para outreach a esta empresa concreta? Caso ambiguo.
- **Velázquez Internacional:** empresa en baja registral. Email aparece pero la empresa no está operativa. Outreach inútil.
- **Velzia Luxury Homes:** empresa marcada como T4 (sin web) en SABI, pero búsqueda manual encontró que SÍ tiene web pública y teléfono visible. Posible error de categorización SABI o web creada después del export. Outreach útil pero el problema NO era cobertura del adapter — era dato SABI desactualizado.

**Corrección humana:** apuntar empresite/einforma como fuente complementaria para Sprint 5 Opción C T4, pero exigir mini-experimento estructurado sobre 10 empresas con tabla de cobertura ANTES de integrarla operativamente. La N=3 actual es insuficiente para estimar hit rate real.

**Regla resultante:** cuando una fuente nueva muestra prometedora con N pequeño (<5), apuntarla como hipótesis y planificar mini-experimento estructurado (N=10-25) con tabla de cobertura ANTES de integrarla en el flujo productivo. La heurística "3/3 funciona, vamos a integrarla" es trampa estadística. La tabla debe documentar: empresa × email_visible_en_perfil × calidad_dato (persona física en otro dominio, baja registral, web ya existente, etc.).

**Riesgos identificados:**

1. **TOS de empresite/einforma** prohíbe scraping comercial automatizado. Como con LinkedIn, contramedida es cuenta dedicada + rate-limit conservador + uso humano-en-el-loop si la fuente lo exige.
2. **RGPD aplicable a emails de personas físicas** que aparecen en directorios públicos. La base legal de interés legítimo B2B aplica si el email es funcional (info@empresa, contacto@empresa). Para emails de persona física que aparecen porque la empresa los publicó como contacto comercial, el balance test sigue siendo razonable pero requiere documentación.

**Aplicado en:** `tasks/todo.md` 2026-05-06 §8.5 (T4 con `empresite.com`/`einforma.com` como fuente complementaria de Sprint 5), §18 (dependencia humana Sprint 5 — mini-experimento estructurado sobre 10 empresas con tabla de cobertura), §19 entrada del 2026-05-06.

---

## 2026-05-06 — Lección 27: roll-out de cold outreach escalonado por probabilidad de respuesta — primeros 100 envíos marcan reputación del dominio para los siguientes 1.000

**Contexto:** decisión D22 durante sesión 2026-05-06. La pregunta operativa era: tras Sprint 4 listo, ¿se mandan correos a las 51 T3 + 48 T2 + 118 T1 + 288 T4 todas a la vez al cap de 10/día, o por lotes? La práctica industrial estándar (capturada implícitamente por Lemwarm, Instantly, Smartlead, Lemlist en sus blogs y guías de deliverability) dice que **los primeros 100 envíos en frío de un dominio nuevo marcan la reputación del remitente para los siguientes ~1.000-10.000**:

- Si los primeros 100 envíos van a leads de **alta probabilidad de respuesta** (cobertura adapter alta + propuesta de valor relevante + cargo correcto), el reply rate inicial es alto, pocos bounces, pocos spam complaints. Gmail/Outlook ven al remitente como "mailer legítimo con engagement positivo" y suben el límite implícito de envíos diarios.
- Si los primeros 100 envíos van a leads de **baja probabilidad** (cobertura adapter baja, mucho `info@` mal segmentado, cargo incierto), el reply rate es bajo y los bounces/spam complaints suben. El dominio entra en "watch list" de los proveedores y los siguientes 1.000 envíos van a spam aunque la calidad mejore.

Ratio práctico: una semana mala al inicio puede degradar deliverability durante meses; una semana buena al inicio compra ~6-12 meses de buffer.

**Corrección humana:** D22 — roll-out escalonado por tier en Sprint 4. Semana 1 solo T3 (cobertura D20 80%, alta confianza). Semana 2-3 añadir T2 con research IA enriquece-cargo (cobertura D21 estimada 50-60%). T1 y T4 (cobertura 0% sin Opción C) NO entran a Sprint 4 — esperan Sprint 5.

**Regla resultante:** roll-out de cold outreach escalonado por probabilidad de respuesta NO es paranoia, es práctica industrial. Aplica desde el día 1 del primer envío en frío:

1. Empezar por el segmento con MAYOR cobertura de adapter Y MAYOR fit con la propuesta de valor — los dos juntos. Cobertura sin fit no genera reply; fit sin cobertura no genera envío.
2. Threshold operativo: **si reply rate Semana 1 < 3% sostenido, parar el roll-out** y revisar KB / prompts / segmento ANTES de añadir el siguiente tier. Es preferible parar 1 semana que quemar el dominio por avanzar con datos malos.
3. Documentar en plan: cada Sprint que active envío productivo debe declarar el tier de arranque y los thresholds de pausa, no solo el total a procesar.

**Aplicable más allá de DEMIN:** cualquier sistema que arranque cold outreach desde un dominio nuevo debe escalonar. Aplicable también a re-engage masivos tras pausas largas (la reputación caduca con la inactividad — un mes sin enviar y los proveedores te tratan como remitente nuevo de nuevo).

**Aplicado en:** `tasks/todo.md` 2026-05-06 D22 + §14 Sprint 4 reorganizado en 9 pasos con roll-out explícito (paso 7 Semana 1 solo T3, paso 8 Semana 2-3 añadir T2), §16 riesgo nuevo "reply rate estructuralmente bajo en T3" con threshold de pausa 3%, §19 entrada "Sesión exploratoria intensiva 2026-05-06".

---

## 2026-05-08 — Lección 28: cuando un worker itera sobre una entidad, cruzar EXPLÍCITAMENTE los filtros de selección con TODA la cadena de decisiones del plan que la afectan, no solo con la sección donde está documentada esa entidad

**Contexto:** Sprint 4 paso 6 implementó `generate_draft.py` con `fetch_pending_contacts` filtrando por las condiciones obvias (research OK, no opt-out, no message previo del mismo step_index). 88 tests cubrieron el comportamiento. Mypy `--strict` limpio. Smoke E2E sobre 5 T3 reales generó 4 drafts en `messages.status='drafted'` y se reportaron como "OK 4/4". El humano (Alberto, en rol PM) detectó en auditoría que LENA CONSTRUCCIONES tenía 3 drafts simultáneos a tres direcciones del mismo dominio (jaime + zaragoza + info @ nozar.es), lo cual es spam interno para el prospecto y señal de spam para los filtros de Gmail/Outlook (degrada los primeros 100 envíos del paso 7, Lección 27). El bug es trivial — falta `AND ct.is_primary = true` en el WHERE — pero pasó la suite porque el campo `contacts.is_primary` existe en el schema, find_contacts lo asignaba bien, los tests parametrizaban distintos `email_type` pero NUNCA comprobaron si `fetch_pending_contacts` respeta `is_primary`.

La causa raíz no es la línea de código que faltaba; es de proceso: al planificar el paso 6, leí "el worker itera contacts" en §10.1 y construí los filtros consultando solo §10 (pipeline de generación) + §6.1 (schema de messages). Lo que NO hice fue cruzar esa decisión de filtrado con D18 ("2-3 decisores por empresa, [...] menos pierde el lead **si el primero no responde**" — la frase que IMPLICA secuencia, no envío simultáneo) + §8.5 ("Primero por prioridad → `is_primary=true`" — el campo existe específicamente como selector de cadencia) + §9.2 ("3 toques **por contacto**" — la unidad de cadencia es el contacto). Los 4 puntos del plan apuntaban inequívocamente a "1 contact activo de cadencia por empresa", pero ninguno lo decía explícitamente en §10.1, así que el filtro `is_primary` se omitió.

**Corrección humana:** Alberto detectó el bug en auditoría manual antes de autorizar paso 7. Pidió fix mínimo (filtro `is_primary=true` + test integración + cleanup datos dev + edición §10.1/§8.5 explícitos) registrado como paso 6.5. Y pidió **registrar esta lección como meta-patrón de proceso**, no como corrección puntual del bug.

**Regla resultante:**

- **Cuando un worker itere sobre una entidad** (contacts, companies, messages, replies, etc.), antes de fijar el SQL de selección, **enumerar las decisiones del plan que afectan a esa entidad** — no solo la sección donde el worker está documentado. Hacer esa lista explícita en el plan (sub-bloque "decisiones cruzadas" del paso, o bullet en §X.Y del worker) y traducir cada una a un filtro o aserción concreta. Si el plan menciona un campo del schema (ej. `is_primary`, `is_optout`, `is_active`, `email_verified`), preguntar para cada uno: "¿debe el worker filtrar por este campo?" — la respuesta explícita "sí, filtra" o "no, no aplica" queda en el plan.
- **Para entidades con múltiples flags operativos** (`contacts` tiene `is_primary` + `is_optout` + `email_verified`; `messages` tiene `status` con 7 valores), construir una matriz "flag × worker" en el plan que documente qué flags consume cada worker. La matriz hace evidentes los huecos.
- **Tests de SQL de selección requieren cobertura de filtro explícita**, no solo de comportamiento downstream. Para `fetch_X_pending`, los tests deben cubrir: insert 2 entidades con la condición distinta (1 que pasa el filtro, 1 que no) y verificar que solo la primera aparece en el resultado. Sin ese test, el SQL puede tener un bug que la suite de comportamiento no captura porque downstream se ve igual con o sin el filtro.
- **Auditoría humana ANTES de autorizar acciones operativas con efecto externo** (envío de correos, integraciones con APIs de terceros, modificación de estado en sistemas downstream). El paso 7 introduce envío real Gmail; sin la auditoría humana del paso 6, los 3 drafts simultáneos a nozar.es habrían entrado al primer batch productivo y degradado deliverability. La validación E2E técnica del paso 6 (workers funcionan) es necesaria pero insuficiente — la validación humana de coherencia operativa es el gate que autoriza envío productivo.

**Aplicable más allá de DEMIN:** cualquier worker que produzca acciones con efecto externo (envío, llamada API, mutación downstream) debe pasar por gate humano entre validación técnica E2E y producción real. La diferencia de coste entre detectar este bug pre-envío (1 commit fix de 5 líneas) y detectarlo post-envío (dominio quemado, deliverability degradada durante meses) es la diferencia entre 1 hora y un sprint perdido.

**Aplicado en:**
- `tasks/todo.md` §10.1 paso 1: filtro `is_primary=true` documentado explícitamente con su justificación cruzada a D18+§9.2.
- `tasks/todo.md` §8.5 paso "Selección y priorización": frase aclaratoria "los candidatos no-primary son respaldo manual, NO envío automático".
- `apps/workers/pipeline/generate_draft.py` `fetch_pending_contacts`: filtro `AND ct.is_primary = true` añadido + docstring extendido con justificación.
- `apps/workers/tests/test_integration_generate_draft.py`: test integración nuevo con marker `@pytest.mark.integration` que verifica filtro `is_primary` con BD dev real (1 primary + 1 no primary → solo el primary aparece en resultado).
- `apps/workers/scripts/cleanup_paso65.py`: cancela los messages pre-envío (drafted + approved) cuyo contact no es is_primary, preservando el status anterior en `_cancelled_from_status` para event trail.
- `tasks/todo.md` §19 entrada "Cierre Sprint 4 paso 6.5".
- Esta lección.

**Trigger de aplicación inmediata:** paso 6.6 (asignación de `is_primary` en `find_contacts.py`) y paso 7+ (cualquier worker que itere sobre `contacts` o `messages`). Para Sprint 5 y Fase 3, **antes de implementar cualquier worker que itere sobre una entidad de BD**, hacer la pasada de "decisiones cruzadas" descrita arriba.

---

## 2026-05-12 — Lección 29: tiebreaker silencioso en sort_key es un bug en espera — ordenar dimensiones por su poder de discriminación operativa, no por su disponibilidad numérica

**Contexto:** Sprint 4 paso 6.5 cerró el bug de envío simultáneo a múltiples contacts del mismo dominio añadiendo el filtro `is_primary=true` a `generate_draft.fetch_pending_contacts`. El cleanup recompute `is_primary` en BD dev — y dejó como primary de LENA CONSTRUCCIONES al nominal-sin-cargo `zaragoza@nozar.es` en lugar del nominal-con-cargo `jaime.nozaleda@nozar.es` (cargo "Business Development Director"). El humano (Alberto, en rol PM) detectó la incoherencia en auditoría del 6.5: ambos contacts caían en `email_priority=3` (bucket nominal único de `assign_priority`) y el sort `(priority asc, confidence desc)` resolvía el empate por confidence Hunter, donde zaragoza ganaba. Intuitivamente jaime es mejor primary porque su cargo identificado lo marca como perfil decisor con mayor probabilidad de respuesta — pero esa señal estaba enterrada bajo un desempate por confidence email.

El bug no fue detectado por la suite de paso 4 ni 4b: `test_assign_priority_table` parametrizaba `("nominal", 90, 3)` y `("nominal", 0, 3)` afirmando que **da igual la confidence en nominal** — pero NO verificaba que da igual también el cargo. La cobertura confirmaba el comportamiento como deseable sin cruzar con la operativa real (mismo patrón que Lección 28 pero un nivel más fino: aquí el bug está en el **orden del sort**, no en el filtro).

**Corrección humana:** Alberto detectó el primary equivocado durante la inspección de BD del paso 6.5 (`debug_contact_state.py`) y autorizó paso 6.6 inmediato antes de paso 7. Pidió revisar `assign_priority` para que dentro del bucket nominal, "con cargo" gane a "sin cargo" antes que el desempate por confidence. Implementación a criterio (sub-bucket numérico, tiebreaker en sort, sub-priority decimal — se eligió bucket 5 explícito para que el campo `email_priority` quede como single source of truth auditable desde SQL). Y pidió **capturar esto como lección distinta de la 28** — el patrón meta es diferente.

**Regla resultante:**

- **Antes de cerrar un sort_key sobre entidades operativas**, listar **todas** las dimensiones que el plan trata como distintas en operativa real, NO solo las que están disponibles como columnas numéricas. Confidence Hunter es señal de calidad del email (sintaxis, fuente del adapter); cargo identificado es señal de calidad del rol — y rol manda sobre email cuando ambos contacts entran al mismo buzón corporativo. El sort `(priority asc, confidence desc)` enterraba esa distinción haciendo invisible un tiebreak operativamente relevante.
- **Las dimensiones cualitativas (presencia/ausencia de cargo, tipo de rol, sector ICP) deben preceder a las cuantitativas (confidence, score, recency) en el sort_key cuando ambas compiten en el mismo bucket.** Lo numérico es más fácil de incorporar porque siempre está disponible — pero esa disponibilidad es accidental, no operativa. Si el plan distingue dos dimensiones cualitativas distintas, codificarlas en el sort_key explícitamente; no delegar a un proxy numérico que "suele correlacionar".
- **Tests de orden requieren cobertura adversarial**: insert 2 entidades donde la dimensión cualitativa y la cuantitativa apunten en sentidos opuestos (con-cargo + low-confidence vs sin-cargo + high-confidence), y verificar que el orden lo dicta la cualitativa. Un test que solo verifica orden cuando todas las señales alinean ("decisor confidence alto" → "nominal confidence alto" → "corporativo confidence alto") es coherente con cualquier sort lineal y no descubre el bug.
- **Si una dimensión cualitativa importa para el sort pero no es columna en BD**, persistirla. En paso 6.6 el bucket 3 vs 4 va al campo `email_priority` (numérico, persistido) en vez de quedarse como un parámetro de runtime — porque ahí queda **auditable desde SQL ad-hoc** sin necesidad de re-correr la clasificación. Single source of truth.

**Aplicable más allá de DEMIN:** cualquier sistema con prioridad multi-dimensional sobre entidades que se procesan en serie (cold outreach contacts, queue de tickets de soporte, candidate ranking, lead scoring). El instinto de codificador es "ordeno por el score numérico que ya tengo" cuando lo correcto es "codifico la dimensión que el dominio considera importante aunque no sea numérica de origen". Lección hermana de la "ordering hierarchy" de los patrones de diseño de queue management.

**Aplicado en:**
- `tasks/todo.md` §3 D18: nota inline "Refinamiento paso 6.6 — dentro del bucket nominal, con cargo precede a sin cargo en `email_priority` antes que el desempate por confidence".
- `tasks/todo.md` §8.5 punto 4 + bullet "Selección y priorización": enumeración explícita 1..5 con sub-distinción nominal-con-cargo (3) vs nominal-sin-cargo (4) + justificación operativa "cargo claro > confidence en bucket nominal".
- `infra/supabase/migrations/20260512120000_10_email_priority_extend_to_5.sql`: CHECK constraint 1..5 + default 5 + COMMENT actualizado.
- `apps/workers/pipeline/find_contacts.py` `assign_priority`: firma extendida a `(email_type, confidence, position=None)` con lógica nueva del bucket 5 y docstring que cruza la regla con §8.5 + esta lección.
- `apps/workers/tests/test_find_contacts.py`:
  - `test_assign_priority_table` parametrizada con 16 casos cubriendo `position` vacío/None/string-vacío + presencia de cargo por cada `email_type`.
  - `test_assign_priority_nominal_con_cargo_gana_a_sin_cargo` documentando el caso real de LENA.
  - `test_select_top_nominal_con_cargo_gana_a_nominal_sin_cargo_alto_conf` como regresión operativa: jaime priority=3 conf=60 + zaragoza priority=4 conf=95 → jaime primero (cobertura adversarial — dimensiones en sentidos opuestos).
- `apps/workers/scripts/recompute_priorities_paso66.py`: re-cómputo de `email_priority` + `is_primary` sobre contacts existentes en dev tras el cambio.
- `apps/workers/scripts/cleanup_paso66.py`: cancela messages pre-envío cuyo contact dejó de ser primary tras recompute (espejo de `cleanup_paso65.py` con razón distinta `paso66_primary_reassign`).
- `tasks/todo.md` §19 entrada "2026-05-12 — Paso 6.6".
- Esta lección.

**Trigger de aplicación inmediata:** paso 7 y siguientes — cualquier worker que ordene/seleccione contacts o messages para acciones operativas. Cuando definamos sort sobre `replies` (paso 11+ Fase 3, categorización + priorización de respuestas), aplicar la misma pasada: listar dimensiones cualitativas del plan, asegurar que preceden a las numéricas, persistir cualitativas si importan al sort.

---

## 2026-05-12 — Lección 30: las asunciones conservadoras del plan original sobre warmup deben revisarse contra datos reales del proveedor antes de fijar el cap operativo

**Contexto:** Sprint 4 paso 7 — antes de arrancar la construcción de pre-requisitos de envío real, el PM (Alberto) detectó que el plan §9.3 fijaba cap inicial "10/día primera semana → +5/semana → tope 50/día" basado en estimación conservadora pre-warmup. La realidad operativa del momento, 2 semanas después de activar Lemwarm Essential sobre el buzón `gonzalo.perez@demingroupmadrid.com`, era distinta:

- **Lemwarm deliverability score: 92** (sobre 100; >85 considerado production-ready según UI Lemwarm).
- **Lemwarm internal reply rate: 80%** sobre el universo de warmup peers.
- **2 semanas de warmup activo** (minimo prescrito por §9.1) cumplidas con holgura.
- **Hunter Starter contratado** simultáneamente — 500 búsquedas/mes aguanta 20/día × 20 días sostenido con margen.
- **Gonzalo aprueba ≤20 drafts/día** en `/approval-queue` sin saturarse (~30s/draft × 20 = 10 min/día de revisión humana).
- **100 envíos/semana** dan muestra estadística suficiente para evaluar bounce/spam/reply rates antes de subir.

El PM decidió: cap Semana 1 = **20/día** en lugar de 10/día. Rampa nueva 20→25→30→40 (Sem 4+) en lugar de 10→15→20→25 que el plan original prescribía.

**Corrección humana:** el plan §9.3 fue escrito en sesión 2026-04-29 (Bloque A, pre-warmup, sin datos Lemwarm). Su número "10/día Semana 1" era prudencia razonable a falta de evidencia. Tras 2 semanas reales, el dato refuta el supuesto conservador. PM aplica regla 10 Apéndice A: corrección humana basada en datos del proveedor → §9.3 refinada + nota a D22 + esta lección.

**Regla resultante:**

- **Antes de fijar un cap o threshold operativo basado en una asunción del plan pre-validación**, revisar los datos reales del proveedor (Lemwarm dashboard, Postmaster Tools, Hunter quota, etc.) y comparar contra el supuesto. Si el supuesto resulta conservador (datos reales superan), subir el cap dentro del techo absoluto del proveedor (§9.1 dice 50/día por buzón, eso es el ceiling de Gmail Workspace, NO se toca). Si el supuesto resulta optimista, mantener el cap bajo y rampar más lento.
- **Los caps deben venir parametrizados con su justificación operativa documentada** (Lemwarm score X, sample mínimo N, threshold proveedor Y). Sin ello, futuras revisiones no saben si el número es "lo que el plan dijo" (estimación) o "lo que los datos validaron" (refinamiento).
- **Cambios de cap rampa requieren refinamiento del plan + Lección + nota inline en la decisión cerrada original** (D22 en este caso). NO reescribir silenciosamente el cap antiguo — preservar la cadena de evidencia: "10/día → 20/día porque Lemwarm score 92".
- **El cap NO es decisión técnica unilateral del implementador**. Es decisión PM con datos del proveedor + capacidad humana (revisión HITL) + threshold proveedor. Code marca el supuesto del plan como entrada, no como ground truth.

**Aplicable más allá de DEMIN:** cualquier sistema con caps operativos pre-validación (rate limits internos, throttling, batch sizes, retry counts) tiene este patrón. La estimación inicial es necesaria para arrancar pero requiere validación contra realidad antes de operar. La frase a buscar: "el plan dice X pero los datos del proveedor dicen Y" → revisar X.

**Aplicado en:**
- `tasks/todo.md` §9.3: rampa cap 20→25→30→40 (Sem 1→4+), tope 50/buzón (sin cambio).
- `tasks/todo.md` §3 D22: nota inline de refinamiento paso 7.
- `tasks/todo.md` §14 paso 7: bullet actualizado con cap 20/día + justificación inline.
- `tasks/todo.md` §17: Hunter Starter contratado, total recurrente actualizado.
- `infra/supabase/migrations/20260512130000_11_seed_outreach_and_clean_seq_comment.sql`: seed `mailboxes.daily_cap=20` + COMMENT actualizado con la rampa nueva.
- Memoria de auto-memory `project_hunter_paid_plan.md`: pendiente actualizar cuando llegue API key B3 (Starter contratado, cap 100 hunter_calls).
- Esta lección.

**Trigger de aplicación inmediata:** paso 8 (Semana 2, subir cap a 25 si bounce <1% y reply >0). Paso 9 cierre Sprint 4 (revisar rampa contra datos reales 3-4 semanas). Sprint 5 cuando arranque T1+T4 (re-validar cap dada distribución diferente).

---

## 2026-05-12 — Lección 31: en sesiones asistidas por chat con humano operando secrets, los secrets aparecen en el chat por inercia — el threat model debe contemplarlo, no pretender que no pasa

**Contexto:** Sprint 4 paso 7, bloqueador B1 (Gmail OAuth en Google Cloud Console). El flow operativo era: PM crea OAuth client tipo Desktop en Google Cloud Console → descarga `credentials.json` → lo coloca en `apps/workers/credentials.json` → ejecuta `scripts/gmail_oauth_setup.py` → genera `refresh_token`. Cero pasos del flow requieren que PM pegue contenido sensible en el chat con Code — basta con que PM diga "el JSON está colocado" y Code verifica shape via `Read` tool sobre el filesystem.

Lo que pasó en la práctica:
1. PM pegó el contenido completo del `credentials.json` en el chat (incluyendo `client_secret`).
2. Code flagueó el leak y recomendó rotar el `client_secret` (3 min en Google Cloud Console).
3. PM rechazó rotar — "me da igual dime cómo continuó" — decisión legítima dado threat model (Desktop OAuth con scope `gmail.send` + Workspace Internal, riesgo real bajo; Google reconoce que Desktop client_secret no es realmente secreto porque el binario puede ser decompilado).
4. PM ejecutó el script. La salida incluyó el `refresh_token` impreso a stdout (diseño explícito del script para que PM lo pudiera copiar al fichero local — `gmail_oauth_setup.py:113` `print(creds.refresh_token)`). PM copió la salida completa al chat en lugar de redactar el token.
5. PM aceptó el riesgo otra vez y siguió. Token persistido en BD via Supabase Vault (UUID), recuperable vía `vault.decrypted_secrets`.

**Corrección humana (parcial):** PM aceptó dos veces consecutivas que un secret aparezca en chat. NO es corrección a un error de Code — es decisión PM sobre threat model. Pero PM pidió capturar esto como lección operacional ("Si quieres anotarlo como Lección 32, hazlo. PM lo deja a tu criterio si vale la pena capturar o no.") porque el patrón meta es valioso para futuros flujos.

**Regla resultante:**

- **Asumir que cualquier credencial generada durante una sesión asistida aparecerá en el canal de chat por inercia.** El humano operando copy/paste va a copiar la salida completa del comando, no a redactar partes. Si quieres minimizar exposure, NO basta con decir "no la pegues" — hay que diseñar el flow para que el secret no salga al stdout / que el output no sea naturalmente copiable / que el siguiente paso del PM no requiera el secret en su buffer.
- **Threat model debe contemplar la exposición chat como dimensión, no pretender que no pasa.** Para Code: el chat es persistente, indexable por Anthropic, e incluido en el contexto de futuras sesiones via auto-memory si aplica. Para credenciales de bajo privilegio + revocables (Desktop OAuth `client_secret`, refresh_tokens scope-limitado, API keys que el proveedor permite rotar trivialmente): aceptable convivir con exposure si el PM lo decide explícitamente. Para credenciales de alto privilegio (service role keys con bypass de RLS, database passwords, prod refresh_tokens con scope amplio): rotación obligatoria pre-uso si aparecieron en chat.
- **Code debe ofrecer flows que NO requieran que el humano pegue el secret en chat.** Patrón correcto: "guarda el fichero en `<path>` y yo lo leo desde filesystem". Patrón incorrecto: "pégame el contenido". El `gmail_oauth_setup.py` cumple bien (token guardado en fichero local gitignored + impreso a stdout para copy fácil) — pero el script PUDO haber omitido el print a stdout y dependido solo del fichero, para empujar al PM al patrón filesystem. Lección para diseñar scripts futuros con secrets: NO printear a stdout si el siguiente paso no lo requiere; obligar uso del fichero.
- **Documentar la decisión PM cuando acepta riesgo de exposure.** Trazabilidad para auditoría futura: "secret X expuesto en chat sesión Y, PM aceptó no rotar porque threat model Z". Sin eso, una auditoría futura puede pensar que fue accidente no detectado.

**Aplicable más allá de DEMIN:** cualquier proceso operativo donde un humano + LLM colaboran y el humano ejecuta comandos que producen credenciales. Mismo patrón en CI/CD setup, cloud provider keys, OAuth flows, database passwords iniciales. Mismo principio: el chat persiste lo que entra, asumirlo.

**Aplicado en:**
- Sesión actual: `client_secret` del OAuth client `350502639252-...` y `refresh_token` Gmail de `gonzalo.perez@demingroupmadrid.com` expuestos en chat. PM aceptó no rotar. Riesgo aceptado: Desktop client_secret semi-público por design + refresh_token revocable desde `https://myaccount.google.com/permissions` si Gonzalo detecta abuso. Workspace Internal restringe quién puede autorizar la app a la organización demingroupmadrid.com.
- **Trigger inmediato B3 (Hunter Starter API key)**: cuando llegue, Code propone explícitamente al PM: "guarda en `.env.dev`/`.env.prod` directamente, NO pegues en chat". Si PM la pega igualmente, Code captura como segunda iteración del patrón y propone rotar (Hunter permite reset trivial). Si PM acepta exposure, anotar decisión en commit message del integration.
- `scripts/gmail_oauth_setup.py` queda anotado como "TODO Fase 3: revisar si el print a stdout del refresh_token es necesario o podemos quitarlo y obligar uso del fichero, reduciendo superficie de exposure por inercia copy/paste".
- Esta lección.

**Trigger de aplicación inmediata:** B3 Hunter API key (próximo bloqueador). Sprint 5 cuando llegue infra adicional con secrets (MillionVerifier, posiblemente Phantombuster). Fase 3 si entra Postmaster Tools API key.

---

## 2026-05-12 — Lección 32: cuando se deroga una regla operativa fijada en §9.x del plan, exigir paper trail (justificación + decisión nueva en §3 + lección) ANTES de tocar código, no después

**Contexto:** Sprint 4 paso 7, pre-B5 smoke E2E. PM solicitó que `send_gmail._FOOTER` no incluyera la línea de opt-out (*"Si no quieres recibir más mensajes, responde STOP..."*) que el plan §9.3 fijaba como obligatoria en cada correo desde la sesión 2026-04-29 (Bloque A). PM justificó: *"decisión PM cerrada anteriormente fue que el footer NO LLEVA opt-out"*. Code verificó el repo con grep (`tasks/` + `apps/`) — la supuesta decisión NO existía documentada. Lo opuesto sí estaba en 7 sitios del repo (§9.3 literal, §14 paso 7 dos veces, Apéndice A regla 1, Lección 1 con razón legal LSSI/RGPD, y el propio OK del PM al plan paso 7 en esta misma sesión). Adicionalmente el teléfono `+34 692 319 217` que PM aportó no aparecía en ningún lado del repo (verificado tras lectura de docs/ confirmó que sí estaba en dossier comercial + onboarding PDF — input legítimo nuevo, pero el meta-patrón sigue siendo válido: PM proponía cambio sin paper trail).

Code paró (criterio de parada 3 paso 7 + regla 9 Apéndice A) y pidió justificación escrita ANTES de tocar código. PM eligió opción "decido AHORA quitar opt-out, asumo riesgo legal" + razón operativa *"la estética no compensa el riesgo de deliverability con dominio aún relativamente nuevo"*. NO aportó asesoría legal específica. Code procedió a aplicar el cambio + documentar D24 + esta lección.

**Corrección humana implícita:** Code reportó originalmente al cierre paso 7 *"footer opt-out + firma + tests"* como entregable hecho según §9.3. PM derogó después. La regla no es "Code no debe entregar el opt-out porque va a cambiar" — la regla es "antes de derogar reglas operativas del plan, exigir paper trail explícito". Sin paper trail, una auditoría futura (denuncia AEPD, peritaje, due diligence de inversor) verá *"Code eliminó opt-out"* sin justificación visible — peor que documentar la decisión con razón explícita por mala que sea la razón.

**Regla resultante:**

- **Cuando PM solicite derogar una línea/regla operativa fijada en §9.x o §10.x del plan (anti-spam, validación post-generación, política de cadencia, etc.), Code DEBE bloquear antes de tocar código y exigir:**
  1. **Verificación**: grep en `tasks/` + `apps/` buscando si la decisión ya está documentada. Si está, citarla y proceder. Si NO está (caso típico cuando PM atribuye a "decisión cerrada anterior" que solo vive en su cabeza), pasar al siguiente paso.
  2. **Justificación escrita literal del PM**: 1-2 líneas mínimas. Las dos formas aceptables son (a) "asesoría legal/operativa X dice Y" o (b) "no tengo asesoría, asumo el riesgo de forma consciente porque Z". Una tercera "PM dijo y punto" sin razón = paper trail roto = bloquear hasta tener razón.
  3. **D# nueva en §3 decisiones cerradas** del plan con: fecha + texto literal de la justificación PM + cita de las §§ derogadas + cita del mecanismo alternativo si existe (en este caso, §11.3 detección de opt-out por keywords sigue activo).
  4. **§ original derogada** con tachado HTML + nota inline citando la D# nueva. NO borrar la línea original — preservar la cadena evidencia "antes decía X, ahora dice Y porque D#".
  5. **Lección capturando el meta-patrón** (no la decisión específica) para que el próximo derogue siga el protocolo.
  6. **Test específico que previene regresión** (en este caso `test_footer_does_NOT_contain_optout_text`). Si un futuro Code o humano re-introduce la línea sin actualizar D#, el test grita.
  7. **Apéndice A NO se toca** salvo que la derogación ataque una de las 12 reglas no-negociables literalmente. §9.3 line items NO son Apéndice A — son política operativa. La regla 1 sobre HITL approval sí es Apéndice A y NO se toca aquí.
- **El "asumo el riesgo" del PM es justificación aceptable, pero debe quedar literal en D#.** Una auditoría futura ve *"PM 2026-05-12: asumo riesgo LSSI/RGPD, sin asesoría legal documentada"* y entiende. Ve *"Code eliminó opt-out"* sin más y no entiende.
- **Code no debe inventar justificación legal por el PM.** Si el PM dice "asumo riesgo" sin más, Code transcribe literal. NO escribir "según asesoría legal X" si no es cierto.

**Aplicable más allá de DEMIN:** cualquier sistema con políticas operativas documentadas que un PM/owner quiera relajar. Patrón meta: la derogación silenciosa de una regla (commit que solo cambia código sin tocar plan) es peor que la derogación documentada con razón mala — porque la silenciosa se pierde en auditoría y la documentada deja rastro. Aplicable a flags de seguridad (rate limits, validations, GDPR consent flows, audit logging), no solo a opt-outs de email.

**Aplicado en:**
- `tasks/todo.md` §9.3: línea opt-out con `~~tachado~~` + cita D24 + razón literal PM + mecanismo alternativo (§11.3 keywords).
- `tasks/todo.md` §3 D24 nueva con justificación literal *"asumo el riesgo legal"* + *"la estética no compensa el riesgo de deliverability con dominio aún relativamente nuevo"* + composición footer + ruta evidencia teléfono (`docs/dossier_demin.pdf` + `docs/onboarding_demin.pdf`).
- `tasks/todo.md` §14 paso 7 B5: cita explícita *"footer D24 renderizado (sin línea de opt-out)"* para que el smoke valide la composición correcta.
- `apps/workers/outreach/send_gmail.py:_FOOTER`: composición nueva + comment header citando D24 + Lección 32.
- `apps/workers/tests/test_send_gmail.py`: `test_footer_does_NOT_contain_optout_text` (previene regresión) + `test_footer_contains_sender_identity` actualizado con "Responsable DEMIN Group" + "+34 692 319 217".
- Apéndice A intacto (la derogación no afecta a las 12 reglas).
- Esta lección.

**Trigger de aplicación inmediata:** próxima vez que PM solicite derogar política operativa fijada en §9.x/§10.x/§11.x del plan. Antes de tocar código: protocolo de 7 pasos arriba. Si PM se niega a aportar justificación literal o se molesta con el protocolo, Lección 32 misma justifica el bloqueo — "esto es paper trail, no fricción burocrática".

---

## 2026-05-13 — Lección 33: copiar logs/observaciones en docs del repo es un vector de leak de secrets tan real como pegar configs — `httpx` y similares loguean URLs completas con `?api_key=…` en cleartext

**Hermana de Lección 31** (secrets en chat por inercia) pero en otro vector: la doc operativa del repo. Lección 31 cubre el canal *chat humano↔Code*; Lección 33 cubre el canal *log → copy/paste → archivo versionado*.

**Incidente real (paso 4 Sprint 4, 2026-05-04, commit `d623bf5`):** durante el cierre de paso 4 se documentó en `tasks/todo.md` §19 (línea 1698) una observación lateral legítima — "`httpx` loguea la URL completa de cada request en INFO, incluyendo `?api_key=…` en cleartext, riesgo si los logs viajan a Sentry/CloudWatch/ELK". El problema: **el ejemplo se pegó con la API key real de Hunter en lugar de un placeholder**. Quedó dormido 9 días hasta que GitGuardian lo detectó (2026-05-13) y notificó por email. PM rotó key inmediatamente, se redactó la línea, se redactó la nueva key con placeholder `<REDACTED-2026-05-13-tras-leak-GitGuardian>`. Coste: pánico de 30min + decisión sobre purga de history (git-filter-repo + force push) pendiente al cierre de esta lección.

**Por qué Lección 31 no lo previno:** Lección 31 codifica "secrets en chat = pasan, no fingirlo". Pero el threat model ahí era *chat efímero entre humano y Code*. El leak de hoy ocurrió en el otro canal: **doc estática versionada, con el secret incrustado como "ejemplo realista" en una observación técnica genuina**. El operador (yo, Code) no flagué porque la observación era válida y el contexto era "deuda técnica documentada", no "credencial expuesta". La ceguera fue: tratar la línea como narrativa técnica, no como string que va a `git log`.

**Regla operativa (cubre lo que Lección 31 no cubre):**

1. **Cualquier string en `tasks/`, `docs/`, comments de código o commits que se parezca a un secret debe ir con placeholder, no con valor real.** Patrones: hex largo (≥32 chars), JWTs (`eyJ…`), `Bearer …`, `Basic …`, `sk_…`, `1//…` (Google refresh_token), `xoxb-…` (Slack), `?api_key=`/`?token=` en URLs, paths con `/credentials/`/`/secrets/`. Si dudas → placeholder.
2. **Cuando copies output de comando que invocó un secret** (curl, httpx logs, scripts de probe), revisa el output ANTES de pegarlo en un archivo. Si el secret aparece en query params, headers, o body de error → reemplaza por `<REDACTED>` o `<API-KEY>` antes de hacer commit.
3. **Documentar observaciones técnicas sobre secrets (como esta de `httpx`) sin pegar el secret real**. Forma correcta: *"`httpx` loguea URLs completas incluyendo `?api_key=<key real>` en cleartext"* — el placeholder hace la observación igual de clara sin crear deuda.
4. **Pre-commit / git hook eventual** (`detect-secrets` o `gitleaks` en `.pre-commit-config.yaml`) como red de seguridad de defensa en profundidad, NO como sustituto del protocolo arriba. La detección por terceros (GitGuardian → email) llegó tarde: la rotación se hizo 9 días después del leak.
5. **Cuando se redacta retrospectivamente** (como hoy con la key Hunter en línea 1698): nota explícita en la propia línea citando fecha + razón + lección, para que la deuda técnica documentada NO se pierda con la redacción. Forma: `... <REDACTED-YYYY-MM-DD-tras-leak-<source>>. <NN-NN>: la versión original ... Lección NN en lessons.md.`
6. **Verificar `.gitignore` ANTES de cualquier commit que toque archivos con secrets por contrato**: `.env`, `.env.*` (excepto `.env.example`), `credentials*.json`, `oauth_token*.json`, `.gmail_refresh_token_*`, `service-account*.json`, `*-private-key*`, `id_rsa*`, claves PGP/SSH en general, exports de `gcloud auth`/`firebase login`, snapshots de Supabase Vault. Aunque el incidente de hoy (key Hunter en `tasks/todo.md`) NO fue un fallo de `.gitignore` (era un doc versionado por diseño), la regla cubre la otra mitad del threat model: cuando el operador edita o genera un fichero que SÍ tiene contenido sensible por contrato y lo commitea por descuido. Comando rápido: `git check-ignore -v <path>` confirma que el match aplica antes de stage. Si `.gitignore` no cubre un patrón conocido peligroso, ampliarlo primero, commit del `.gitignore`, y solo después tocar el archivo sensible.

**Diferencia con Lección 31 — clarificación:**

- Lección 31 → "PM pega secrets en chat". Threat model: `chat efímero` + `humano confunde Code con sysadmin`. Mitigación: ofrecer canal alternativo (filesystem) y aceptar el riesgo si PM lo asume.
- Lección 33 → "secrets entran en docs del repo por copia descuidada". Threat model: `git permanente` + `Code y humano copian outputs sin sanear`. Mitigación: protocolo de placeholder + revisión de output antes de commit + hook eventual.

**Coste real del leak (registrado para calibrar futuras decisiones):** key rotada (gratis, mismo plan Starter), 9 días de exposición histórica en commits `d623bf5..HEAD~1`, redacción de HEAD (1 commit), purga de history pendiente decisión PM (force push a `main`). Bajo riesgo de uso por terceros (key seguía siendo válida al detectarse, no se observó tráfico anómalo en quota Hunter — 0 búsquedas usadas tras rotación con la key nueva), pero el riesgo de "qué pasa si OTRO scraper de claves la encuentra en el commit antes que GitGuardian" no se puede medir retrospectivamente. Decisión: aplicar protocolo arriba como NO negociable para todo `tasks/`, `docs/`, commits y comments de aquí en adelante.

**Trigger de aplicación inmediata:** siguiente vez que vaya a documentar una observación técnica que incluya un secret real (output de probe, log de error, ejemplo de config) en cualquier archivo versionado — pasar el contenido por el protocolo de 5 reglas arriba antes de Edit/Write. Si dudas si una string es un secret, asumir que sí y redactar; el coste de un placeholder de más es cero, el coste de un secret de más son días de pánico.

---

## 2026-05-13 — Lección 34: env vars del cloud target (Vercel/Render/Fly/etc.) deben auditarse cross-referenciando contra `.env.<env>` local del repo ANTES de declarar un deploy productivo cerrado — "parecen OK" no basta cuando hay 2 environments con FK schemas y seed idénticos

**Contexto:** durante el cierre de B6 (Sprint 4 paso 7, 2026-05-13), Gonzalo entró a `https://demin-system.vercel.app/approval-queue` y vio "No hay drafts pendientes" pese a que la BD prod tenía 2 drafts confirmados con SQL directo y con reproducción del query exacto vía PostgREST. Tras ~40 min de debugging descartando hipótesis sobre RLS, embeds PostgREST anidados, deploy stale post-filter-repo, cache Next.js, y varias más, la causa raíz resultó ser combinada — la mitad **(Lección 35)** sobre Supabase Auth Site URL desviando a localhost, la otra mitad sobre **env vars cross-env**:

- `SUPABASE_SERVICE_ROLE_KEY` en Vercel prod era el **JWT legacy de DEV** (`eyJ...`), no la `sb_secret_6El5MggRwc...` de prod.
- Vino de un copy/paste antiguo (probablemente al crear el proyecto Vercel inicialmente, antes de que prod migrara al formato nuevo `sb_secret_*`).
- Se camufló durante días porque la única vez que se había mirado el dashboard prod, PM acabó en localhost (Lección 35). Y nadie había validado un read sobre `messages` desde Vercel real hasta el momento del HITL.

PM verificó el bug comparando 50 chars de la legacy JWT en Vercel contra la legacy JWT que Supabase mostraba en el proyecto prod — no coincidían. Por descarte, era la del proyecto dev.

**Corrección humana:** PM hizo el cross-reference de JWTs manualmente (50 chars). Antes de eso, mi diagnóstico había avanzado por descarte (RLS, embeds, cache, force-push), todo correcto pero todo PARALELO al bug real. No tenía visibilidad sobre los values de Vercel, así que no podía cerrar el caso solo — el bug solo se diagnostica con datos del cloud target.

**Regla resultante (cubre tanto pre-deploy como post-incident):**

Antes de cualquier deploy de producción de un servicio con env vars sensibles (Vercel, Render, Fly, Cloud Run, Railway, etc.), y tras CUALQUIER incidente que sospeche de config:

1. **Listar TODAS las env names** del environment de cloud target. Comando: `vercel env ls production` (Vercel CLI) o copiar del UI.
2. **Cross-referenciar uno a uno** contra `.env.prod` (o equivalente canónico en el repo) usando `comm -3 <(sort cloud-names.txt) <(grep -oE '^[A-Z_]+=' apps/<service>/.env.prod | tr -d = | sort)` para detectar omitidos en ambas direcciones.
3. **Comparar prefijo + longitud** (no el value exacto — el local puede ser placeholder o legacy format). Si la canónica es `sb_secret_*` (41 chars) y la del cloud es `eyJ...` (200+ chars), es mismatch ruidoso. Si la canónica es URL `https://stxicalzpwrcjpaqdkdb.supabase.co` y la del cloud apunta a otro subdominio, también.
4. **Validar funcionalmente AL MENOS UN READ** sobre cada tabla crítica desde el cloud target (no solo desde local) ANTES de invitar a usuarios externos. En este caso: una llamada de smoke a `SELECT * FROM messages LIMIT 1` desde el dashboard Vercel (no desde mi PostgREST local) habría detectado el bug instantáneamente.
5. **Auditoría obligatoria tras INCIDENTE de env vars:** si UNA env var estaba mal en el cloud, asumir que pueden estar mal MÁS y auditar TODO el set, no solo la flagged. Pendiente para próximo turno (PM autorizó): auditar `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `HUNTER_API_KEY`, `DATABASE_URL`, `ALLOWED_EMAILS`, modelos LLM, etc. en Vercel.

**Why:** los env vars cross-env (dev↔prod) son una fuente de bugs en producción difícilmente diagnosticables porque NO fallan ruidosamente. Una key de dev en un cloud prod puede:

- **Funcionar para algunas tablas y no para otras** — la key de dev contra prod URL devolvió 401 silencioso en `messages` pero PostgREST/Next.js no propagó el error, terminando como `data=[]`. Si la URL hubiera sido también la de dev, todo habría funcionado contra dev (FKs idénticas, schema idéntico).
- **Hacer aparecer datos del proyecto wrong sin distinción visual** — dev y prod tienen el mismo seed (5578 companies), así que `/pipeline` mostraba 5578 en cualquier configuración. El conteo NO discrimina. Las únicas tablas discriminadoras eran `messages` y `mailboxes.current_day_sent`, pero solo se miran en pantallas específicas.
- **Sobrevivir auditorías superficiales** — PM verificó URL ✓ y ANON_KEY ✓ (con valores correctos en Vercel), pero NO el SERVICE_ROLE_KEY. La regla mata exactamente este sesgo: auditar **todas** las env vars, no solo las que se sospechan a primera vista.

**How to apply:** próximo turno (auditoría env vars Vercel pendiente). Y para CUALQUIER próximo deploy en cloud: aplicar el protocolo de 5 pasos antes de declarar "deploy cerrado". Coste extra: ~5 min de cross-reference. Coste de saltar: 40 min de debugging con conclusiones potencialmente erróneas, usuarios externos esperando (Gonzalo).

---

## 2026-05-13 — Lección 35: Supabase Auth `Site URL` debe ser la URL canónica de producción ANTES del primer magic link a un usuario externo — localhost va en Redirect URLs whitelist, NUNCA en Site URL

**Contexto:** durante el cierre de B6 (Sprint 4 paso 7, 2026-05-13), PM reportó que `/approval-queue` mostraba "No hay drafts pendientes" pese a BD prod con 2 drafts. Yo descarté varias hipótesis sobre RLS, embeds PostgREST, cache Next.js, deploy stale post-filter-repo. La mitad del bug resultó ser env vars (Lección 34), pero la OTRA MITAD que confundió todo el flow:

- **`Site URL`** en Supabase Auth del proyecto prod estaba como `http://localhost:3000` (de cuando PM empezó a desarrollar el dashboard local).
- PM había pedido un magic link DESDE su localhost días antes para testear el flow auth.
- El magic link enviado por Supabase llevaba como redirect el `emailRedirectTo` del client: `window.location.origin + '/auth/callback'` = `http://localhost:3000/auth/callback`. Esto es coherente con el código `login-form.tsx:32`.
- PM clicó el link ANTIGUO desde Gmail (días después, ya en el flow productivo). Lo abrió en nueva pestaña.
- El link iba a `http://localhost:3000/auth/callback?code=...`. PM tenía `next dev` corriendo en local (con `.env.local` apuntando a BD dev). La sesión se completó allí.
- **PM creía que estaba en `demin-system.vercel.app`** — el dashboard visual es idéntico, el dominio en la barra de direcciones lo miró por encima y el flow de auth no es ruidoso sobre dónde acaba. En realidad estaba en `localhost:3000` con BD dev.

Síntomas que generaba: `/pipeline` 5578 empresas ✓ (coincide ambas BD), `/metrics` 2 sent + 3 cancelled (coincide con dev tras smokes B5), `/approval-queue` 0 drafts (coincide con dev — los drafts dev ya estaban sent post-B5).

**Corrección humana:** PM detectó la causa tras revisar con más calma la URL real del browser. La mismísima pista que yo no le pedí explícitamente al principio (DevTools Network o URL bar). Captura el patrón meta: cuando los datos no coinciden con lo esperado, **antes** de hipótesis sobre código/RLS/keys, **verificar que estás mirando lo que crees que estás mirando**.

**Regla resultante:**

Para CUALQUIER proyecto que use Supabase Auth con magic links u OAuth, antes del primer link enviado a un usuario externo (Gonzalo, clientes, beta testers):

1. **`Site URL`** en Supabase Dashboard → Authentication → URL Configuration debe ser el **dominio canónico de producción** (e.g. `https://demin-system.vercel.app`). NUNCA `http://localhost:PORT`. Site URL es el FALLBACK que Supabase usa cuando el `emailRedirectTo` solicitado no matchea ningún Redirect URL whitelisted; si Site URL es localhost, ese fallback dirige a localhost.
2. **Redirect URLs whitelist** puede incluir tanto prod como localhost (paths específicos o wildcards `/**`). Permitir login local en dev NO compromete prod, mientras Site URL sea prod.
3. **Wiring final correcto** (cuño para próximos proyectos):
   ```
   Site URL: https://<prod-domain>
   Redirect URLs:
     https://<prod-domain>/auth/callback
     https://<prod-domain>/**
     http://localhost:3000/auth/callback
     http://localhost:3000/**
   ```
4. **Smoke obligatorio antes de invitar usuario externo:** pedir magic link desde browser fresh (incógnito) en la URL de prod. Abrir DevTools Network → verificar que el link en el email arranca con `https://<prod-domain>/auth/callback?code=...`, NO con `localhost`. Si arranca con localhost, parar — Site URL/whitelist mal configurado.
5. **Recomendación operativa para sesiones mixtas dev+prod:** usar perfil/ventana de incógnito separado para dev local. Cookies de `demin-system.vercel.app` y `localhost:3000` son técnicamente independientes pero un usuario en la misma sesión browser puede acabar autenticado en uno y mirar otro sin notarlo. PM tuvo este síntoma exacto.

**Why:** un magic link mal-direccionado contamina TODO el debugging downstream porque el bug es "los datos no coinciden con lo que esperas" — un síntoma no-específico que invita a hipotetizar sobre código/RLS/cache/redes ANTES de comprobar lo más simple: ¿estoy mirando la URL que creo? Yo gasté ~40 min descartando hipótesis sobre Vercel, RLS, embeds, force-push del filter-repo, etc., antes de que PM revisara la URL real de su navegador. El coste fue alto: Gonzalo esperando, rate-limit posterior del Auth, dos lecciones que capturar.

**How to apply:** próximo proyecto nuevo con Supabase Auth — primer paso ANTES de habilitar `signInWithOtp` o `signInWithOAuth`, ir a Supabase Dashboard → Authentication → URL Configuration y aplicar el wiring de regla 3. Y siempre antes de un debugging de "datos no coinciden": pedir al humano que confirme dominio real del browser. Coste: 5 segundos. Ahorra horas.

---

## 2026-05-14 — Lección 36: OAuth scopes nuevos requieren bloqueador humano documentado pre-implementación, no descubrirlos durante deploy

**Contexto:** Sprint 5 Fase 3, construcción de `poll_imap.py` (worker que lee replies del buzón Gmail Gonzalo). El plan §11.1 dice "Worker `poll_imap.py` lee respuestas de los 3 buzones". Diseño técnico durante implementación: usar Gmail REST API en lugar de IMAP literal (mismo flujo OAuth, API más limpia). **Detección post-implementación**: el `refresh_token` actual de Gonzalo (paso 7 B1, scope `gmail.send`) NO alcanza para leer mensajes. Gmail API requiere `gmail.readonly` o `gmail.modify` (este último para marcar como leído tras procesar). Cualquier de los 2 son scopes distintos del `gmail.send` actual.

El consent OAuth de Gonzalo cubre solo `gmail.send`. Para ampliar el scope:
1. Modificar `scripts/gmail_oauth_setup.py` con scope ampliado.
2. Gonzalo re-autoriza la app en consent screen de Google Cloud Console.
3. Re-correr setup + `seed_oauth_token.py --env prod` para guardar nuevo refresh_token en Vault.
4. Workers de Fase 3 ya funcionan E2E.

Esto se llamó "Bloqueador humano B7" en §19. Fue **descubierto durante el deploy E2E** del primer timer poll_imap en VPS (logs mostraron 403 Forbidden de Gmail API). El worker manejó el error correctamente (raise GmailAuthError → exit 3 → SuccessExitStatus=0 3 4 systemd) pero el flow productivo no funciona hasta que se resuelva B7.

**Corrección humana parcial (auto-aplicada por Code):** debió haberse detectado ANTES de construir el worker, no DESPUÉS de desplegarlo. La regla `Apéndice A regla 9` (parar cuando detectes desviación del plan) aplicaba aquí, pero no se aplicó porque el "desviación" era sutil: el plan original §11.1 dice "poll_imap" (sugiriendo IMAP) y la implementación con Gmail API es elegante pero requería un scope OAuth que no estaba documentado en pre-requisitos.

**Regla resultante:**

- **Antes de implementar cualquier worker nuevo que consuma una API externa, verificar explícitamente el scope/permisos requeridos contra los ya concedidos.** Patron meta: si una API es nueva (no se usó antes en el proyecto), su scope OAuth puede diferir del que ya está consented. Mismo OAuth provider, mismo refresh_token, ≠ misma capacidad.
- **Documentar el scope requerido en el header del worker** (línea 1-5 del docstring): "Requiere scope OAuth `gmail.modify`. Si solo está consented `gmail.send`, falla con 403 → bloqueador humano." Esto evita re-descubrir el problema en deploy.
- **Crear bloqueador humano explícito (Bn) ANTES de desplegar el worker, no después.** El patron Sprint 4 paso 7 (B1-B6) era correcto: cada pre-requisito humano documentado pre-deploy. Sprint 5 Fase 3 introdujo B7 reactivamente — debió ser proactivamente, antes del primer commit del worker.
- **Convención de exit codes documentada en el worker** (3 = bloqueador externo conocido, no fatal; SuccessExitStatus en systemd unit refleja la convención). Esto permite que el deploy no marque "failed" al sistema operations team mientras se resuelve el bloqueador.

**Aplicable más allá de DEMIN:** cualquier proyecto que use OAuth con scopes granulares (Google, Microsoft, Slack, GitHub) — auditar pre-implementación los scopes que cada nuevo worker requiere vs los ya consented por el end-user owner.

**Aplicado en:**
- `apps/workers/replies/poll_imap.py` docstring inicial cita B7.
- `infra/systemd/demin-poll-imap.service` con `SuccessExitStatus=0 3 4`.
- `tasks/todo.md` §14 Fase 3 + §19 entrada 2026-05-14 documenta B7 explícito.
- Esta lección.

**Trigger de aplicación inmediata:** próximo worker que consuma una nueva API externa (Postmaster Tools API en Sprint 5+, MillionVerifier en Sprint 6+, etc.) — auditar scope pre-implementación, documentar bloqueador humano si aplica, antes del primer commit.

---

## 2026-05-14 — Lección 37: sesiones asistidas con goal autónomo necesitan reportes periódicos cada N turns + caps de presupuesto duros

**Contexto:** Sprint 4 paso 8 + paso 9 + Sprint 5 Fase 3 construidos en una sola sesión asistida (Claude Opus 4.7 + PM Alberto presente al arranque, ausente durante ejecución). PM autorizó `/goal` literal con scope ambicioso ("paso 7 + 8 + 9 + Fase 3 entera + 7 días piloto autónomo después"). Caps PM autorizados: $15 LLM acumulado, 150 Hunter calls, VPS Hetzner ya pagado.

Code procesó: 4 commits Fase A (poblamiento), 4 systemd units VPS paso 8, 5 commits saneamiento + cierre Sprint 4, 6 commits Sprint 5 Fase 3 (workers + prompts + UI + systemd + docs). Total acumulado: 13 commits + push, ~$0.90 LLM (de $15 cap), 60 Hunter (de 150 cap), ~3h tiempo asistido.

**Observaciones del proceso:**

- **Auto-pausa por context budget no aplicó.** Code no se quedó sin context ni cerca. El cap real fue *turns* (~80 autorizados, ~55 usados antes del cierre Sprint 5).
- **Caps presupuestarios fueron muy conservadores vs realidad.** $15 LLM autorizados, $0.90 consumido (6%). 150 Hunter autorizados, 60 consumidos (40%). PM puede ser más generoso en futuras sesiones similares — el riesgo real no fue gasto sino tiempo + scope creep.
- **Scope creep fue real.** Sprint 4 paso 8 (auto_replenish + VPS) y paso 9 (saneamiento) entraban naturalmente. Sprint 5 Fase 3 entera fue **ambicioso** y se cumplió al ~85% (8 entregables ✓, 2 diferidos a Sprint 6: /metrics ampliada, /settings toggle HITL). Lección: cuando PM autoriza "Fase 3 entera", explicitar al arranque qué scope realista entra en una sesión (decisión senior eng) vs qué se difiere.
- **Reportes intermedios al PM funcionaron en text-only.** PM ausente durante ejecución pero leerá los reportes al volver. Sin reportes, sería un blob de 50 turns sin estructura legible. Reportes cada ~10 turns (Fase A cierre, Fase B cierre, Sprint 4 cierre) dieron la estructura.

**Regla resultante:**

- **En sesiones asistidas tipo `/goal` con PM ausente durante ejecución, reportar progreso cada 10-15 turns o al cierre de fases lógicas.** Formato: una línea por entregable + estado + coste acumulado + bloqueadores. Esto permite al PM hacer revisión async eficiente al volver.
- **Antes de aceptar `/goal` con scope ambicioso, explicitar al arranque qué entregables son "garantizados hoy" vs "probables" vs "scope creep aspiracional".** En esta sesión Code hizo eso al inicio (mensaje "scope assessment"). Replicar en próximas sesiones.
- **Caps presupuestarios pueden ser ~2x más generosos sin riesgo real.** Este proyecto consume $0.005-0.05 por unidad de trabajo (research + draft + classify) y los caps duros son holgados. PM puede autorizar $30-50 LLM por sesión asistida sin overshoot real.
- **Sprint completo entero (e.g. "Sprint 5 = Fase 3") es scope realista en 1 sesión asistida** cuando:
  - PM ausente pero pre-autorizado.
  - Code Opus 4.7 1M context (caben todos los archivos del repo).
  - Workers Python tienen patrones repetibles (CLI argparse + idempotencia + tests).
  - UI dashboard Next.js tiene componentes ya construidos para reutilizar.
- **Pantallas dashboard ambiciosas (e.g. /metrics ampliada) NO siempre caben en la misma sesión.** Pueden requerir migration BD + actions server-side + componentes interactivos cliente-side. Diferir a Sprint siguiente cuando el scope crítico (workers + cron + smoke E2E) consume el budget de turns.

**Aplicable más allá de DEMIN:** cualquier proyecto donde un humano supervisor autoriza autonomía a un LLM para múltiples turns — formato reportes + caps presupuestarios + scope creep gestionado son universal.

**Aplicado en:**
- Esta sesión: 3 reportes intermedios al PM (Fase A→B, Sprint 4 cierre, Sprint 5 cierre).
- §19 todo.md: entradas estructuradas por sub-fase con métricas comparables.
- `tasks/todo.md` §14 Fase 3 con [x] / [-] / [ ] explícito para diferenciar construido vs diferido vs pendiente humano.
- Esta lección.

**Trigger de aplicación inmediata:** próxima sesión asistida `/goal` con PM ausente. Aplicar formato reporte + scope assessment + caps generosos desde el arranque.

---

## 2026-05-25 — Lección 38: pausa de Lemwarm tras un mes de warmup y score 97/100 validado

**Contexto:** el buzón `gonzalo.perez@demingroupmadrid.com` lleva ~1 mes en warmup continuo con Lemwarm. Score actual **97/100**, **802 emails calentando acumulados, 0 blacklists**, mensaje del propio Lemwarm: *"You can start your campaigns"*. Coste Lemwarm: ~29€/mes. Total mensual del sistema: ~70€/mes sobre techo de 150€ (hay margen, pero la línea Lemwarm es la más fácil de optimizar sin riesgo).

**Decisión PM (2026-05-25):** cancelar Lemwarm. Ahorro: ~29€/mes.

**Razón:** el score 97/100 ya valida la reputación del dominio + buzón; mantener warmup activo cuando hay envío productivo regular es redundante (el propio outreach genera tráfico human-like que mantiene la reputación). Lemwarm cumplió su función como puente entre dominio nuevo y primer batch productivo (paso 7 cap 20/día Lección 30); a partir de aquí el propio sistema sostiene la deliverability.

**Regla resultante:**

- **El warmup externalizado (Lemwarm o equivalente) es una palanca de arranque, no un coste recurrente perpetuo.** Una vez el score del proveedor llega a ≥95/100 sostenido + ≥4 semanas + ≥500 emails calentando + envío productivo regular en curso, el ROI del warmup activo cae a cero. Cancelar libera presupuesto sin degradar deliverability.
- **Trigger de cancelación:** los 4 criterios juntos (score, tiempo, volumen, productivo activo). Si falta alguno (ej. pausa de outreach >2 semanas por holiday), reactivar Lemwarm antes de reanudar — la reputación caduca con la inactividad (capturado en Lección 27 al final).
- **Reactivación de emergencia:** si en algún momento Postmaster Tools muestra degradación del dominio (warning amarillo/rojo) o bounce rate >2% sostenido, reactivar Lemwarm como medida correctiva. Coste de reactivación: 29€ del primer mes + 2-3 semanas para volver a score >90.
- **Aplicable más allá de DEMIN:** cualquier servicio externo de "warmup" o "reputation booster" tiene la misma curva — útil al arranque, redundante en operación continua, reactivable si hay degradación. Aplica también a calentamiento de cuentas LinkedIn, dominios secundarios, números SMS para 2FA, etc.

**Acción humana ejecutada (PM):** cancelación en panel Lemwarm (`lemlist.com` → Settings → Billing → Cancel Lemwarm subscription). No afecta a Lemlist core si en algún momento se contrata Lemlist Sales Engine — son productos separados con billing separado.

**Aplicado en:**
- `tasks/todo.md` §17 actualizado: Lemwarm pasa de "29-58€/mes" a "0€ (cancelado 2026-05-25 — ver Lección 38)".
- `tasks/todo.md` §4 stack técnico: nota inline "cancelado tras validación reputación (Lección 38)".
- `tasks/todo.md` §19 entrada del 2026-05-25 con la decisión y ahorro.
- `tasks/lessons.md` esta lección.

**Numeración corregida:** PM tituló el input "Lección 9" — typo evidente (la 9 está ocupada desde 2026-04-29 con "el KB capturado en sesión 1 desvía del plan en 6 puntos"). La numeración correcta es **38** siguiendo Lección 37 (2026-05-14). Patrón ya cubierto por Lección 20 (verificar último número con grep antes de elegir el siguiente).

---

## 2026-05-25 — Lección 39: cambios de producto tras 12 envíos en producción (saludo, footer, cadencia, criterio interesado)

**Contexto:** tras observar los primeros 12 envíos productivos entre el 14 y el 19 de mayo, el PM identificó cinco ajustes de producto necesarios antes de escalar el sistema a modo autónomo. Los cambios responden a feedback de calidad del contenido generado y a una recalibración de la cadencia operativa.

**Decisiones (todas cerradas por PM):**

### 1. Saludo neutro en correo de apertura

El LLM debe abrir el cuerpo del correo de apertura con un saludo cercano y NEUTRO (sin marca temporal) antes de entrar en materia. Varía con criterio entre fórmulas naturales:

- "Buenas [nombre], espero que estés bien"
- "Hola [nombre], espero que te pille bien"
- "Buenas [nombre], te escribo porque..."
- Variantes equivalentes sin marca temporal

**PROHIBIDO** "Buenos días" y "Buenas tardes" o cualquier saludo con franja horaria. Razón: el correo puede enviarse a una hora y abrirse muchas horas después; un saludo desincronizado con la hora real del destinatario delata el envasado en serie y queda raro.

Sin emojis, sin signos de exclamación. Mantiene el límite de 130 palabras del cuerpo.

Aplica solo al `opening`. El `reframe` y el `closing` no llevan saludo de apertura (son continuación de hilo).

### 2. Footer: "Un saludo" en lugar de "Un abrazo"

En `apps/workers/outreach/send_gmail.py`, la constante `_FOOTER` cierra con "Un saludo". La línea "Quedo atento a vuestra respuesta" se mantiene en el cuerpo del correo, no en el footer.

### 3. Cadencia D+14 / D+28 (sustituye D+12 / D+30 de Lección 4)

La secuencia activa `demin_v1` pasa a:

```json
[
  {"day": 0,  "angle": "opening"},
  {"day": 14, "angle": "reframe"},
  {"day": 28, "angle": "closing"}
]
```

**Esto sustituye explícitamente la cadencia D+0/D+12/D+30 indicada en la Lección 4.** La razón: PM detectó en producción que la cadencia real ejecutándose era ~D+5 (Jaime de Lena recibió opening el 14 may y reframe el 19 may), demasiado agresiva. Se elige D+14/D+28 como ritmo más natural y menos invasivo para B2B.

Mensajes con `status='scheduled'` no enviados aún deben recalcular `scheduled_for` según la nueva cadencia tomando como base `sent_at` del step 0. Los ya enviados no se tocan.

### 4. Respuestas tibias NO son `interesado`

En `classify_replies.md`: respuestas tipo "me guardo tus datos", "lo tendré en cuenta", "ya te diré", "interesante, hablamos cuando haga falta" se clasifican como `no_ahora` (no como `interesado`). Disparan re-engage a +60 días.

Solo cuenta como `interesado` una respuesta que pide reunión, llamada, presupuesto o equivalente compromiso CONCRETO con fecha/hora o intención clara de agendar.

### 5. Criterio de éxito real del seguimiento = llamada agendada

Un lead no se considera convertido hasta que hay compromiso de fecha/hora de llamada o reunión con Gonzalo. Hasta entonces se sigue insistiendo vía follow-up del modo normal (sin saltarse cadencia). El opt-out explícito sigue siendo, como siempre, el único motivo de exclusión permanente.

**Aplicado en (sesión 2026-05-25):**

- `apps/workers/shared/prompts/generate_email_opening.md` v2: sección SALUDO neutro + ejemplos.
- `apps/workers/shared/prompts/generate_email_reframe.md` v2: cabecera "Hace 14 días" + nota saludo neutro.
- `apps/workers/shared/prompts/generate_email_closing.md` v2: cabecera "Han pasado 28 días".
- `apps/workers/outreach/send_gmail.py`: `_FOOTER` con "Un saludo," (era "Un abrazo,").
- `apps/workers/tests/test_send_gmail.py`: `test_footer_contains_standard_closing` actualizado + regresión guard de "Un abrazo,".
- `apps/workers/shared/prompts/classify_reply.md` v2: `interesado` restringido a compromiso concreto + `no_ahora` ampliado con tibias.
- `apps/workers/outreach/follow_ups.py`: docstring D+14/D+28.
- `infra/supabase/migrations/20260525120000_13_seq_demin_v1_cadence_d14_d28.sql`: UPDATE sequences.steps + recálculo defensivo de `messages.status='scheduled'`.
- `apps/workers/tests/test_prompts_generate_email.py`: `test_opening_forbids_temporal_greeting`, `test_opening_mentions_neutral_greeting_variants`, `test_reframe_mentions_d14_in_system`, `test_closing_mentions_d28_in_system`.
- `tasks/todo.md` §9.2 actualizada con cadencia D+14/D+28.

---

## 2026-05-25 — Lección 40: el email del remitente NUNCA va en el cuerpo del LLM

**Contexto:** en el draft de Lena Construcciones (step 2 closing para Jaime Nozaleda) apareció en el cuerpo `gonzalo@demingroup.es`, dominio incorrecto (el correcto es `gonzalo.perez@demingroupmadrid.com`). Independientemente de si fue alucinación del LLM, dominio viejo en algún prompt, o copy-paste de un caso de prueba, el patrón de poner el correo del remitente en el cuerpo genera una clase entera de bugs evitables.

**Decisión PM (cierre del problema en origen):** el correo del remitente, el teléfono y la web van EXCLUSIVAMENTE en la firma generada por `send_gmail.py`. NUNCA en el cuerpo redactado por el LLM. Esto elimina toda posibilidad de error de dominio/email en el cuerpo.

**Regla resultante:**

- Todos los prompts de generación (`generate_email_opening.md`, `generate_email_reframe.md`, `generate_email_closing.md`, `generate_email_re_engage_*.md`) deben incluir una sección "PROHIBIDO" con la regla explícita: "NUNCA escribas el email del remitente, su teléfono ni su web en el cuerpo. La firma se añade automáticamente después. Si quieres dejar el contacto abierto, usa frases del tipo 'quedo a vuestra disposición' o 'podéis escribirme cuando os venga bien' sin incluir datos de contacto."
- Validación post-generación en `generate_draft.py` (§10.3 del plan): regex que rechaza cualquier `body` que contenga `@demingroupmadrid.com`, `gonzalo@demingroup.es` (dominio viejo), teléfono o web suelta. Si lo detecta: regenera (máx 2 reintentos) y luego marca para revisión humana con `_failed_validations: ['has_sender_leak']`.
- La firma de `send_gmail.py` se verifica que incluye: nombre, cargo, email correcto, teléfono, web.

**Por qué importa:** cualquier dato de contacto en el cuerpo es un punto de fallo. Si el LLM alucina un dominio (caso real arriba), el destinatario lo ve y la credibilidad del correo se hunde. Mantener email/teléfono/web SOLO en la firma generada por código garantiza que el dato sea siempre el correcto.

**Aplicado en (sesión 2026-05-25):**

- Bloque "PROHIBIDO — CONTACTO EN EL CUERPO" en los 3 prompts `generate_email_{opening,reframe,closing}.md` v2.
- `apps/workers/pipeline/generate_draft.py`: `_SENDER_LEAK_RE` regex multi-variante + integración en `validate_post_generation` (devuelve `has_sender_leak` al fallar).
- `apps/workers/tests/test_generate_draft.py`: parametrizado con 13 variantes positivas (incluido el caso real `gonzalo@demingroup.es`) + 2 casos negativos (sin sender leak / email tercero no dispara).
- `apps/workers/tests/test_prompts_generate_email.py`: `test_prompt_forbids_sender_contact_in_body` parametrizado sobre los 3 prompts.

---

## 2026-05-25 — Lección 41: bugs detectados en producción tras 12 envíos — cadencia agresiva y pool de contactos pequeño

**Contexto:** PM revisó la cuenta `gonzalo.perez@demingroupmadrid.com` el 25 de mayo y detectó dos anomalías graves en el comportamiento del sistema en producción:

1. **Cadencia mal calibrada.** Jaime Nozaleda (Lena Construcciones) recibió el opening el 14 de mayo y el reframe el 19 de mayo — solo 5 días después, no 14 como dice el plan ni 12 como dice la Lección 4. Tampoco coincide con la cadencia original §9.2 del plan (D+0/D+4/D+10). Algo está leyendo mal `sequences.steps` o tiene fechas hardcoded en `follow_ups.py`. **Diagnóstico cerrado:** `sequences.steps` seedeada en migration 11 venía con la cadencia §9.2 D+0/D+4/D+10 (no la Lección 4 D+0/D+12/D+30). El ~D+5 observado es D+4 + jitter de la ventana de cron. Resolución: migración 13 reescribe `sequences.steps` a D+0/D+14/D+28 (Lección 39).

2. **Pool de contactos sospechosamente pequeño.** 12 envíos productivos en 5 días, pero parte de esos 12 son toques múltiples a los mismos contactos (Jaime ha recibido ya 2 y tiene un 3º en cola). Esto sugiere que el universo de empresas que han pasado todos los filtros (`ia_fit='fit'` + `research_done_at` + email verificado + sin opt-out) es minúsculo, y `replenish` está machacando a los mismos contactos en lugar de avanzar.

**Regla resultante:**

- Antes de cualquier nuevo batch de drafts y antes del switch a autónomo, hay que auditar con queries SQL el pool real de contactos elegibles vírgenes (sin mensajes previos). Distribución por tier obligatoria. Implementado en `apps/workers/scripts/audit_pool_contacts.py` (script nuevo de la sesión).
- Si el pool elegible es <100 contactos vírgenes: expandir a T2 y T1 antes de generar más drafts; o relanzar `research_prospect.py` / `find_contacts.py` sobre subsets que no los tengan.
- `replenish` debe verificar explícitamente que NO reescribe a contactos con mensajes previos en `('sent','scheduled','drafted','approved')`. Auditado en `auto_replenish.count_contacts_without_draft` (filtro `NOT EXISTS messages` ya está en sitio — verificado contra `apps/workers/pipeline/auto_replenish.py:113-116` en sesión 2026-05-25, NO es un bug, el filtro es correcto). El cross-check `auditoria==replenish` se ejecuta en `audit_pool_contacts.py --env prod`.
- Pool mínimo para activar modo autónomo: ≥100 contactos vírgenes elegibles. Documentado en `tasks/todo.md` §10.4 nueva (sesión 2026-05-25).

**Por qué importa:** un sistema autónomo con cadencia agresiva sobre un pool minúsculo es la receta para quemar el dominio en semanas. Si machacas a los mismos 5 contactos cada 5 días, alguno marca spam y se cae la deliverability del dominio entero.

**Aplicado en (sesión 2026-05-25):**

- `apps/workers/scripts/audit_pool_contacts.py` — script SQL de auditoría con breakdown por tier + cross-check contra `auto_replenish` + veredicto de threshold + conteo de messages por status.
- Migración 13 (descrita en Lección 39): la cadencia agresiva D+0/D+4/D+10 se reescribe a D+0/D+14/D+28.
- `tasks/todo.md` §10.4 nueva: "Condiciones para activar modo autónomo" incluyendo "pool ≥100 contactos vírgenes elegibles" como condición.
- Auditoría humana del replenish: filtros `NOT EXISTS messages` en `apps/workers/pipeline/auto_replenish.py:113-116` verificados correctos en sesión.

---

## 2026-05-25 — Lección 42: el prompt de closing no puede tener tono pasivo-agresivo ni ultimátum

**Contexto:** el draft step 2 (closing) generado para Jaime Nozaleda (Lena Construcciones) tenía asunto "Último correo de mi parte" y cerraba con "¿Es algo que podría tener sentido más adelante o lo descartamos definitivamente?". Esto es pasivo-agresivo: fuerza al destinatario a decir "no" para quitarse el correo de encima en lugar de dejar la puerta abierta de forma honesta. Además contradice el principio de DEMIN de "trato cercano y flexible" (valor n.º 5 del dossier).

**Corrección PM:** un closing nunca puede ser un ultimátum. Su función es cerrar el hilo dejando la puerta abierta para el futuro, no presionar para una respuesta inmediata. La asimetría psicológica del "quítame o di que no" quema reputación con un coste de oportunidad enorme (las personas cambian de empresa, los proyectos cambian — Lección 1).

**Tensión resuelta:** la v1 del prompt de closing (`generate_email_closing.md`, Sprint 4 paso 5) consideraba la pregunta sí/no estructural — "alimenta el clasificador §11". En sesión 2026-05-25 se evalúan tres opciones (mantener dicotomía suavizada / pregunta abierta no binaria / eliminar pregunta). El PM elige el comportamiento más respetuoso de la marca: **pregunta abierta sin binario forzado**. El clasificador §11 sigue recibiendo señal sobre las respuestas que SÍ lleguen; los silencios post-closing van por defecto a `no_ahora` → re_engage +60d (Lección 1), igual que antes. La señal estructural se mueve del prompt al comportamiento downstream (silencio = no_ahora, no `no_interesado`).

**Regla resultante para `generate_email_closing.md` (y por analogía para los `re_engage`):**

- **Asunto:** PROHIBIDO "Último correo", "Última oportunidad", "Me rindo", "Cierro contacto" en tono de queja, o cualquier variante de despedida con presión. Asunto neutro tipo "Quedo a vuestra disposición", "Por si os encaja más adelante" o similar.
- **Tono del cuerpo:** honesto y abierto. La idea es "si no es el momento, lo entiendo; quedo a disposición cuando os venga bien".
- **Prohibido en el cuerpo:** preguntas binarias que fuercen al "no" ("¿lo descartamos?", "¿paso página?", "¿zanjamos el tema?"); frases que cuenten el número de correos previos en tono de queja ("es la tercera vez que escribo", "ya van dos correos sin respuesta"); cualquier insinuación de molestia.
- **Deseable en el cuerpo:** agradecer brevemente el tiempo, dejar abierto que pueden escribir cuando coordinen demolición, mencionar que es la última vez que escribimos por ahora (sin tono de queja).

**Aplicado en (sesión 2026-05-25):**

- `apps/workers/shared/prompts/generate_email_closing.md` v2: secciones PROHIBIDO + reescritura del OBJETIVO DEL CORREO + reescritura de ADAPTACIÓN POR EMAIL_TYPE con patrones honestos sin "una última vez" en tono de queja.
- `apps/workers/tests/test_prompts_generate_email.py`: `test_closing_forces_yes_no_categorization` reemplazado por `test_closing_invites_without_forced_dichotomy` + `test_closing_forbids_aggressive_subject` (ambos verifican que la versión v2 prohíbe explícitamente los patrones pasivo-agresivos).

---

## 2026-05-25 — Lección 43: crear una migration NO es aplicarla; el commit con la migration es marker, no garantía de estado prod

**Contexto:** sesión `/goal` 2026-05-25, Bloque -1. Detecté que las "Lecciones 5-9" que el prompt pedía añadir ya estaban en el archivo como 38-42 (sesión previa del mismo día las añadió). Pero al ir a ejecutar el resto del goal, descubrí que la migración 13 (cadencia D+14/D+28, parte del commit 251cf31 etiquetado como cierre de los cambios de producto) estaba commiteada en el repo pero **NO aplicada a prod**. Migración 12 (mailboxes.hitl_mode default true, parte de cierre Sprint 6 fcad523) tampoco aplicada. Auditoría de `_migrations`: prod tenía solo 1-11.

Síntoma operativo: la BD prod seguía con `sequences.steps = [D+0/D+4/D+10]` aunque el commit 251cf31 decía "feat(product): ajustes post-12-envios -- saludo neutro + cadencia D+14/D+28 + sender-leak guard + closing sin ultimatum". Lección 39 también afirmaba "Aplicado en: migración 20260525120000_13_seq_demin_v1_cadence_d14_d28.sql". Ambos commit y lección decían "aplicado" sin que la migración hubiese pasado por `apply_migrations.py --env prod`.

Adicional: cuando re-corrí `apply_migrations.py --env prod`, la migración 13 falló con `column "updated_at" of relation "sequences" does not exist` — bug en la migración (el author asumió una columna inexistente). Si la migración se hubiera aplicado en la misma sesión que la creó, este bug se habría detectado en el momento, no días después en otra sesión.

**Corrección humana:** PM autorizó aplicar migraciones 12+13 en esta sesión, fix de migración 13 (quitar referencia a `updated_at`), re-aplicación con éxito, y captura de esta lección.

**Regla resultante:**

- **"Crear una migration" y "aplicar una migration" son dos acciones distintas.** El primer commit debe incluir EXPLÍCITAMENTE el output de `apply_migrations.py --env prod` (y dev si aplica) en el commit message o en una entrada §19 del plan, citando el OK de cada migración aplicada. Si solo se crea el archivo `.sql` sin aplicar, el commit message NO puede decir "aplicado" — debe decir "creado, pendiente aplicar en prod".
- **Verificación automática:** al cerrar cualquier feature que dependa de schema changes, hacer un check final SQL contra prod (`select * from _migrations order by applied_at desc limit 5`) y confirmar que las migrations esperadas aparecen. Sin ese check, "lección aplicada" es una afirmación no verificada.
- **Migrations deben probarse al menos contra dev antes de marcar como hecho.** Si dev está offline (caso de hoy con `demin-dev` decomisado), probar contra el schema en local con `psql -f migration.sql` apuntando a un BD throwaway. Crear una migration que falle en prod desperdicia el slot de número + obliga a editarla retroactivamente, lo cual es feo y rompe la inmutabilidad de migraciones aplicadas.
- **El plan §19 debe registrar explícitamente "migración N aplicada a {dev|prod}" como entrada propia**, no envuelta en bullet de feature genérico. Auditoría futura debe poder responder "¿migración X está en prod?" desde §19 sin tener que abrir BD.

**Aplicable más allá de DEMIN:** cualquier proyecto con migraciones SQL versionadas (Flyway, Alembic, Knex, Prisma, etc.). El antipattern es universal: el repo cree que ya aplicó algo porque el archivo existe; la realidad operativa va por separado.

**Aplicado en:**
- Migraciones 12 + 13 aplicadas a prod en esta sesión via `scripts/apply_migrations.py --env prod`.
- Migración 13 editada: quitada referencia a `sequences.updated_at` (columna inexistente). Nota inline en la propia migración explicando el fix retroactivo.
- Migración 14 (`message_revisions`, Bloque 7) creada Y aplicada en la misma sesión, validada con `\d message_revisions` post-apply.
- Esta lección.

**Trigger de aplicación inmediata:** próxima migración (cualquier numero >14). Antes de commitear el archivo `.sql`, aplicar con `apply_migrations.py --env prod` (con confirmación interactiva `yes`) o `dev` según corresponda. Incluir el output del apply en el commit message. Si la aplicación falla, fix de la migración antes de commitear nada.

---

## 2026-05-25 — Lección 44: cancelar y regenerar son operaciones semánticamente distintas — la cola de cadencia no debe confundirlas en el filtro NOT EXISTS

**Contexto:** sesión `/goal` 2026-05-25, Bloque 5.2. Tenía que cancelar 7 reframes que se generaron con cadencia agresiva D+4 (pre-migración 13), con la expectativa explícita del PM en el prompt: "Se regenerarán automáticamente cuando follow_ups detecte el step 0 sent con la nueva cadencia [D+14]". Al revisar `follow_ups.fetch_followup_candidates`, el SQL hacía `NOT EXISTS (SELECT 1 FROM messages WHERE step_index = :next_step)` — sin filtrar por status. Eso significa: un draft cancelado al step N bloquea regeneración futura al mismo step N exactamente igual que un draft enviado. La intuición del PM ("cancelar libera el slot para regenerar") chocaba con el comportamiento real ("cancelar petrifica el slot para siempre").

**Corrección autónoma (esta sesión, con autoridad delegada del goal):** modifiqué el SQL para excluir status='cancelled' del check. Drafts cancelados ya no cuentan como "ya intentado este step" — un follow_ups posterior los re-evalúa y regenera con prompts actuales y cadencia actual.

**Regla resultante:**

- **Diseñar filtros idempotentes ("evita duplicar trabajo") con conciencia de los estados terminales válidos.** Para una entidad como `messages.status` con 7 valores (`drafted`, `approved`, `queued`, `sending`, `sent`, `cancelled`, `scheduled`), el filtro "ya hay uno aquí" rara vez es "cualquier status existe" — es más bien "hay uno en alguno de los estados activos". `cancelled` es un estado de cierre, NO de actividad — debe excluirse de las queries que buscan "qué falta hacer".
- **Convención sugerida para futuros workers que iteren entidades con flag de status:** definir una constante `ACTIVE_STATUSES` en el módulo (ej. `{'drafted', 'approved', 'queued', 'sending', 'sent', 'scheduled'}`) y usarla en todos los filtros idempotentes. No hardcodear "status <> 'cancelled'" en cada query — más limpio y central.
- **Cancelar es un opt-out reversible del slot, no del contact.** Si quieres cancelar Y no regenerar, debes hacer dos acciones: cancelar el message + algún flag al contact (is_optout, is_primary=false, cooling event). Cancelar el draft solo NO debe bloquear futuras intentonas — eso es opt-out implícito y confuso.
- **Lección hermana de 28 y 29.** Lección 28 dijo "cruzar TODAS las decisiones del plan con los filtros del worker". Lección 29 dijo "ordenar dimensiones cualitativas antes que cuantitativas en sort_key". Lección 44 es "distinguir estados activos de estados terminales en filtros de duplicación" — el patrón común: el SQL de iteración requiere reflexión sobre qué dimensiones cuentan para "ya hecho", "no aplicable", "actividad".

**Aplicable más allá de DEMIN:** cualquier sistema con cola de trabajo iterado y status de entidades con cierre — queue de jobs, tickets de soporte (open vs resolved vs cancelled), pull requests (open vs merged vs closed), tareas de cualquier tipo.

**Aplicado en:**
- `apps/workers/outreach/follow_ups.py` `fetch_followup_candidates`: filtro NOT EXISTS de m_next amplía con `AND m_next.status <> 'cancelled'`.
- `apps/workers/tests/test_follow_ups.py`: guard `test_followup_sql_excludes_cancelled_from_next_step_check` que ancla el cambio contra regresión por inspeccion del source.
- Script `scripts/cancel_drafts_2026_05_25.py`: cancela los 7 reframes Y enfría Jaime con `is_primary=false` + evento contact_cooling — combinando cancelación de slot con desactivación del contact (separadas) según la regla.
- Esta lección.

**Trigger de aplicación inmediata:** próxima vez que diseñe o revise un filtro idempotente sobre entidades con status. Antes de commitear el SQL, listar explícitamente los status terminales (cancelled, archived, deleted, rejected, expired, etc.) y verificar que el filtro los excluye apropiadamente. Misma regla aplica a fetch_pending_contacts (generate_draft) — verificar si ya tiene este patrón o si requiere extensión similar.

---

## 2026-05-26 — Lección 45: el bot no responde dentro de hilos abiertos por el prospecto

**Contexto:** tras ver primeras respuestas inbound a los 20 envíos productivos del 26-may, PM decidió que cualquier respuesta del prospecto la contesta Gonzalo a mano. El bot NUNCA escribe dentro de un hilo abierto, ni siquiera con aprobación humana. Esto modifica el plan `todo.md` §11.2 que prevéa "draft de respuesta sugerida" para `interesado` y `pide_info`.

**Distinción clave — dos cosas distintas:**

1. **Respuesta dentro de hilo abierto** = bot contesta a un correo que el prospecto le ha enviado. **PROHIBIDO en cualquier forma.** Esto incluye el acuse automático de opt-out que el plan original prevéa. Gonzalo decide si acusa o no, a mano.

2. **Follow-up programado** = correo NUEVO en frio con otro ángulo, planificado por la secuencia o por el re-engage. **Sigue siendo automático.** No es "responder", es continuar la secuencia de prospección.

**Matriz de acciones actualizada por categoría de respuesta:**

| Categoría | Bot escribe dentro del hilo | Bot programa correo nuevo futuro | Notificar a Gonzalo |
|---|---|---|---|
| `interesado` | NO | NO | Sí, flag urgente en /inbox |
| `pide_info` | NO | NO | Sí, flag urgente en /inbox |
| `no_ahora` | NO | Sí, `re_engage_40` a +40d | No |
| `no_interesado` | NO | Sí, `re_engage_90` a +90d | No |
| `rebote` | NO | NO (marca email inválido) | No |
| `fuera_oficina` | NO | Reprograma siguiente toque del plan | No |
| Opt-out explícito | NO (ni acuse) | NO (exclusión permanente) | Sí, log silencioso |

**Aplicado en:** sesión Code post-26may, Bloque C.

---

## 2026-05-26 — Lección 46: re-engage `no_ahora` cambia de +60d a +40d

**Contexto:** revisión de la cadencia operativa tras observar primeras respuestas. PM decidió acortar la ventana de re-engage para `no_ahora` de +60 días (Lección 1) a +40 días. La lógica: "no es el momento" rara vez significa "vuelve en 2 meses"; con frecuencia significa "esta semana mal, próximo mes mejor". +40d cae a las ~6 semanas, suficiente para que el contexto del prospecto cambie sin parecer insistente.

**Esto sustituye explícitamente el +60d de Lección 1.** El `no_interesado` se mantiene en +90d, sin cambio.

**Implementación:**

- Añadir nuevo ángulo `re_engage_40` a la lógica de `handle_actions.py`.
- El prompt `generate_email_re_engage_40.md` se crea como variante del `re_engage_60` existente, con redacción adaptada al timing más corto ("han pasado unas semanas y" en lugar de "ha pasado un trimestre").
- Migrar cualquier `messages` con `angle='re_engage_60'` ya programado: si `scheduled_for` está todavía en el futuro, recalcular como `original_reply_at + 40d` y cambiar `angle` a `re_engage_40`. Si ya se envió, no tocar.

**Aplicado en:** sesión Code post-26may, Bloque C.

---

## 2026-05-26 — Lección 47: OAuth re-autorización Gmail con PM como mensajero — patrón Flow manual (sin local-server, sin OOB)

**Contexto:** B7 (Lección 36) llevaba bloqueado desde 2026-05-14 (~12 días). Causa raíz operativa: el script original `gmail_oauth_setup.py` usa `InstalledAppFlow.run_local_server`, que abre browser local y levanta server HTTP en localhost — útil cuando ejecutor y autorizador son la MISMA persona, inservible cuando Code está en una máquina (CI / dev local del PM) y Gonzalo (el dueño real del buzón) está en otra. Google también deprecó OOB (`urn:ietf:wg:oauth:2.0:oob`) en 2022, así que no hay flow Google-canónico para autorización sin redirect web.

La salida limpia: usar `Flow` (no `InstalledAppFlow`) con `redirect_uri="http://localhost:<port>"` (Desktop OAuth solo acepta localhost/127.0.0.1, no IPs públicas), generar URL manualmente, dársela a Gonzalo. Gonzalo autoriza → su browser intenta redirect a localhost:8765 → muestra "no se puede conectar" pero la URL en la barra contiene `?code=...&scope=...&state=...`. PM copia esa URL y se la pasa a Code. Code intercambia y persiste.

**Sesión 2026-05-26 ejecutada:** Code+PM+Gonzalo cerraron B7 en una vuelta (~20 min wall clock, 2 ciclos URL+code porque el primer code se quemó por bug del script — usaba `oauth2.googleapis.com/userinfo` para validar email, endpoint que requiere scopes `openid email profile` NO pedidos. Reemplazado por `gmail.googleapis.com/gmail/v1/users/me/profile` que SÍ está cubierto por `gmail.modify`). Script `scripts/oauth_reauth_manual.py` queda en repo como herramienta reusable.

**Regla resultante (patrón meta para futuras OAuth re-autorizaciones donde Code y dueño-del-recurso son personas distintas):**

- **NO usar `InstalledAppFlow.run_local_server`** cuando el dueño del recurso no está en la misma máquina que el script. Usar `Flow.from_client_secrets_file` directo con `redirect_uri` localhost + puerto fijo.
- **Persistir PKCE `code_verifier`** entre generate y exchange — son invocaciones de script distintas, el verifier debe matchear o Google rechaza el code (challenge mismatch). Fichero local gitignored.
- **Validar identidad del autorizador con un endpoint cubierto por el scope solicitado**, no con `oauth2/userinfo` por defecto. Para Gmail: `gmail/v1/users/me/profile`. Para Drive: `drive/v3/about?fields=user`. Para Calendar: `calendar/v3/users/me/calendarList?maxResults=1`. Cualquier endpoint que devuelva email + falle 401 si scope no es el correcto cumple — y evita pedir scopes extra solo para validar.
- **Guardar el refresh_token en `.tmp` ANTES de validaciones posteriores**. Si una validación cosmética falla (email no coincide, scope falta, etc.), el code ya se quemó (Google los invalida tras 1 uso). Guardar primero evita perder el token y obligar al humano a re-autorizar (10+ min extra). Si todas las validaciones pasan, mover `.tmp` → fichero final. Si falla validación crítica (scope insuficiente, email equivocado), borrar `.tmp` y dejar el state limpio.
- **Trabajo de mensajero del PM**: pasar URL completa de la barra del navegador (no solo el code) cuando es posible — permite validación adicional del `state`, `scope`, `iss` antes de procesar el code. Si solo viene code pelado, también funciona pero pierdes una capa de validación gratis.

**Por qué importa:** OAuth re-autorizaciones son operacionalmente caras (coordinar 3 personas + ventana ciega de envío + riesgo de equivocarse de cuenta). El patrón anterior obligaba a uno de dos malos caminos: (a) PM tiene la contraseña de Gonzalo y autoriza por él (legal/imagen problemático), o (b) Gonzalo clona el repo y ejecuta uv en su máquina (overhead técnico que no es razonable). El patrón Flow manual elimina ambos.

**Aplicado en:**
- `apps/workers/scripts/oauth_reauth_manual.py` — nuevo, sustituye uso de `gmail_oauth_setup.py` para escenarios remotos. El original se mantiene para flows local-only (dev rápido del PM en su máquina sin Gonzalo presente).
- `.gitignore` extendido con `.oauth_pkce_verifier.txt`.
- Sesión 2026-05-26: B7 cerrado. mailbox `gonzalo.perez@demingroupmadrid.com` tiene refresh_token con scope `gmail.modify` (verificado via `users.getProfile` + run real de `poll_imap` end-to-end con 50 mensajes procesados + 0 matched + exit 0).

**Trigger inmediato:** próxima vez que cualquier worker requiera scope OAuth ampliado (ej. Postmaster Tools, Calendar para agendar llamadas, Drive para adjuntos), reusar `oauth_reauth_manual.py` con scope diferente. La estructura del script (`--step generate / exchange --auth-url`) es genérica.

---

## 2026-05-26 — Lección 48: PM acepta el riesgo de refresh_token OAuth en plaintext

**Contexto:** durante la re-autorización OAuth gmail.modify del 26-may (Lección 47), `seed_oauth_token` falló al cifrar con Vault por UniqueViolation (el secret `oauth_refresh_token_gonzalo.perez@demingroupmadrid.com` ya existía de un intento previo de hace 2 semanas — Lección 31). Cayó al fallback PLAINTEXT: el refresh_token actual con scope `gmail.modify` está guardado sin cifrar en `mailboxes.oauth_refresh_token_encrypted`.

**Decisión PM (Alberto):** aceptar el riesgo de no cifrar y NO ejecutar la limpieza (`DELETE FROM vault.secrets WHERE name='oauth_refresh_token_...' + re-correr seed`).

**Riesgo asumido:** el refresh_token da acceso completo (lectura, escritura, modificación y eliminación de emails) sobre la cuenta `gonzalo.perez@demingroupmadrid.com`. Vectores de exposición a los que PM está expuesto al elegir no cifrar:

- Filtración de credenciales `service_role` de Supabase (Code, workers VPS, env vars Vercel).
- Dumps o exports de BD que terminen en logs, chats, repos o backups.
- Compromiso del VPS Hetzner donde corre `seed_oauth_token`.
- Copia-pega de SELECT en logs o screenshots.
- Futuras sesiones de Code o humanos haciendo SELECT y mostrando el valor.

RLS de Supabase protege contra acceso vía API pública pero NO contra ninguno de los vectores anteriores.

**Mitigación recomendada (no aplicada):** cifrar con Vault usando 5 min de trabajo en próxima sesión eliminaría ~95% de los vectores.

**Si en el futuro ocurre incidente relacionado con la cuenta de Gmail de Gonzalo:** este registro existe para post-mortem.

**Aplicado en:** sin acción. Decisión PM cerrada el 2026-05-26.

---

## 2026-05-26 — Lección 49: Opción C heurística (slug+TLD+MX+SMTP probe) NO es viable para PYME ES sin web

**Contexto:** sesión 2026-05-26 implementó pipeline completo Opción C T4 (`pipeline/option_c_t4.py` + 4 sub-módulos) para procesar 288 empresas T4 fit sin web declarada — último gran bloque de pool sin tocar tras agotar Hunter retry T1+T2 en mismo día (0 contactos nuevos sobre 102 empresas, confirma L22). Smoke (5) + batch real (30) = 35 empresas procesadas con:

- Dominio inferido: 9/35 (25.7%) tras quitar variante "primera palabra" que producía falsos positivos peligrosos (constructora.es matchea para múltiples empresas distintas).
- SMTP probe verificado: **0/9 dominios** dieron 250 OK al RCPT TO.
- Hit rate end-to-end: **0%**.

Las empresas T4 sin web SÍ tienen dominio comercial activo (1/4 al menos), pero los providers (Gmail Workspace, Microsoft 365, GoDaddy) están bloqueando SMTP probing al RCPT TO en 2026. Patrón: aceptan EHLO/MAIL FROM, luego o cierran sin respuesta, o responden 5xx generic, o son catch-all (la detección está pero salta la mayoría a "no concluyente"). El probe pasivo sin DATA que en 2020-2022 daba ~50% hit rate hoy da ~0%.

**Decisión PM:** parar el procesamiento de las 258 T4 restantes. Coste evitado: ~22 min + ~$1.50 LLM por información que ya tenemos (hit rate 0% statistically significativo). Las 25 empresas procesadas en el batch real quedaron como `tier='descartado'` con `research_data._descartado_reason='no_domain_inferred'` cuando no se infirió dominio, o con `research_data._smtp_status='no_match'` cuando había dominio pero SMTP no validó.

**Regla resultante:**

- **Antes de comprometer pipeline completo con SMTP probe agresivo en 2026**, hacer smoke de 10-30 sample SOLO de los pasos críticos (en este caso: solo SMTP probe sobre dominios conocidos válidos). Si hit rate sobre dominios reales y verificados es <5%, abortar pipeline antes de invertir tiempo en infer_domain + research IA. El cuello de botella suele ser el SMTP, no los pasos previos.
- **Para sectores donde Hunter ya falla (cobertura saturada L22)**, NO existe una "opción C heurística + SMTP probe" viable en 2026. Los caminos reales para subir el pool son:
  - Phantombuster LinkedIn (L25 — ~$60/mes, hit rate típico 60-80% en M&A según experiencia industrial).
  - Servicios comerciales especializados con APIs de validación email (MillionVerifier ~$0.0008/probe, etc.) — externalizar la validación, no hacerla in-house.
  - Empresite/Einforma scraping (L26 — mini-experimento pendiente, fuente complementaria pero requiere RGPD + TOS análisis).
  - Nuevo dump SABI con CNAEs/geografías adyacentes (palanca C en §20).
- **Documentar palancas activadas Y descartadas** con datos reales para que futuras sesiones no re-intenten el mismo error con la esperanza de que funcione "esta vez". Lección 49 cierra Opción C heurística in-house como vía descartada empíricamente para PYME construcción ES en 2026.

**Aplicado en:**
- Código `pipeline/option_c_t4.py` + 4 sub-módulos commiteados igualmente (curva de aprendizaje + dejan infra reusable si en futuro un sector distinto se procesa donde SMTP sea más permisivo).
- 35 empresas T4 procesadas en BD prod: 25 a `tier='descartado'`, 10 con `research_data._smtp_status='no_match'` + dominio inferido + research IA.
- Decisión documentada en §19 todo.md entrada 2026-05-26.
- `tasks/todo.md` §20 nueva palancas A/B/C/D con esta como D (activada, fallida documentada).

**Trigger inmediato:** cuando el pool actual (9 vírgenes hoy) baje a 0 sin más material disponible, PM evalúa Palancas A (LinkedIn) o B (clasificar pendientes Sabi) como next step. Lección 49 ahorra el tiempo de reintentar Opción C.

---

## 2026-05-26 — Lección 50: PM acepta switch automático a autónomo con threshold pool ≥50 + 4 safeguards

**Contexto:** prompt /goal v4 del 25-may estipulaba Bloque 6 (switch a autónomo) con activación manual por PM cuando 7 condiciones se cumplieran. Sesión 2026-05-26 cambió a activación AUTOMÁTICA con safeguards. Cambio adicional: pool threshold de 100 → 50.

**Decisión PM (Alberto, 2026-05-26):**

- Threshold pool vírgenes elegibles: **≥50** (no ≥100 del prompt original).
  - Justificación: 50 vírgenes + cadencia D+14/D+28 + cap 20/día = ~10 días de operación autónoma sin intervención. Suficiente para validar el modo antes de escalar.
  - Threshold 100 queda como objetivo aspiracional para fase de escalado posterior (cuando Phantombuster + nuevos dumps Sabi sumen pool).
- Switch a autónomo se activa **automáticamente** sin requerir confirmación manual PM, condicionado a las 7 condiciones del Bloque 6 (con L50 aplicada a Cond 5) Y a 4 safeguards obligatorios.

**Los 4 safeguards (no opcionales):**

1. **Email previo 24h** a `albertobueno10@gmail.com` Y `gonzalo.perez@demingroupmadrid.com` cuando el worker detecte 7/7 condiciones verdes y vaya a hacer switch. Asunto "[DEMIN] Switch a autonomo programado para [fecha+24h]". Cuerpo HTML con tabla de las 7 condiciones + link directo a `/settings` para cancelar.
2. **Toggle `auto_switch_enabled` en `/settings`** (default ON, decisión PM). PM puede desactivar en cualquier momento desde dashboard. Si OFF: worker solo evalúa y notifica "cumplidas, activa manualmente" sin programar switch.
3. **Cap inicial 20/día al activarse**. Sin escalado automático. PM decide subir cap manualmente con cuidado.
4. **Botón rollback de emergencia "Volver a HITL ahora" en `/settings`**, visible, accesible desde móvil, con `variant="destructive"` y tamaño `lg`. Acción inmediata sin doble-confirm (es rollback, no flip nuevo — confianza en que si lo pulsas es porque algo está mal).

**Por qué cambio de manual a automático con safeguards:**
- Reduce dependencia de PM disponible para flipar switch cuando llegue el momento.
- Email 24h da ventana para cancelar si PM/Gonzalo detectan algo raro (toggle off, cancel schedule, o ignorar el email tras revisar /settings).
- Worker corre cada 6h → 4 disparos por día → si una condición se rompe entre el schedule y la ejecución, el worker la cancela y notifica.
- El toggle `auto_switch_enabled` es el opt-out per-mailbox: si PM no se siente cómodo lo apaga y vuelve al flujo manual del prompt v4 sin perder ninguna garantía.

**Por qué hardcoded `lemwarm_pausado=true` en Cond 7:**
- No verificable desde Code (PM ejecuta pausa manualmente en panel Lemwarm — L38).
- Asumimos true para que no bloquee operativamente. Si PM no pausó realmente, la condición no se cumple pero el worker no lo detecta y dispararía igual. Es deuda consciente — alternativa sería una columna `lemwarm_paused_at` en mailboxes que PM marca manualmente en /settings. Por simplicidad no se implementa en v1.

**Aplicado en:**
- Migration `16_auto_switch_autonomous.sql`: añade `mailboxes.auto_switch_enabled` + `mailboxes.scheduled_autonomous_switch_at`. Default ON.
- `apps/workers/monitoring/auto_switch_to_autonomous.py`: worker 6h. 4 casos (autonomo ya, toggle off, schedule con rota, schedule alcanzado, no schedule + todas verdes).
- `apps/workers/shared/notifications.py`: helper Resend HTTP API best-effort (L8 — sin RESEND_API_KEY → warning + skip, sin abortar).
- `/settings` UI: nueva Card "Auto-switch a autónomo (Bloque 6 — L50)" con toggle + scheduled state + rollback emergency + tabla 7 condiciones evaluadas server-side.
- Server actions: `toggleAutoSwitchEnabledAction`, `cancelScheduledSwitchAction`. Paper trail en events.
- systemd: `demin-auto-switch.service` + `.timer` cada 6h. Pendiente despliegue VPS.

**Trigger inmediato:** próxima sesión Code o PM despliegan systemd unit al VPS Hetzner: `scp infra/systemd/demin-auto-switch.{service,timer} demin@vps:/etc/systemd/system/ + sudo systemctl daemon-reload + sudo systemctl enable --now demin-auto-switch.timer`. Sin esto, el worker no corre en background; solo se puede invocar manualmente.

**Mitigación pendiente para Cond 7 Lemwarm:** si en futuro queremos auditar realmente que PM pausó Lemwarm, añadir columna `mailboxes.external_warmup_paused_at` y toggle en /settings que PM marca tras pausar en panel Lemwarm. Tarea de mejora, no bloqueante.

---

## 2026-05-27 — Lecciones 51-53: anuladas

Los números L51, L52 y L53 quedaron sin uso. Estaban reservados para la sesión de despliegue del worker auto_switch al VPS (Sesión 1 del 2026-05-27), que fue CANCELADA por decisión PM tras evaluar coste/beneficio (ver entrada en §19 de todo.md: el worker solo automatiza el toggle hitl_mode, y pulsar el botón manual en /settings es trivial). El código del worker + UI + safeguards permanece en el repo, re-desplegable en el futuro. La numeración continúa en L54.

---

## 2026-05-27 — Lección 54: tres bugs encadenados en poll_imap producían 0% reply rate aunque hubiera respuestas reales en bandeja

> **Nota numeración:** lecciones 51-53 quedaron anuladas — ver entrada "Lecciones 51-53: anuladas" arriba. La numeración salta de L50 a L54.

**Contexto:** tras desbloqueo OAuth B7 (L47 26-may), dashboard `/metrics` seguía mostrando REPLY RATE 0.00% pese a 4 respuestas reales en la bandeja de Gonzalo (Cabbsa, Cador, Umavial, Oliveros). PM detectó que olía mal y pidió diagnóstico. Hipótesis inicial: `poll_imap` filtra por `is:unread` y Gonzalo marca leído al abrir → race condition. Esa hipótesis resultó parcial — había **3 bugs encadenados**, cualquiera bastaba por sí solo:

1. **Bug B (matching demasiado estricto, el más grave).** `find_matching_message_by_rfc_id` estaba stubbed devolviendo `None` siempre porque `messages.rfc_message_id` no existía en schema. El fallback subject+from exigía `contact.email == reply.from` exacto, pero los 4 casos reales eran forwards internos (administracion@umavial.es → amartin@umavial.es, info@grupooliveros.com → juanvalle@grupooliveros.com) o variantes TLD (.com vs .es para Cabbsa). 0/4 matcheaban.
2. **Bug A (is:unread + race humana).** Worker corre cada 5 min; Gonzalo abre los emails como humano y se marcan leídos → el siguiente run no los ve. Para Umavial/Oliveros, recibidos ANTES del desbloqueo OAuth, esto era 100% determinista: nunca se vieron.
3. **Bug C (cap max_results=50 sin paginación).** Bandeja tenía 57+ unread totales → 7+ quedaban fuera de cada poll. No fue el bug bloqueante, pero hubo que subirlo a 500 para el backfill.

**Corrección humana / decisión PM:**
- P0a: persistir RFC Message-ID en `messages.rfc_message_id` (migration 17 + cambios en `gmail_adapter.SendResult` + `send_gmail.persist_send_success`). Matcher primario en cascada.
- P0b: query default `newer_than:7d` sin `is:unread`. Dedup por `replies.gmail_message_id UNIQUE`. **El bot ya NO marca leídos en Gmail** — Gonzalo conserva la señal humana "qué he visto y qué no".
- P1a: fallback adicional por `(dominio del From, subject strippeado, 60d)` cuando email exacto no matchea. Log explícito `matched_by=domain_fallback` para auditoría.
- P1b: añadir prefijos `RV:`/`R:` (reenvío español) a strip iterativo de subject. Antes solo había Re:/Fwd:/Fw:.

**Regla resultante:**
- **Cuando una columna de matching es central, persistirla desde el momento del envío.** No dejar matchers stubbed con comentarios "esto requiere columna nueva" — fixearlo en la misma sesión o documentar como blocker explícito. La columna `messages.rfc_message_id` debería haberse añadido cuando se diseñó el flujo de threading, no 3 semanas después.
- **Los matchers de identidad en respuestas comerciales DEBEN tolerar forwards internos.** Las empresas redirigen emails a la persona competente (info@ → ventas@, administracion@ → comercial@). Exigir `contact.email == reply.from` rompe el matching en mayoría de casos reales. Cascada de 3 niveles (RFC Message-ID → email exacto → dominio + subject) cubre 3/4 de los casos observados.
- **Cualquier `is:unread` que dependa de que el bot marque leídos es un anti-patrón cuando hay humanos lectores en el medio.** Dedup en BD por id estable (gmail_message_id), no por flag de estado en Gmail. Permitir que el humano mantenga su propia señal de lectura.
- **Numeración / regex de "Re:" debe incluir variantes locales.** "RV:" (español), "Sv:" (noruego/sueco), "AW:" (alemán). Para outreach en mercados no anglo, los prefijos en inglés no bastan.

**Aplicado en:**
- `infra/supabase/migrations/20260527113000_17_rfc_message_id_and_replies_dedup.sql`: añade `messages.rfc_message_id` + `replies.gmail_message_id UNIQUE`.
- `apps/workers/shared/gmail_adapter.py`: `SendResult.rfc_message_id` + `_build_raw_message` devuelve tupla `(raw, rfc_id)`.
- `apps/workers/outreach/send_gmail.py`: `_normalize_rfc_id` (strip brackets + lower) + persiste en `messages.rfc_message_id` + lo añade al payload del evento `message_sent`.
- `apps/workers/replies/poll_imap.py`: 3 matchers en cascada, query default `newer_than:7d`, dedup por `gmail_message_id`, eliminado `mark_message_as_read`, skip self-sent emails del mailbox.
- `apps/workers/tests/test_poll_imap_matchers.py`: 23 tests unitarios (strip RV/Re, normalize Message-ID, extract In-Reply-To/References, normalize_rfc_id espejo).

**Resultado del backfill productivo (newer_than:7d max_results=500):**
- 4 respuestas reales en bandeja → **2 entraron a `replies` table automáticamente**:
  - **Umavial** (amartin@umavial.es, "RV: Demoliciones interiores...") → `interesado` ✓. Matched_by=domain_fallback (contact=administracion@umavial.es).
  - **Oliveros** (juanvalle@grupooliveros.com, "RE: Demolición interior...") → `pide_info` ✓. Matched_by=domain_fallback (contact=info@grupooliveros.com).
- **2 no entraron y quedan para gestión manual de Gonzalo**:
  - **Cabbsa** (alvaro.lopez@cabbsa.es): contact existe pero con TLD distinto (`alvaro.lopez@cabbsa.com`). El domain fallback solo matchea dominio exacto, no variantes TLD. Cubrirlo requeriría heurística "misma raíz de marca" no autorizada por PM.
  - **Cador** (ymartinez@grupocador.com): outreach se envió a `jflores@cador.es` (dominio distinto sin relación obvia "grupocador" ↔ "cador"). Reply sin In-Reply-To ni References. Sin matching posible.
- Reply rate `/metrics` rates_7d: **0.00% → 6.67%** (2 replies / 30 sent).

**Mitigación pendiente:** para mensajes nuevos enviados desde 2026-05-27 12:00 UTC el matching primario (RFC Message-ID) cubrirá automáticamente los forwards internos sin depender del domain fallback. Los 30 messages enviados antes del fix tienen `rfc_message_id IS NULL` — sus replies futuros dependerán del domain fallback (limitación conocida; aceptable porque la cohorte es pequeña).

**Trigger próxima sesión:** si PM ve que sigue faltando cobertura tras 1 semana de envíos nuevos, evaluar (a) heurística raíz-de-marca para casos tipo Cabbsa, (b) paginación poll_imap si `listed=500` se alcanza regularmente. P3 matching por `gmail_thread_id` queda como mejora arquitectónica posterior.

---

## 2026-05-27 — Lección 55: PM declinó añadir heurística de matching cross-TLD por riesgo de falsos positivos a baja muestra

**Contexto:** tras aplicar fixes P0+P1 a `poll_imap` (L54), 2 de 4 respuestas históricas no se recuperaron. Cabbsa especialmente: contacto en BD `alvaro.lopez@cabbsa.com`, respuesta llegó de `alvaro.lopez@cabbsa.es`. Mismo nombre, misma raíz de dominio, distinto TLD. Code propuso heurística de "raíz de marca" como mejora opcional.

**Decisión PM:** NO añadir la heurística. Razones:

- 32 envíos productivos solo, base muestral pequeña para evaluar riesgo real de falsos positivos.
- Cabbsa es 1 caso, no patrón.
- Falsos positivos en matching de replies son peores que perder un reply: asocian una respuesta a un mensaje equivocado, corrompiendo señal de aprendizaje y posibles re-engages.
- Gonzalo gestiona Cabbsa manualmente sin coste significativo.

**Reevaluación futura:** si en próximas 2-3 semanas con ≥100 envíos emergen ≥5 casos similares (TLD switch, sub-marca, etc.), se reevaluará la heurística con datos.

**Aplicado en:** ninguno. Decisión PM registrada para auditoría futura.

---

## 2026-05-27 — Lección 56: universo Sabi actual es 100% Madrid — ampliación requiere dump nuevo

**Contexto:** PM planteó ampliar a provincias limitrofes. Query confirmó: 5.578 empresas en `companies` 100% Comunidad de Madrid (5 localidades, todas Madrid; sin campo `provincia`). El Excel Sabi original se filtró por Madrid; otras provincias nunca estuvieron.

**Conclusión:** no se puede "filtrar el Excel por provincias" — no hay otras provincias en él. Ampliar requiere dump nuevo (Palanca C, detallada en §20).

**Decisiones Gonzalo:** radio Madrid+Guadalajara+Toledo+Ávila+Segovia+Cuenca; sin extra desplazamiento; sin cambio plazos; correo mismo tono con geografía neutralizada.

**Pre-requisito:** PM tiene acceso Sabi, extraerá dump cuando pool actual se agote. NO ejecutado ahora (hay colchón tras 191 rescatadas Palanca B).

**Aplicado en:** documentación §20. Ejecución futura.

---

## 2026-06-03 — Lección 57: exclusión de clientes existentes es por contacto, no por empresa — riesgo en modo autónomo

**Contexto:** Inner XXI (cliente real de Gonzalo) tenía su contacto primary marcado opt-out tras rechazo HITL, pero sus contactos secundarios (yolanda@, ruben@) seguían activos. El pipeline hoy no los contacta porque exige is_primary=true y no lo son, pero no hay garantía estructural: no existe flag a nivel empresa de "cliente existente / no contactar".

**Riesgo identificado:** en HITL el riesgo es bajo (Gonzalo revisa cada draft y rechaza a sus clientes). En AUTÓNOMO el riesgo es real: si un proceso promoviera un contacto secundario de un cliente existente a primary, el sistema le enviaría prospección en frío sin revisión humana. Escribir a un cliente actual de Gonzalo en frío es dañino reputacionalmente.

**Decisión PM:** no construir mecanismo de exclusión a nivel empresa ahora. Aceptado para HITL.

**PRE-REQUISITO AÑADIDO PARA EL SWITCH A AUTÓNOMO:** antes de activar modo autónomo, resolver el tema de clientes existentes, bien:
- (a) construyendo flag a nivel empresa `companies.no_contactar` + razón, filtrado en todos los puntos del pipeline, O
- (b) asegurando que la lista completa de clientes actuales de Gonzalo está en opt-out a nivel de TODOS sus contactos (no solo el primary).

**Aplicado en:** documentación. Pendiente de resolver antes de autónomo.

---

## 2026-06-03 — Lección 58: el cuello de las T2 sin contacto era la política D20, no (solo) la cobertura de Hunter — scraping de web propia recupera 71% a coste cero

**Contexto:** 33 de 48 T2 fit (incluidas las 5 mayores, 13-19M€) estaban fuera del pipeline con `ia_fit_reason='no_contactos_encontrados'`. Diagnóstico previo asumía "Hunter no encontró nada". La realidad tiene dos partes: (a) Hunter tiene cobertura pobre de PYME constructora española (8 de 9 dominios reintentados devolvieron 0), y (b) cuando encuentra algo genérico o nominal-sin-cargo, D20 lo rechaza para T2 (`corporativo_pequeno` y A3 no aceptables).

**Sesión de recuperación (números):** scraper de emails visibles en web propia (`pipeline/scrape_emails.py`, antes stub D17): 22 de 31 scrapeadas con email (71%), 25 contacts insertados `email_source='web_scrape'`, $0. Hunter retry dirigido sobre las 9 restantes: 0 directas (9 calls), pero 1 recuperada vía override PM posterior (Brillas Agusti, ver abajo). **Total: 23 de 33 recuperadas.** Drafts: 23/23 OK validados ($0.45). Quedan 10 pendientes (documentadas en §20, decisión PM: no buscar a mano ahora).

**Override D20 (decisión PM 2026-06-03, alcance limitado):** para `web_scrape` en T2 se aceptan buzones corporativos (info@, obras@, administracion@...) — un buzón real publicado en la web propia de una constructora de 15M€ es mejor que excluirla. D20 sigue intacta para el flujo Hunter. La whitelist NEGATIVA (rrhh@, prensa@, noreply@...) se respeta siempre.

**Reglas resultantes:**
- `empresa@empresa.es` (local part == primer label del dominio) es buzón corporativo de marca, NO persona (visto: iycsa@iycsa.es, trauxia@trauxia.es, divegon@divegon.com...). El scraper lo clasifica `corporativo_pequeno`/priority 5.
- Si la web redirige a un dominio registrable distinto (logistikservice.es → logistik.es), el filtro estricto de dominio propio descarta los emails del dominio destino. Conservador a propósito (anti-terceros); esos casos van a manual.
- Emails de la web solo se persisten si aparecen literalmente (L49 sigue: cero permutación/invención).

**Resuelto mismo día (override PM):** Hunter encontró `ragusti@brillasagusti.com` (apellido coincide con razón social BRILLAS AGUSTI) pero D20 lo descartaba (sin nombre/cargo, regla 7). PM aprobó insertarlo: para PYME constructora española, un email con apellido coincidente con la razón social es señal válida de decisor aunque no tenga cargo confirmado. Insertado como `nominal`/priority 4, `email_source='hunter'`, `ia_fit_reason='recuperada_hunter_override_pm'`. Criterio reutilizable en futuros filtrados D20 análogos (siempre con aprobación PM explícita, no automatizar).

**Aplicado en:** `pipeline/scrape_emails.py` (worker real + 7 tests), `scripts/hunter_retry_nocontacts.py`, 25 contacts + 22 drafts en prod, §19 todo.md.

---

## 2026-06-04 — Actualización L48: segunda exposición del refresh_token + medida preventiva

**Contexto:** durante la verificación del flujo de edición HITL (2026-06-03), al inspeccionar la tabla `mailboxes` el refresh_token OAuth se imprimió de nuevo en el output de una sesión Code (segunda exposición tras la de origen en L48).

**Decisión PM:** dejarlo, riesgo bajo (el token solo es utilizable junto al client_id/secret del proyecto GCP, transcripts locales). Consistente con L48 (no cifrar).

**Medida preventiva acordada:** cuando un prompt pida inspeccionar la tabla `mailboxes`, incluir explícitamente "NO imprimas el campo `oauth_refresh_token_encrypted`; selecciona solo las columnas necesarias". Evita acumular más copias del token en transcripts sin coste ni re-autorizar.

**Estado del riesgo:** acumulativo pero bajo. Si en algún momento PM decide higiene máxima, re-autorizar OAuth (5 min, `docs/oauth_reauthorize_gmail.md`) revoca todos los tokens viejos.

**Aplicado en:** nota preventiva para prompts futuros. Sin acción técnica inmediata.

---

## 2026-06-04 — Lección 59: ajuste de prompt — saludo neutro se mantiene + presentación de Gonzalo añadida

**Contexto:** la verificación del flujo HITL (2026-06-03, auditoría de las 46 ediciones en `message_revisions`) reveló que Gonzalo edita casi todos los drafts para añadir "soy Gonzalo, responsable de DEMIN" y cambiar el saludo a "Buenos días".

**Decisión PM:**
- Saludo neutro SE MANTIENE (L5/L39 vigentes), por riesgo de desincronía horaria. Gonzalo edita a mano si quiere en casos concretos.
- Presentación "soy Gonzalo, responsable de DEMIN" SE AÑADE al prompt de opening, integrada naturalmente en el cuerpo sin redundar con la firma (la firma ya cierra con "Gonzalo Pérez / Responsable DEMIN Group" — el cuerpo presenta conversacional, la firma cierra con datos).
- Follow-ups dentro de secuencia (reframe D+14, closing D+28): NO llevan presentación — son continuación y sus prompts ya lo prohíben/desaconsejan. `re_engage_40` (+40d tras `no_ahora`): SÍ lleva recordatorio LIGERO de identidad ("soy Gonzalo, de DEMIN — cruzamos unos correos hace unas semanas") porque a ~6 semanas el prospecto puede no recordar el hilo. No existe prompt `re_engage_90` (es concepto en §11.2, sin archivo); si se crea, heredará el recordatorio ligero.
- Los drafts ya existentes (`drafted`) NO se regeneran — solo los nuevos llevan el cambio.

**Motivo:** reducir el trabajo de edición manual de Gonzalo en los correos futuros (46 de 46 envíos con edición seguían este patrón).

**Aplicado en:** `generate_email_opening.md` (v3) y `generate_email_re_engage_40.md` (v2). `reframe`/`closing` sin cambios (justificado arriba). Sin regeneración de drafts existentes, tabla `messages` intacta.

---

## 2026-06-04 — Lección 60: ventana de backfill debe cubrir desde el primer envío + bounces DSN eran invisibles — y el HITL atrapó el único follow-up erróneo

**Contexto:** el bug de matching de replies (L54, fix 2026-05-27) dejó un periodo ciego. El backfill correctivo usó `newer_than:7d`, pero el envío productivo empezó el 14-may: la respuesta de Carmen (POR OTRA ARQUITECTURA, 19-may, **45 minutos** después del opening) quedó 1 día fuera de la ventana y nunca entró en `replies`. En cascada, `follow_ups.py` (cuyo stop-on-reply en líneas 154-157 depende de `replies`) regeneró un reframe el 02-jun para alguien que ya había contestado.

**(a) Backfill 30d correctivo:** `poll_imap --query "newer_than:30d -subject:lemwarmup" --max-results 500` (el ruido lemwarm saturaba el cap de listado). Resultado: 1 reply nueva (Carmen → `no_ahora`), 6 dedup correctas, 0 duplicados. **Regla: la ventana de un backfill se dimensiona desde el inicio del periodo ciego (primer envío sin matching fiable), no con un valor por defecto.**

**(b) Bounces DSN invisibles (deuda de auto_pause.py:23-24 cerrada):** los DSN (`postmaster@`/`mailer-daemon@`, subject "Undeliverable:...") nunca matcheaban la cascada → `skipped_no_match` → bounce rate de auto_pausa infracontado (Apéndice A regla 6). Fix: rama DSN en `poll_imap` ANTES de la cascada (`is_dsn` + `extract_bounced_recipient` vía Final-Recipient/X-Failed-Recipients/fallback) que inserta la reply con `category='rebote'` preseteada (sin LLM), y la rama rebote de `handle_actions` ahora marca `messages.status='bounced'` + inserta evento `bounce` (joineable por `message_id`, que es lo que cuenta auto_pause). Retroactivo: DECON 86 (a.rompotis@decon.gr) bounced + evento + email_verified=false. 8 tests nuevos, 23 existentes sin regresión.

**(c) Daño real: cero.** El único follow-up erróneo (reframe de Carmen) murió DOS veces antes de salir: PM lo detectó en /approval-queue y Gonzalo ya lo había rechazado vía HITL (categoría `tono`, 04-jun 14:13 UTC) horas antes del fix. 0 de 8 follow-ups enviados fueron a contactos con reply previa. El re_engage_40 de Carmen quedó reprogramado a su respuesta+40d (28-jun), no a now()+40d, porque el retraso de procesamiento era artefacto del bug.

**(d) PRE-REQUISITO REFORZADO PARA AUTÓNOMO:** sin HITL, ese reframe habría salido solo — un correo "por si no viste el primero" a alguien que respondió en 45 minutos. Antes del switch: pipeline de replies+bounces sólido y verificado (poller corriendo, matchers cubriendo bounces, backfill post-outage protocolizado). Se suma a la Condición 8 (clientes existentes, L57) como condición humana previa.

**Ventana default del poller (recomendación, NO aplicada):** mantener `newer_than:7d` — con cadencia de 5 min sobra, y 14d duplicaría llamadas Gmail por run sin beneficio en operación continua. La regla operativa correcta es: tras CUALQUIER parón del poller >3 días, backfill manual con ventana = parón + margen. El riesgo real a vigilar es el timer muerto, no la ventana.

**Aplicado en:** `replies/poll_imap.py` (rama DSN + category preseteada), `replies/handle_actions.py` (mark_message_bounced + evento bounce), `tests/test_poll_imap_dsn.py`, datos prod corregidos (Carmen + DECON 86).

---

## 2026-06-04 — Lección 61: push automático al cerrar tarea

**Contexto:** se acumularon 7 commits en local sin pushear a GitHub durante ~1 semana (27-may a 04-jun) porque el push solo se hacía bajo petición explícita y nadie lo pidió. Riesgo: trabajo viviendo solo en la máquina local (sin copia en remoto) y deploys al VPS bloqueados (el VPS hace pull de GitHub, que estaba desactualizado).

**Decisión PM:** Code debe hacer `git push origin main` automáticamente al cerrar cada tarea con commits, sin esperar petición. Regla añadida a CLAUDE.md. Se eligió instrucción en CLAUDE.md sobre git hook post-commit por ser más controlable (pushea al cerrar tarea, no en commits intermedios ni experimentos; no rompe si se trabaja sin conexión).

**Regla resultante:** push al cierre de tarea por defecto, con excepciones (cambios a medias, push fallido, rama no-main). Confirmar en cada reporte si se pusheó.

**Aplicado en:** CLAUDE.md (Gestión de tareas, regla 7).

---

## 2026-06-10 — Lección 62: la cadencia es data-driven en DÍAS pero no en ÁNGULOS; reordenarla reindexa `step_index` y toca media docena de sitios

**Contexto:** decisión de producto (Alberto/Fernando) de espaciar mucho más los follow-ups a no-respondedores y añadir un tercer follow-up: de D+0/D+14/D+28 (3 toques) a D+0/D+40/D+80/D+120 (4 toques: opening/reframe/`value`/closing). Sobre el papel parecía "solo cambiar `sequences.steps` en BD". No lo era.

**Lo aprendido (patrón técnico reutilizable):**

1. **`follow_ups.py` es data-driven en los DÍAS pero NO en los ÁNGULOS.** Lee `sequences.steps[].day` en runtime (cambiar el ritmo = UPDATE en BD, sin redeploy), pero los `angle` válidos están en una **whitelist hardcodeada** en dos sitios: `Angle = Literal[...]` + la validación de `load_sequence_steps` en `follow_ups.py`, y `Angle = Literal[...]` + `_STEP_BY_ANGLE` + `--angle choices` en `generate_draft.py`. Un ángulo nuevo lanza `RuntimeError` hasta que se amplían. Regla: **antes de añadir un toque nuevo, grep de la lista de ángulos en todo el repo**, no asumas que basta con la BD.

2. **Reordenar la cadencia REINDEXA `step_index`** (aquí `closing` pasó de 2 a 3). El `step_index` está cableado en más sitios de los obvios: `_angle_from_step_index` de `classify_replies.py`, comentarios de schema (`messages.step_index`/`messages.angle`), el array de ángulos del dashboard `metrics/page.tsx`, y varios tests parametrizados. Un grep de `step_index` + `closing` + la lista de ángulos lo destapa todo (lo hizo un subagente de exploración; yo había subestimado la superficie).

3. **Colisión de `step_index` entre cadencia y re_engage.** `handle_actions` asigna `step_index` 3/4 a `re_engage_40`/`re_engage_90`; al mover `closing` a 3 colisiona con `re_engage_40`. Es **inocua** (el dedup de re_engage es por `angle`, y la cadencia se detiene en cualquier reply, así que un contacto nunca recorre ambos caminos), pero la solución correcta es **leer el campo autoritativo `messages.angle` directo en vez de derivar el ángulo del `step_index`** (que es ambiguo). Patrón general: si un dato existe explícito en la tabla, no lo re-derives de un índice posicional.

4. **Cambiar la cadencia afecta el CONTENIDO de los prompts existentes, no solo su orden.** El `reframe` decía "Hace 14 días" y el `closing` "Han pasado 28 días" / "tercer y último" / "el más corto de los tres": todo eso queda factualmente falso al re-espaciar. Dos tests (`test_closing_mentions_d28`, `test_reframe_mentions_d14`) lo cazaron. Regla: al recalibrar cadencia, revisar los prompts por menciones de días y de conteo de toques.

5. **In-flight al ampliar intervalos: seguro por construcción.** Idempotencia `(contact, step_index)` → cero duplicados; ampliar intervalos solo RETRASA el siguiente toque (nunca lo adelanta) → ningún toque inmediato sorpresa. El único riesgo (un FU nuevo a contactos que YA completaron la secuencia vieja) se neutraliza aplicando pronto + `--dry-run` de verificación. **Verificar el estado real antes de tocar** (Paso 0) confirmó que la hipótesis de cadencia era correcta y que hoy 0 contactos habían completado el closing.

**Meta-aprendizaje (workflows de verificación):** los agentes verificadores adversariales del prompt nuevo dieron muchos falsos positivos ("step_index 2 ya es closing", "la cadencia es de 3 toques") porque **no les di el contexto de que el cambio a 4 toques ERA el objetivo** — evaluaron contra el repo actual. Al lanzar verificadores de un cambio, dales explícitamente el estado destino, o filtrarán como "error" justo lo que vas a modificar.

**Regla resultante:** cambiar la cadencia de `demin_v1` = (a) migración `UPDATE sequences.steps`; (b) si hay ángulo nuevo, ampliar whitelist en `follow_ups.py` + `generate_draft.py` + crear el prompt versionado; (c) si reordena, auditar `step_index` en `classify_replies`, comentarios de schema, dashboard y tests; (d) revisar prompts por menciones de días/conteo; (e) verificar in-flight (idempotencia + ampliar-solo-retrasa) y correr `--dry-run` tras aplicar a prod.

**Aplicado en:** migración `20260610120000_18_seq_demin_v1_cadence_d40_d80_d120.sql`; `follow_ups.py`, `generate_draft.py`, `classify_replies.py`; prompts `generate_email_value.md` (nuevo), `generate_email_closing.md` (v3), `generate_email_reframe.md` (v3); `apps/dashboard/.../metrics/page.tsx`; tests de workers (636 passed); `todo.md` D11 + §9.2 + log §19. NO aplicada a prod en esta sesión.

---

## 2026-06-17 — Lección 63: aplicar una migración de cadencia en el VPS la ACTIVA en vivo (el timer la lee en runtime); deploy seguro = parar el timer O confirmar 0-inmediatos antes, + limpiar los drafts in-flight obsoletos

**Contexto:** deploy de la cadencia nueva (migración 18, L62) al VPS de producción. El plan ingenuo ("git pull → aplicar migración → dry-run → parar antes de activar") asumía que aplicar la migración era inerte. **No lo es.**

**Lo aprendido (patrón operativo reutilizable):**

1. **Aplicar la migración = activar.** `demin-followups.timer` corre cada hora y lee `sequences.steps` de la BD **en runtime, sin --dry-run**. En cuanto la migración cambia la cadencia en BD, el siguiente disparo del timer actúa con ella. No hay un "punto de parada" entre migrar y activar: o se para el timer antes, o se acepta que migrar es activar. Para un cambio de cadencia, **el dry-run de verificación debe correrse ANTES de aplicar la migración a la BD viva** (reproduciendo la query real con las deltas nuevas inyectadas, en SELECT puro) — no después, porque "después" ya es producción activa.

2. **0-inmediatos hace el deploy de bajo riesgo aunque el timer siga vivo.** El dry-run (simulación read-only y, tras migrar, el `--dry-run` nativo) confirmó 0 candidatos en los 3 steps: ampliar de 14→40 días retrasa a todos y nadie llevaba aún 40 días desde su paso previo (primer toque nuevo ~14-jul). Con eso, aplicar la migración + cancelar los obsoletos + dejar el timer vivo es seguro: su próximo disparo crea 0. El parón del timer pasa a ser cinturón-y-tirantes, no requisito.

3. **Reordenar la cadencia deja drafts in-flight con ángulo obsoleto que hay que cancelar.** La cadencia vieja había dejado en cola HITL **48 reframe** (creados a D+14, demasiado pronto para el espaciado nuevo) y **6 closing** en `step_index=2` — slot que la cadencia nueva trata como `value`. Esos 6 closing, si Gonzalo los aprobaba y enviaba, generarían un segundo closing a +40d (doble-closing). Se cancelan (`status='cancelled'`, **sin** tocar `is_optout` — son drafts obsoletos, no bajas), con precondición de conteo exacto (48/6) y transacción con verificación de rowcount antes del commit. Regla: **un cambio de cadencia exige limpiar los drafts creados bajo el timing/indexado viejo**, no solo cambiar la definición.

4. **El VPS deriva del git: working tree con hotfixes a mano.** El árbol del VPS tenía cambios sin commitear (fix DSN de L60 aplicado a mano, migración 17 y un test como untracked) que bloqueaban el pull. Diagnóstico read-only: 0 commits propios, todo redundante o **superado** por origin (poll_imap del VPS era PRE-L60, 0 marcadores DSN vs 10 en origin). Reconciliado con `git stash push -u` (backup recuperable, no borrar) + `git pull` fast-forward limpio. Regla: **antes de un deploy, reconciliar el working-tree del VPS, no asumir pull limpio**; un `git stash -u` es la vía reversible cuando los cambios locales están superados por origin.

5. **`demin` no tiene sudo sin password** (root reseteada vía Hetzner, NOPASSWD no configurado — ver §"Nota sobre sudo" de todo.md). Parar/reactivar timers (`systemctl stop/start`) lo hace el humano; los workers son oneshot (`uv run` fresco por disparo), así que recogen el código nuevo del pull sin restart. Planear los deploys contando con que el agente NO puede tocar systemd.

**Regla resultante:** desplegar un cambio de cadencia a prod = (a) reconciliar working-tree del VPS (`git stash -u` si hay hotfixes superados) + `git pull`; (b) **dry-run de verificación ANTES de migrar** (simulación SELECT con deltas nuevas) → confirmar 0 toques inmediatos/vencidos; (c) aplicar la migración (scope-check: exactamente la esperada); (d) cancelar los drafts in-flight obsoletos (conteo exacto + transacción + sin opt-out); (e) `--dry-run` nativo de confirmación; (f) si hubiera toques inmediatos, parar el timer (humano, sudo) antes de migrar.

**Aplicado en:** deploy 2026-06-17 al VPS Hetzner — migración 18 aplicada a prod (`apply_migrations.py --env prod`, verify OK), 54 drafts obsoletos cancelados (48 reframe + 6 closing), `hitl_mode` intacto (True), dry-run nativo 0 candidatos. Pendiente 1 (fix DSN L60) quedó también desplegado por el mismo pull. Acceso SSH de Fer añadido (`authorized_keys` con 2 claves); 1C (desactivar password auth) saltado por falta de sudo.

---

## 2026-06-17 — Lección 64: cambio de modelos a Opus — el `.env` no estaba cableado, Opus antepone prosa al JSON, y editorializa cuando el research es pobre

**Contexto:** decisión de Alberto de subir los workers LLM a Opus 4.8. Tres descubrimientos en cadena al ejecutarlo.

**1. El string de Opus: verificar contra la cuenta, no asumir.** `claude-opus-4-8` SÍ existe y la cuenta lo acepta (verificado con `client.models.list()` + llamada mínima `messages.create`). Regla: antes de cambiar un model id en prod, confirmar con `models.list()` / una llamada de prueba — no asumir el string. La cuenta tiene Opus 4.5–4.8, Sonnet 4.5/4.6, Haiku 4.5.

**2. Bug latente: las vars de modelo del `.env` estaban mal nombradas y se ignoraban.** `config.py` (`Settings`, `case_sensitive=True`, `extra="ignore"`) solo lee 4 nombres EXACTOS: `ANTHROPIC_MODEL_CLASSIFY/_GENERATE/_RESEARCH/_REPLY`. El `.env.prod` (y `.env.example`) traían `..._CLASSIFY_DESCR`, `..._GENERATE_DRAFT`, `..._CLASSIFY_REPLY`, `..._SUGGEST_RESPONSE` → **todas ignoradas**; el sistema corría con los **defaults del código** (que por casualidad coincidían: Haiku/Sonnet). **Implicación crítica:** editar las vars que había NO cambia nada. Siempre **verificar el modelo resuelto en runtime** (`settings.* + MODEL_FOR_TASK`), no fiarse de que el `.env` "tiene una var con ese aspecto". Corregido `.env.example` + `.env.prod`. Colateral conocido: `generate_draft` y `suggest_response` comparten `ANTHROPIC_MODEL_GENERATE` (no hay key separada); `research_prospect` y `research_t4_nowebsite` comparten `_RESEARCH`.

**3. Opus 4.8 antepone razonamiento antes del JSON → rompió el parser (2/3 fallos).** Pese a pedir "solo JSON", Opus emite prosa ("La investigación está casi vacía… devuelvo un borrador honesto… {…}") y `json.loads` directo daba `Expecting value: line 1 column 1`. Fix: `shared/jsonutil.extract_json_block` (extrae el primer `{…}` balanceado tolerando prosa/fences), usado en `generate_draft.parse_llm_json` y `research_prospect.parse_research_json`. Tras el fix: 2/2 OK. Regla: cualquier worker que parsee JSON de un LLM "reasoning-forward" debe extraer el bloque, no asumir JSON-only.

**4. Opus editorializa cuando el research es pobre — y la validación mecánica no lo caza.** Para 2 contactos T4 con research fino, Opus generó meta-comentario; uno pasó las validaciones §10.3 con subject literal **"Sin datos para personalizar"** (4 palabras, sin emoji/promesa/leak → válido mecánicamente, basura semánticamente). Lo atrapa el HITL (Gonzalo lo rechaza), no el código. Doble lección: (a) un contacto con research pobre da mal draft con cualquier modelo — no forzar; (b) la validación mecánica no sustituye el criterio humano (HITL sigue siendo la red).

**Coste/beneficio (dato que pidió Alberto):** pricing verificado (claude.com 2026-06-17): **Opus 4.8 $5/$25 por MTok vs Sonnet 4.6 $3/$15** (1.67×) + **Opus 4.7+ usa tokenizer nuevo, hasta +35% tokens** → brecha real mayor. Draft de opening: **~$0.03–0.047 con Opus** vs ~$0.018–0.028 con Sonnet. Gasto total de esta tarea ~$0.35 (incluye 6 reintentos desperdiciados antes del fix del parser). **A revisar:** medir reply-rate de drafts Opus vs Sonnet antes de decidir si el sobrecoste compensa. Tabla `PRICING_USD_PER_MTOKENS` rellenada → el log de coste deja de ser `None`.

**Decisión final aplicada (opción 3 de Alberto):** `classify_descr` vuelve a **Haiku** (L3: Opus es overkill y caro para clasificar); `research_prospect` y `generate_draft` (y por colateral `suggest_response`) en **Opus 4.8**; `classify_reply` en Haiku. `hitl_mode` intacto (True) — verificado que `auto_approve` es no-op con `hitl_mode=true` (0 aprobaciones `auto`; Gonzalo aprueba a mano).

**Aplicado en:** `.env.prod` (VPS, gitignored) + `.env.example` (nombres correctos), `shared/jsonutil.py` (nuevo), `shared/llm.py` (pricing), `pipeline/generate_draft.py` (parser + coste model-aware), `pipeline/research_prospect.py` (parser), `tests/test_generate_draft.py` (test preámbulo, 63 pass). Commit `19764e6`. 3 drafts de opening generados (los únicos 3 vírgenes elegibles del universo actual — el pool está agotado, 154/157 primaries ya con opening; más requiere research de las 1.382 fit sin investigar).

---

## 2026-06-17 — Lección 65: gate de research antes de generar + el correo VENDE, no se disculpa — el cuello de calidad es el research, no el modelo

**Contexto:** Alberto vio 2 drafts malos en la cola HITL. **MECANISMO SL:** cuerpo con "No conozco a fondo el detalle de vuestros proyectos, así que no voy a presuponer nada" — un correo de venta que se disculpa, suena inseguro. **IBERIA & CAUCASUS:** el "correo" era literalmente el modelo explicando que NO podía redactarlo ("La investigación no incluye tipo de actividad... recomiendo completar la investigación"). Causa raíz común: el pool raspaba el fondo (T4 con research vacío/fino) y el prompt mezclaba "no inventar" con el tono → correos-disculpa.

**Dos arreglos de fondo:**

1. **Gate de research (la pieza clave) — `generate_draft.has_sufficient_research`.** Antes de llamar al LLM se exige research REAL: `tipo_actividad_concreta` no vacío O ≥1 hook real. Si no → NO se genera draft; `mark_company_for_research` marca la empresa `_failed='insufficient_research'` (sale del pool de generate y entra en `research_prospect --retry-failed`) y se reporta `skipped_no_research`. Garantiza que NUNCA salga un correo-disculpa: sin datos, no hay draft. El prompt, por tanto, SIEMPRE tendrá hooks reales — ya no necesita rama "si no hay datos".

2. **Prompt que vende con confianza (los 5 prompts de email).** Sustituida "Honesto: si no sabes algo, no lo inventes" por la distinción explícita: **"no inventar" limita los HECHOS (no afirmar datos falsos del prospecto), NO el tono.** Prohibidas las frases de auto-sabotaje/disculpa ("no conozco a fondo", "no voy a presuponer", "sin datos no puedo"...). Bloque "VENDER CON CONFIANZA" en opening: es venta en frío — abre con seguridad, ancla en el research real, propón valor concreto.

**El cuello de botella de calidad es el RESEARCH, no el modelo.** Opus sobre research vacío da correo vacío (peor: editorializa la falta de datos — L64). Subir el modelo no arregla la falta de material; la palanca de calidad es investigar bien (o no enviar). Conecta con el pool agotado (1.382 fit sin research).

**El HITL no basta solo — por eso el gate es de fondo.** MECANISMO (el de la disculpa) había sido **aprobado por Gonzalo** (no cazó el problema): estaba `approved`, sin enviar, cuando se canceló por instrucción de Alberto. Un humano revisando en volumen aprueba drafts malos; el gate + el prompt evitan que el draft malo EXISTA, que es más robusto que confiar en que el HITL lo cace siempre.

**Aplicado en:** `generate_draft.py` (`has_sufficient_research` + `mark_company_for_research` + gate en `main` + `skipped_no_research`), 5 prompts `generate_email_{opening(v4),reframe,value,closing,re_engage_40}.md`, `tests/test_generate_draft.py` (gate; 160 pass). Commit `dcb9888`. Drafts MECANISMO (B87327136) + IBERIA (B85871283) cancelados + empresas marcadas para re-research; `is_optout` intacto; piremol (research bueno) intacto.

---

## 2026-06-17 — Lección 66: el cuello del pool no es research ni modelo — es DATA (contactos). Hunter casi agotado para este universo

**Contexto:** Alberto pidió "research de 250 + 50 drafts". Al comprobar el pool: **0 empresas fit-sin-research CON web** (las 1.301 sin research no tienen web → `research_prospect`, que scrapea, no puede investigarlas). Pivote acordado: Hunter sobre las 157 fit con research bueno SIN contacto → generar.

**Resultado de Hunter (254 búsquedas, quota 2000):**
- T1: 0/69. T2: 0/10. T4: 0/122 (solo-web). **T3: 13/53.** Yield global ~5%. → **9 drafts** (T3, todos `corporativo_pequeno`), gated, **9/9 buenos** (0 disculpa).

**Por qué tan bajo:**
- **T1/T2 (alto valor):** Hunter devuelve emails genéricos (info@…) pero `email_policy.is_acceptable_for_tier` exige decisor/nominal para tiers grandes → rechazados. Domain-search no destapa decisores nominales para estas.
- **T4 (mínimo valor):** Hunter no tiene datos de empresas tan pequeñas → 0 emails.
- **T3 (medio):** `corporativo_pequeno` es aceptable → 13 mailboxes genéricos.

**Conclusión estratégica — el bottleneck es DATA, no research ni modelo.** El research del universo con-web ya está hecho (309 buenas); el modelo es Opus (L64); lo que falta son CONTACTOS, y Hunter domain-search está casi agotado para este universo (5% yield, 0 en alto valor). Para repoblar de verdad: (a) **ingesta nueva** (Palanca C SABI limítrofes → más empresas con web) y/o (b) **contactos a nivel decisor** para T1/T2 (LinkedIn/Phantombuster, Palanca A) — Hunter no los encuentra. Subir el modelo o "investigar más" (no hay con web) NO mueve la aguja.

**El gate (L65) aguantó:** 9/9 drafts generados eran research bueno (0 saltados, 0 correos-disculpa) pese a raspar el fondo.

**Coste:** research $0 (0 candidatos, no se corrió — se evitó ~$20 de Opus inútil al comprobar el pool ANTES), generación ~$0.44 Opus (9 × ~$0.049), 254 búsquedas Hunter (gratis, subscription, 254/2000). **Patrón:** comprobar el pool real (read-only) ANTES de lanzar un lote caro — el plan asumía 250 con web y había 0.

**Aplicado en:** `find_contacts.py` (flag `--require-web` para evitar fuzzy by-name sin dominio — 0% yield L58 — commit `9bc91e9`); 9 drafts opening en cola HITL (T3); 13 contactos Hunter nuevos. Pool: 1.727 fit / 1.301 sin research (0 con web) / 309 research bueno.

---

## 2026-06-19 — Lección 67: una feature que parece contradecir una regla no negociable NO la deroga unilateralmente — para y pregunta; el humano suele reencuadrarla más simple

**Contexto:** Fer pidió un Approval/Inbox "consciente de respuesta": apertura si no han hablado, seguimiento si ya contestaron. El mapeo del código (5 subagentes en paralelo) destapó que "la IA genera el seguimiento dentro del hilo" chocaba de frente con **L45** (el bot nunca escribe dentro de un hilo abierto; Gonzalo responde a mano). Mi primer plan asumió derogar L45 vía HITL y diseñó 5 piezas nuevas (prompt + ángulo + worker + migración + threading en `send_gmail`).

**Corrección humana:** Fer NO derogó L45. La reencuadró: L45 se MANTIENE → la IA **no** redacta si han contestado; la IA solo redacta en silencio (la cadencia que YA existía); el Caso B es **100% read-only** (mostrar hilo + clasificación + responder a mano en Gmail). El reencuadre **eliminó ~5 piezas** de la implementación: quedó en solo dashboard read-only (3 ficheros nuevos + 3 editados, sin migración, sin workers, sin tocar `send_gmail`).

**Regla resultante:**
1. Cuando una feature nueva parece contradecir un `[DECIDIDO]` o una lección no negociable (Apéndice A regla 9), **NO la implementes asumiendo que la deroga** — PARA y plantéaselo al humano con las opciones explícitas. La decisión de tumbar una regla es suya, no mía.
2. **Lo más simple suele ser respetar la regla, no sortearla.** El reencuadre del humano fue mucho más barato que mi plan de "derogar y construir".
3. **Mapea el código real ANTES de prometer un diseño.** El conflicto con L45 no era evidente desde la petición; lo destapó el mapeo en paralelo. Descubrir el choque antes de planear evitó construir lo que no era.
4. Las **preguntas de clarificación** (apertura/seguimiento, in-thread, categorías) no fueron fricción: revelaron una simplificación de alcance enorme. Preguntar lo que de verdad cambia el diseño > asumir.

**Aplicado en:** feature Caso A/B (inbox hilo completo + cola consciente de respuesta), 6 ficheros en `apps/dashboard/` (`lib/conversation.ts`, `lib/reply-format.ts`, `components/conversation-thread.tsx` nuevos; `inbox/page.tsx`, `approval-queue/page.tsx`, `approval-queue-content.tsx` editados). Ver log §19 (2026-06-19).

---

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
