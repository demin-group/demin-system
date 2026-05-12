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

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
