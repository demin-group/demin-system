# DEMIN — Plan de construcción del sistema de captación automática

> **Documento maestro.** Es la fuente de verdad para Claude Code. Todo lo que no esté aquí no se hace sin preguntar al humano. Todo lo que esté aquí marcado como `[DECIDIDO]` no se cuestiona — son decisiones tomadas tras conversaciones largas; cambiarlas requiere consulta explícita.

**Estado:** plan v1.3 — Bloque A CERRADO + Bloque C CERRADO (web pública en producción `https://demingroupmadrid.com`, deploy 2026-05-04; ver §19)
**Última actualización:** 2026-05-04

---

## Quick reference

**Qué construimos:** un agente de IA que actúa como SDR (Sales Development Rep) para DEMIN Group, una empresa de demoliciones interiores en Madrid. Toma 5.619 empresas de un Excel de Sabi, las filtra hasta ~400-500 leads cualificados, investiga cada una en su web, redacta correos genuinamente personalizados (no plantillas), gestiona la secuencia de envío y los follow-ups, clasifica respuestas y escala lo importante a Gonzalo (responsable de DEMIN). Todo bajo identidad de Gonzalo, con dashboard custom para operarlo.

**Stack en una línea:** Next.js 15 + Supabase (Postgres + pgvector + Auth) + Python workers + Gmail API + Anthropic API.

**Coste recurrente estimado:** ~110-130€/mes (techo del usuario: 150€).

**Tiempo estimado:** 6 semanas, 4 fases incrementales.

---

## 1. Contexto del negocio

### 1.1 Quién es DEMIN
Empresa de Madrid especializada en **demoliciones interiores y limpieza de espacios** para preparación de reformas. Su rol en el ciclo de obra es la "fase cero": entrar antes que los gremios, vaciar el espacio, retirar escombros, dejarlo listo para que el reformista empiece a construir desde el día 1.

Responsable: **Gonzalo Pérez**. Operación pequeña, alta especialización, valor diferencial es rapidez + limpieza + cumplimiento normativo.

### 1.2 Qué venden
Servicios de demolición interior: desmontaje de falsos techos, tabiquería, vaciados técnicos, gestión de escombros. Proyectos típicos van de 7k€ (trabajo pequeño) a 100k€+ (proyecto grande). Sweet spot operativo: 5k-100k€ (validado en captura de KB con Gonzalo, sesión 1, 2026-04-29). Por encima de 100k€ se estudia caso a caso — precedente activo: caso Calle Montalbán de 230k€ en seguimiento. Ver KB documento `servicios`, sección 'Sweet spot de presupuesto'.

### 1.3 ICP (Ideal Customer Profile)
Empresas que **coordinan obras integrales y subcontratan la fase de demolición**. Es decir:

- Constructoras de obra residencial
- Promotoras inmobiliarias
- Estudios de arquitectura que llevan ejecución
- Reformistas medianos
- Administradores de fincas (para reformas en comunidades)

**Nota de calibración tras KB sesión 1 (2026-04-29):** cuando se le pregunta
a Gonzalo por sus mejores clientes y por su cliente ideal, menciona
exclusivamente **constructoras**. No descarta los otros 4 perfiles, pero no
los respalda con experiencia cerrada. El sistema sigue prospectando a los 5
perfiles, pero los correos generados NO fingen experiencia con perfiles
donde Gonzalo no la tiene. Ver KB documento `icp` para el detalle.

**Lo que NO es ICP** (aunque pase el filtro CNAE): instaladores especialistas (climatización, fontanería, electricidad, asfaltado, conductos…). Esos son gremios al mismo nivel que DEMIN, no clientes.

**Sectores y obras adicionales fuera de alcance, validados con Gonzalo en KB
sesión 1:**

- **Obras públicas** — trabas documentales, no compensa.
- **Demoliciones de fachadas** — implican andamios, sin experiencia en
  montaje ni contratación.
- **Obras que requieran plantilla > 20 personas** — exceden capacidad.

Estas tres exclusiones deben incorporarse al prompt
`apps/workers/shared/prompts/classify_fit.md` cuando se construya en Fase 1
(B-something del plan).

### 1.4 Por qué este sistema
Hoy Gonzalo hace prospección manual: dossier + correo de apertura + 1-2 follow-ups, todo a mano, uno a uno. No escala. Este sistema automatiza el ciclo completo manteniendo la calidad de un humano: cada correo se redacta tras investigar al prospecto, con tono propio, sin que el cliente sepa que hay automatización detrás.

---

## 2. Visión del sistema

### 2.1 Qué hace el sistema (los 7 pilares)

1. **Conoce el negocio a fondo** vía RAG: KB editable con servicios, ICP, objeciones, casos de éxito, tono.
2. **Investiga cada cliente antes de escribirle**: scrapea su web, extrae señales reales (qué hacen, tamaño, proyectos recientes), y adapta el correo a esa empresa concreta.
3. **Redacta correos genuinamente personalizados**: no son plantilla + variables. Cada correo es una generación completa de LLM alimentada por el KB de DEMIN + dossier de investigación del prospecto + etapa de la secuencia.
4. **Aprobación humana en la cola**: panel de drafts que Gonzalo revisa/edita/aprueba (al inicio 100%, luego por lotes cuando haya confianza, luego autónomo).
5. **Clasifica respuestas y actúa**: 6 categorías (interesado, pide info, no ahora, no interesado, rebote, fuera de oficina) + flag de opt-out explícito. Acción por categoría definida en §11.
6. **Follow-ups automáticos** a D+4 y D+10 con ángulos distintos en cada toque.
7. **Aprende de los resultados**: en v1, el sistema mide y muestra patrones; humanos ajustan el KB/prompts. v2 (cuando haya datos suficientes) puede automatizar.

### 2.2 Qué NO hace el sistema
Anti-feature-creep. Estas cosas están explícitamente fuera del alcance:

- ❌ Llamadas telefónicas, llamadas en frío, voicebots
- ❌ LinkedIn outreach automatizado (puede venir en v2)
- ❌ WhatsApp outreach
- ❌ Generación de presupuestos
- ❌ Cierre de ventas — el bot nunca se compromete a precios ni plazos
- ❌ Negociación con el cliente — todo lo que requiere criterio se escala a Gonzalo
- ❌ Aprendizaje automatizado en v1
- ❌ Multi-tenancy / SaaS para terceros — esto es para DEMIN, no es un producto
- ❌ **Teléfono como dato del prospecto.** DEMIN solo usa email — el sistema no incluye teléfono en `contacts` ni se muestra en el dashboard ni se ofrece como dato a Gonzalo en ninguna fase. Decisión 2026-05-04 tras evaluación. Razones: coherencia con identidad de DEMIN (trato cercano, no invasivo), simplicidad operativa, foco en el canal con infra completa construida (Workspace + warmup + cadencia + clasificación).

### 2.3 Métricas de éxito
**No optimizamos open rate ni reply rate** como objetivo final. Optimizamos:

- **Reuniones cerradas/mes** (objetivo v1: ≥3-5/mes en régimen autónomo)
- **Conversión de reunión a presupuesto enviado** (proxy de calidad de leads)
- **Conversión de presupuesto a obra cerrada**
- **Coste de adquisición** (€ gastados / obra cerrada)

Métricas operativas que sí trackeamos para diagnosticar (no como objetivo): bounce rate (alarma si >2%), spam complaints (alarma si >0.1%), reply rate por ángulo de email, deliverability por buzón.

---

## 3. Decisiones arquitectónicas cerradas

| # | Decisión | Estado |
|---|---|---|
| D1 | Autonomía: HITL primeros lotes → autónomo cuando se valide | [DECIDIDO] |
| D2 | Origen de leads: Excel Sabi (5.619 empresas) + enriquecimiento programático | [DECIDIDO] |
| D3 | Plataforma de envío: custom Gmail API + dominio propio nuevo | [DECIDIDO] |
| D4 | Warmup: externalizado (Lemwarm o Warmup Inbox), no se construye | [DECIDIDO] |
| D5 | CRM/dashboard: custom desde día 1, Next.js + Supabase | [DECIDIDO] |
| D6 | Filtrado: reglas tier T1-T4 + clasificador IA por descripción | [DECIDIDO] |
| D7 | ~~Enriquecimiento: scraping custom para 880 con web; Apollo (~45€/mes) para 857 sin web~~ | [SUPERSEDED por D17 — 2026-05-04] |
| D8 | Personalización: redacción IA completa por correo, no plantillas con variables | [DECIDIDO] |
| D9 | KB del negocio: vía RAG con `pgvector` en Supabase, editable desde dashboard | [DECIDIDO] |
| D10 | Investigación pre-redacción: scrapeo + extracción IA del dossier del prospecto | [DECIDIDO] |
| D11 | Cadencia: 3 toques (D0, D4, D10) con ángulos distintos por toque | [DECIDIDO] |
| D12 | Clasificación de respuestas: 6 categorías + flag de opt-out explícito | [DECIDIDO] |
| D13 | Re-engage: "no ahora" → +60 días; "no interesado" → +90 días; opt-out → permanente | [DECIDIDO] |
| D14 | Aprendizaje: manual en v1 (humanos ajustan KB/prompts viendo métricas) | [DECIDIDO] |
| D15 | Tope SaaS: 150€/mes | [DECIDIDO] |
| D16 | Modelo de leads híbrido empresa-decisor. SABI sigue siendo universo de empresas (5.578 ya cargadas). Para cada empresa accionable con `ia_fit='fit'`, el sistema busca 2-3 decisores reales (gerente, jefe de obra, responsable compras) usando email finder por dominio. | [DECIDIDO 2026-05-04] |
| D17 | ~~Hunter.io como email finder primario, RocketReach como adapter de respaldo. Interfaz `EmailFinder` abstracta desde el principio para evitar refactor mayor si Hunter falla. ExtractorLead descartado para ahora (modelo de filtros generales no encaja con flujo SABI-first); apuntado como fuente potencial de descubrimiento de leads nuevos cuando se agoten los SABI. Sustituye a D7.~~ | [SUPERSEDED por D19 — 2026-05-06] |
| D18 | 2-3 decisores por empresa (gerente + jefe de obra + responsable de compras donde aplique). Más allá de 3 genera percepción de spam para el destinatario; menos pierde el lead si el primero no responde. | [DECIDIDO 2026-05-04] |
| D19 | RocketReach descartado por API gateada al plan Ultimate ($2.484/año, excede techo D15). Hunter validado AMARILLO (8% hit rate decisor sobre 25 empresas SABI, commit 3c5b7a9). Plan revisado: probar **Skrapp y Apollo** (free tier con API) sobre el mismo sample 25 empresas con criterio dual (decisor + any email útil según D20). Adapter primario y secundario decididos tras prueba comparativa, no antes. La interfaz abstracta `EmailFinder` se mantiene. Sustituye a D17. | [DECIDIDO 2026-05-06] |
| D20 | Política de aceptación de emails por tier de empresa. **T1 y T3** (1k-5k€ y 0.5k-1k€) aceptan decisor + nominal con cargo + corporativo_pequeno (whitelist positiva por prefijo: `info@`, `contacto@`, `gerencia@`, `obras@`, etc.). **T2** (5k-20k€) acepta decisor o nominal con cargo identificable; sin eso, fallback humano. **T4** (sin web) pendiente de resolver tras prueba comparativa (D19). Whitelist negativa global (todos los tiers): `marketing@`, `rrhh@`, `prensa@`, `noreply@`, etc. Razón: empresas micro/pequeñas no filtran `info@` — el gerente lo lee directamente; medianas sí filtran y exigen al menos email nominal. | [DECIDIDO 2026-05-06] |
| D21 | **Arquitectura híbrida de email finder por tier** (camino 1 tras Frente E ROJO global 20%). El reanálisis Hunter+D20 sobre las mismas 25 empresas (commit 36d5077) dio **T3=80%** (production-ready) pero **T1=0%, T2=20%, T4=0%**. Apollo y Skrapp también descartados durante la sesión (Apollo people endpoints gateados Free, Skrapp API gateada Enterprise — Lección 21 aplicada por 4ª vez). Decisión: Hunter es adapter primario único viable; otros adapters quedan como hooks futuros tras la interfaz `EmailFinder`. Plan de cobertura por tier: **T3** = Hunter+D20 production-ready en Sprint 4. **T2** = Hunter+D20 + research IA enriquece-cargo en Sprint 4 paso 4 (sube estimado 20%→50-60%, validar empíricamente). **T1 y T4** = Opción C completa en Sprint 5 (research IA web + permutación de patrones email + verificación con MillionVerifier; T4 complementada con `empresite.com` como fuente de email visible). | [DECIDIDO 2026-05-06] |
| D22 | **Roll-out escalonado de Sprint 4 productivo por tier**. **Semana 1 post-warmup: solo T3** (~51 empresas accionables tras `ia_fit='fit'` con cap inicial 10/día). **Semana 2-3: añadir T2** con research IA enriquece-cargo. **Semana 4+: mantenimiento** (revisión de métricas) + arrancar Sprint 5 (T1+T4 con Opción C) si reply rate de T3+T2 valida el sistema. Razón: empezar con leads de alta probabilidad de respuesta calienta dominio y genera baseline de reputación antes de escalar a leads inciertos. Los primeros ~100 envíos marcan la reputación de remitente para los siguientes ~1.000 — práctica industrial estándar capturada en Lección 27. | [DECIDIDO 2026-05-06] |

---

## 4. Stack técnico

| Capa | Tecnología | Justificación |
|---|---|---|
| Frontend dashboard | Next.js 15 + TypeScript + Tailwind + shadcn/ui | Stack más Claude-Code-friendly, UI bonita sin pelearse con CSS |
| Backend API | Next.js API routes + Supabase Edge Functions | Una codebase, deploy unificado |
| Database | Supabase Postgres (con `pgvector` para RAG) | Free tier generoso, RLS, auth integrado |
| Auth | Supabase Auth (magic link) | Sin contraseñas; entran Gonzalo + colaborador |
| Workers / pipeline | Python 3.11 en VPS Hetzner CX22 (~5€/mes) | Cron + systemd; SQLAlchemy hacia Supabase |
| Cola de jobs | Postgres con tabla `jobs` + worker pull | Suficiente al volumen; sin Redis ni Celery |
| LLM | Anthropic Claude Sonnet 4.5 (clasificación + redacción + extracción) | Calidad alta y precio razonable |
| Embeddings | Voyage AI `voyage-multilingual-2` (1024 dim) | Decidido en Bloque A. Multilingüe (ES nativo) y casa con `vector(1024)` del schema §6.2 |
| Email envío | Gmail API + dominio propio + Workspace | Custom según D3 |
| Email warmup | Lemwarm Essential 29€/mes standalone (1 buzón) | Descartados Warmup Inbox y Smartlead por bloqueo de App Passwords / OAuth no verificado en Workspace |
| Scraping | Python `httpx` + `selectolax` + `tldextract` | Más rápido que requests+BS4 |
| Browser-needed scraping | `playwright` (cuando JS bloquee httpx) | Solo si fallback |
| Email finder primario (T2/T3 con web) | **Hunter.io Domain Search API** | Único adapter viable tras descarte Apollo (people endpoints gated Free) y Skrapp (API gated Enterprise) — Lección 21 aplicada 4× incl. RocketReach. Validado AMARILLO al 8% decisor estricto, **80% en T3 con criterio D20** (commits 3c5b7a9 + 36d5077). Free tier 25 búsquedas/mes basta para T3+T2 del primer batch (~115 leads accionables); plan Starter solo si se escala más allá. |
| Enriquece-cargo T2 | **Research IA web (`research_prospect.py`, §8.4)** con función dual | Hunter en T2 devuelve nombres reales sin cargo identificado en bastantes casos (COPROMA, MG AISLAMIENTOS). El worker de research lee la web del prospecto y extrae cargos de las personas que aparecen ahí, cruza con los nombres de Hunter para reclasificar nominal-sin-cargo → nominal-con-cargo. Función crítica de Sprint 4 paso 4, no secundaria. |
| Email finder T1+T4 | **Opción C: research IA + permutación de patrones email + verificación** (Sprint 5) | Hunter no indexa T1 ni T4 (0% en ambos). T1 (~118 fits con web) requiere scrapeo + extracción de nombres+cargos + permutación `nombre@`/`n.apellido@`/`nombre.apellido@` + verificación MillionVerifier. T4 (~288 fits sin web, 55.6% del universo accionable, Lección 24) suma `empresite.com`/`einforma.com` como fuente complementaria de email visible (Lección 26). |
| Otros adapters (Skrapp/Apollo/RocketReach) | Descartados | Mantenidos como hooks teóricos tras la interfaz abstracta `EmailFinder` (§8.6) por si en el futuro alguno cambia su pricing. RocketReach Ultimate $2.484/año (D17→D19), Skrapp Enterprise $262/mes, Apollo Free no expone people endpoints. |
| Hosting dashboard | Vercel free | Suficiente |
| Repo | GitHub privado | Estándar |
| Logs / observabilidad | Logflare (free tier de Supabase) o Axiom | Trazabilidad básica |
| Secrets | Variables de entorno + Supabase Vault | Nunca commitear nada |

---

## 5. Estructura del repositorio

```
demin-system/
├── apps/
│   ├── web/                          # Sitio público (demingroupmadrid.com) — Vercel
│   │   ├── app/
│   │   │   ├── page.tsx              # Landing one-pager con anchors
│   │   │   └── api/contact/route.ts  # Endpoint del formulario → Supabase
│   │   ├── components/
│   │   ├── public/                   # Imágenes de obras (aporta Gonzalo)
│   │   └── package.json
│   ├── dashboard/                    # Panel autenticado (app.demingroupmadrid.com) — Vercel
│   │   ├── app/
│   │   │   ├── (auth)/login
│   │   │   ├── pipeline/             # Pantalla 1
│   │   │   ├── approval-queue/       # Pantalla 2
│   │   │   ├── inbox/                # Pantalla 3
│   │   │   ├── kb/                   # Pantalla 4 (CRUD del KB)
│   │   │   ├── metrics/              # Pantalla 5
│   │   │   └── settings/             # Pantalla 6
│   │   ├── components/ui/            # shadcn
│   │   ├── lib/supabase/
│   │   └── package.json
│   └── workers/                      # Python (despliegue Hetzner)
│       ├── pipeline/
│       │   ├── ingest_sabi.py        # Carga el Excel (Sprint 2 paso 1)
│       │   ├── classify_descr.py     # Filtro IA por descripción (Sprint 3)
│       │   ├── research_prospect.py  # PENDIENTE Sprint 4 paso 4b — función dual D21 (dossier + personas_extraidas)
│       │   ├── find_contacts.py      # PENDIENTE Sprint 4 paso 4 — email finder D21 + cruce personas_extraidas
│       │   ├── enrich_emails.py      # PENDIENTE Sprint 4 paso 3 — interfaz EmailFinder + HunterAdapter (D21)
│       │   ├── verify_emails.py      # PENDIENTE Sprint 4 — MX + SMTP check
│       │   ├── scrape_emails.py      # STUB histórico descartado (D17 → D19 → D21)
│       │   └── apollo_enrich.py      # STUB histórico descartado (D7 → D17 → D19 → D21)
│       ├── outreach/
│       │   ├── generate_draft.py     # PENDIENTE Sprint 4 paso 5 / Fase 2
│       │   ├── send_gmail.py         # PENDIENTE Fase 2 (envío real)
│       │   └── follow_ups.py         # PENDIENTE Fase 2 (Programador D4 / D10 / re-engage)
│       ├── replies/
│       │   ├── poll_imap.py          # PENDIENTE Fase 3
│       │   ├── classify_replies.py   # PENDIENTE Fase 3
│       │   └── handle_actions.py     # PENDIENTE Fase 3 (acción por categoría)
│       ├── monitoring/
│       │   └── auto_pause.py         # PENDIENTE Fase 3 (bounce >2%, spam >0.1%)
│       ├── kb/
│       │   └── embed_documents.py    # Pipeline de embeddings (Sprint 1 paso 2)
│       └── shared/
│           ├── db.py                 # SQLAlchemy (Sprint 1 paso 1)
│           ├── llm.py                # Cliente Anthropic + Voyage (Sprint 1 paso 1)
│           ├── config.py             # pydantic-settings dev/prod (Sprint 1 paso 1)
│           ├── email_policy.py       # PENDIENTE Sprint 4 paso 2 — whitelists D20 + clasificador
│           └── prompts/              # Prompts versionados (regla 8 Apéndice A)
│               ├── classify_fit.md   # Sprint 3
│               └── generate_email_*  # PENDIENTE Sprint 4 paso 5 — opening/reframe/closing
├── infra/
│   ├── supabase/migrations/          # SQL de schema
│   └── systemd/                      # Worker units
├── tasks/
│   ├── todo.md                       # ESTE DOCUMENTO
│   └── lessons.md                    # Lecciones capturadas
├── docs/
│   ├── dossier_demin.pdf             # Dossier comercial original
│   └── onboarding_demin.pdf          # Doc de onboarding original
└── README.md
```

---

## 6. Esquema de base de datos

### 6.1 Tablas principales

```sql
-- Empresas (lo que viene de Sabi + enriquecimiento)
create table companies (
  id              uuid primary key default gen_random_uuid(),
  nif             text unique not null,
  nombre          text not null,
  localidad       text,
  descripcion     text,                  -- Sabi
  web             text,                  -- Sabi o enriquecida
  rev_y0_keur     numeric,               -- Ingresos último año (k€)
  rev_y1_keur     numeric,
  rev_growth_pct  numeric,
  tier            text check (tier in ('T1','T2','T3','T4','descartado')),
  ia_fit          text check (ia_fit in ('fit','no_fit','dudoso','pendiente')) default 'pendiente',
  ia_fit_reason   text,                  -- razón breve para auditar
  research_done_at timestamptz,
  research_data   jsonb,                 -- dossier de investigación (ver §10)
  created_at      timestamptz default now()
);
create index on companies(tier, ia_fit);

-- Contactos (decisores dentro de cada empresa)
create table contacts (
  id              uuid primary key default gen_random_uuid(),
  company_id      uuid references companies(id) on delete cascade,
  email           text not null,
  email_verified  boolean default false,
  email_source    text check (email_source in ('sabi','web_scrape','apollo','hunter','skrapp','manual')),
  -- 'hunter' añadido 2026-05-04 (D17). 'skrapp' añadido 2026-05-06 (D19);
  -- 'rocketreach' eliminado por descarte (D19 supersede D17 — RocketReach
  -- requiere plan Ultimate $2.484/año, excede techo D15, ver Lección 21).
  -- 'apollo' y 'web_scrape' se conservan por compatibilidad histórica.
  -- TODO migration al arrancar Sprint 4: ALTER TABLE contacts DROP CONSTRAINT
  -- + ADD CONSTRAINT con la lista revisada, junto con email_type y
  -- email_priority abajo.
  email_type      text check (email_type in ('decisor','nominal','corporativo_pequeno','descartado')),
  -- AÑADIDO 2026-05-06 (D20). Pendiente migration al arrancar Sprint 4.
  --   decisor:             cargo claro de gerente / director / responsable
  --                        con autoridad de contratación de obras.
  --   nominal:             email tipo `nombre.apellido@` con cargo no claro
  --                        o no decisor estricto pero útil. Aceptado en
  --                        todos los tiers como segundo recurso.
  --   corporativo_pequeno: buzón con prefijo de la whitelist positiva
  --                        (info@, contacto@, hola@, gerencia@, obras@,
  --                        proyectos@, comercial@, direccion@, oficina@,
  --                        administracion@). Aceptado SOLO en T1 y T3
  --                        (empresas pequeñas donde el gerente lee `info@`
  --                        directamente sin filtro humano intermedio, D20).
  --   descartado:          buzones de la whitelist negativa global
  --                        (marketing@, rrhh@, prensa@, comunicacion@,
  --                        noreply@, facturas@, contabilidad@, webmaster@,
  --                        soporte@, etc.). NO se usa para outreach en
  --                        ningún tier.
  email_priority  int check (email_priority between 1 and 4),
  -- AÑADIDO 2026-05-06 (D20). Pendiente migration al arrancar Sprint 4
  -- productivo (paso 1 de §14, antes de implementar HunterAdapter).
  -- Orden de envío cuando hay varios contacts por la misma empresa.
  -- 1 = mejor candidato (decisor con confidence alto del adapter primario);
  -- 4 = peor (corporativo_pequeno en T1/T3 sin alternativa). Se rellena al
  -- insertar en find_contacts.py según política tier-segmentada.
  nombre          text,                  -- si lo conocemos
  cargo           text,
  linkedin_url    text,
  is_primary      boolean default false,
  is_optout       boolean default false,
  optout_at       timestamptz,
  optout_reason   text,
  created_at      timestamptz default now(),
  unique(company_id, email)
);
create index on contacts(email_verified, is_optout);

-- Buzones de envío (3 buzones del dominio nuevo)
create table mailboxes (
  id              uuid primary key default gen_random_uuid(),
  email           text unique not null,
  display_name    text,                  -- "Gonzalo Pérez"
  daily_cap       int default 50,
  current_day_sent int default 0,
  warmup_status   text check (warmup_status in ('warming','ready','paused')),
  oauth_refresh_token_encrypted text,    -- guardado cifrado
  status          text check (status in ('active','paused','disabled')) default 'active',
  pause_reason    text
);

-- Secuencias y plantillas (las "etapas" de la cadencia)
create table sequences (
  id              uuid primary key default gen_random_uuid(),
  nombre          text not null,         -- "demin_v1"
  is_active       boolean default true,
  steps           jsonb not null         -- [{day:0,angle:'opening'},{day:4,angle:'reframe'},{day:10,angle:'closing'}]
);

-- Campañas (un envío masivo a un conjunto de leads con una secuencia)
create table campaigns (
  id              uuid primary key default gen_random_uuid(),
  nombre          text not null,
  sequence_id     uuid references sequences(id),
  status          text check (status in ('draft','running','paused','completed')) default 'draft',
  created_at      timestamptz default now()
);

-- Cada email enviado o por enviar
create table messages (
  id              uuid primary key default gen_random_uuid(),
  campaign_id     uuid references campaigns(id),
  contact_id      uuid references contacts(id),
  mailbox_id      uuid references mailboxes(id),
  step_index      int not null,           -- 0=apertura, 1=D+4, 2=D+10
  angle           text not null,          -- 'opening' | 'reframe' | 'closing' | 're_engage_60' | 're_engage_90'
  subject         text,
  body            text,
  status          text check (status in ('drafted','approved','scheduled','sent','bounced','failed','cancelled')) default 'drafted',
  scheduled_for   timestamptz,
  sent_at         timestamptz,
  gmail_message_id text,
  approved_by     text,                  -- email del humano que aprobó
  approved_at     timestamptz,
  edited          boolean default false,
  research_snapshot jsonb,               -- snapshot del research que usó para generar
  generation_cost_usd numeric,
  created_at      timestamptz default now()
);
create index on messages(status, scheduled_for);
create index on messages(contact_id);

-- Respuestas recibidas
create table replies (
  id              uuid primary key default gen_random_uuid(),
  message_id      uuid references messages(id),  -- el correo al que responden
  contact_id      uuid references contacts(id),
  received_at     timestamptz not null,
  raw_subject     text,
  raw_body        text,
  category        text check (category in ('interesado','pide_info','no_ahora','no_interesado','rebote','fuera_oficina','desconocido')),
  is_explicit_optout boolean default false,
  ai_classification_reason text,
  ai_suggested_response text,            -- redacción sugerida si aplica
  human_action    text check (human_action in ('pendiente','escalado','respondido','archivado','reprogramado')) default 'pendiente',
  created_at      timestamptz default now()
);

-- Eventos (log para métricas y debug)
create table events (
  id              uuid primary key default gen_random_uuid(),
  type            text not null,         -- 'message_sent','reply_received','bounce', etc.
  message_id      uuid references messages(id),
  contact_id      uuid references contacts(id),
  payload         jsonb,
  created_at      timestamptz default now()
);
create index on events(type, created_at);

-- Cola de jobs (para los workers Python)
create table jobs (
  id              uuid primary key default gen_random_uuid(),
  type            text not null,         -- 'research_prospect','generate_draft','send_email','classify_reply', etc.
  payload         jsonb,
  status          text check (status in ('pending','running','done','failed')) default 'pending',
  attempts        int default 0,
  last_error      text,
  scheduled_for   timestamptz default now(),
  created_at      timestamptz default now(),
  completed_at    timestamptz
);
create index on jobs(status, scheduled_for);
```

### 6.2 Tablas del Knowledge Base (RAG)

```sql
create extension if not exists vector;

-- Documentos del KB (servicios, ICP, objeciones, casos, correos de Gonzalo)
create table kb_documents (
  id              uuid primary key default gen_random_uuid(),
  category        text check (category in ('servicios','icp','objeciones','casos_exito','tono','diferenciador','correos_gonzalo','otro')),
  titulo          text not null,
  contenido       text not null,
  is_active       boolean default true,
  created_by      text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- Chunks con embeddings para retrieval
create table kb_chunks (
  id              uuid primary key default gen_random_uuid(),
  document_id     uuid references kb_documents(id) on delete cascade,
  chunk_index     int not null,
  contenido       text not null,
  embedding       vector(1024),           -- ajustar a la dim del modelo elegido
  created_at      timestamptz default now()
);
create index on kb_chunks using ivfflat (embedding vector_cosine_ops);
```

### 6.3 Notas

- **Row Level Security:** activar RLS en todas las tablas; políticas en Fase 0 son simples ("solo usuarios autenticados leen/escriben").
- **Migrations:** todas las migraciones en `infra/supabase/migrations/` con timestamp en nombre. Orden cronológico estricto.
- **No hay tabla de "campañas autónomas vs HITL":** el modo es global (toggle en `settings`). Cuando está en HITL, los `messages` se quedan en estado `drafted` esperando aprobación; en autónomo pasan directo a `scheduled`.

---

## 7. Knowledge Base (RAG)

### 7.1 Contenido inicial (lo que Gonzalo debe aportar)

Esto es **dependencia humana crítica de la Fase 1**. Sin esto, el agente redacta correos genéricos por mucho LLM que metamos. Se le pide a Gonzalo en Fase 0 una sesión de 60-90 minutos para vaciarle el cerebro y producir:

| Categoría | Qué contiene | Volumen mínimo |
|---|---|---|
| `servicios` | Cada servicio descrito con detalle: qué incluye, qué no, plazos típicos, cómo se diferencia | 4-6 documentos |
| `icp` | Por cada perfil del ICP: cómo es, qué le duele, cómo decide, qué objeciones suele tener | 5 documentos (uno por perfil) |
| `objeciones` | Objeciones reales que Gonzalo ha oído + cómo las responde | 8-12 entradas |
| `casos_exito` | 2-3 obras concretas: contexto, qué hicieron, resultado, sin nombres si no quiere | 2-3 documentos |
| `tono` | Cómo escribe Gonzalo: directo, sin floruras, profesional, cercano. Ejemplos de qué SÍ y qué NO. | 1 documento |
| `diferenciador` | El ángulo "somos pequeños y eso juega a vuestro favor" desarrollado: por qué importa, qué se traduce en operativa | 1 documento |
| `correos_gonzalo` | Correos reales que él ha mandado (con permiso). Sirven de ejemplo de tono. | 5-10 correos |

### 7.2 Pipeline de embedding

1. Documento se inserta o edita en la pantalla de KB del dashboard
2. Trigger en Postgres encola un job tipo `embed_document`
3. Worker `embed_documents.py`:
   - Toma el documento
   - Lo trocea (chunks de ~500 tokens con overlap de 50)
   - Genera embedding por chunk
   - Inserta en `kb_chunks`
4. Reembed completo si el documento cambia (borra chunks viejos, crea nuevos)

### 7.3 Retrieval en redacción

Cuando se va a redactar un correo, el sistema:

1. Toma el dossier del prospecto (research) y construye una query
2. Embeds la query
3. Recupera top-K (K=5) chunks más similares del KB
4. Pasa esos chunks al prompt del generador como contexto

---

## 8. Pipeline de leads

### 8.1 Ingesta del Excel de Sabi

- El Excel `docs/sabi_export.xlsx` ya está analizado: hoja `Resultados`, header en fila 1, **5.619 filas brutas → 5.578 NIFs únicos tras dedup** (ver Lección 18: SABI exporta cuentas consolidadas + individuales para 41 empresas grandes; deduplicación por "tier más alto gana"), 19 columnas (ver §6.1 estructura `companies` para mapping).
- Worker `ingest_sabi.py`: lee el Excel, valida cabeceras esperadas, normaliza `n.d.` → NULL, calcula `rev_growth_pct`, asigna `tier` por reglas (ver §8.2), deduplica por NIF.
- Idempotente por `nif` (UPSERT). Conserva `ia_fit`, `ia_fit_reason`, `research_done_at`, `research_data` en re-ejecuciones.

### 8.2 Reglas de tier (ya validadas)

```python
def assign_tier(rev_y0, has_web):
    if rev_y0 is None or rev_y0 < 500 or rev_y0 >= 20000:
        return 'descartado'
    if has_web:
        if 1000 <= rev_y0 < 5000:  return 'T1'   # 455 empresas
        if 5000 <= rev_y0 < 20000: return 'T2'   # 173
        if  500 <= rev_y0 < 1000:  return 'T3'   # 252
    else:
        return 'T4'                              # 857
    return 'descartado'
```

Total accionable: ~1.737. Pasamos al filtro IA (§8.3).

### 8.3 Filtro IA por descripción

Objetivo: descartar instaladores especialistas que pasan el CNAE pero no son ICP.

**Paso obligatorio antes de §8.5 (búsqueda de decisores).** Motivo económico: cada llamada al email finder consume créditos de Hunter; filtrar antes con Haiku (~$0.001/empresa) ahorra ~70% de búsquedas Hunter sobre las ~1.737 accionables (los `no_fit` y `dudoso` no se procesan).

Worker `classify_descr.py` itera sobre todos los `tier in (T1,T2,T3,T4)` con `ia_fit='pendiente'`. Por cada uno hace una llamada a Claude con este prompt (en `apps/workers/shared/prompts/classify_fit.md`):

```
Eres un analista que filtra empresas para una empresa de demoliciones interiores
en Madrid (DEMIN Group). DEMIN entra en obras como subcontratista para vaciar
espacios antes de reformas: tira tabiques, falsos techos, retira escombros.

Tu tarea: dada la descripción de actividad de una empresa, decidir si es un
CLIENTE POTENCIAL para DEMIN.

Cliente potencial = empresa que coordina obras integrales y subcontrata
demolición. Por ejemplo: constructoras, promotoras, reformistas que llevan
ejecución completa, estudios de arquitectura que ejecutan, administradores
de fincas que organizan reformas.

NO cliente potencial = gremios o instaladores especialistas que están al
mismo nivel que DEMIN. Por ejemplo: climatización, fontanería pura,
electricidad pura, asfaltado, pavimentación, carpintería, cristalería,
cerrajería, conductos, pintura, empresas de demolición (competidores).

Empresa: {nombre}
Descripción: {descripcion}

Responde SOLO con JSON:
{"fit": "fit"|"no_fit"|"dudoso", "reason": "<1 frase>"}
```

Coste: ~$0.001 × 1.737 = ~2€ una vez.

### 8.4 Investigación de prospecto (research) — función dual

**Reescrito 2026-05-06 (D21).** El worker pasa a tener **dos funciones**: la dossier-de-personalización original (D10, alimenta el prompt de redacción §10.2) **más** la nueva extracción de personas/cargos para enriquecer matches parciales del email finder en T2 (Hunter devuelve `nombre@dominio` sin cargo identificado en empresas medianas como COPROMA o MG AISLAMIENTOS — el research IA lee la web "Equipo" / "Sobre nosotros" / "Contacto" y rellena el cargo). Sin esta función dual, T2 queda en hit rate efectivo 20% (Frente E, commit 36d5077); con ella, estimado 50-60% (validar empíricamente en Sprint 4).

Worker `research_prospect.py`. Para cada empresa con `ia_fit='fit'` y web disponible:

1. Scrapea con `httpx` la home y hasta 3 páginas internas (`/contacto`, `/servicios`, `/proyectos`, `/sobre-nosotros`, **`/equipo`, `/team`, `/about`, `/quienes-somos`** — añadidos para extracción de personas).
2. Si la home requiere JS (detectado por respuesta vacía o redirect a SPA), reintenta con `playwright`.
3. Manda el HTML extraído (texto plano, máximo 8k tokens) a Claude con este prompt:

```
Eres un investigador comercial. Acabas de leer la web de una empresa que es
un cliente potencial para una empresa de demoliciones interiores en Madrid
(DEMIN Group). Tu tarea: extraer señales útiles para que el comercial pueda
escribir un correo personalizado y relevante.

Web de: {nombre}
Contenido extraído:
{texto_web}

Devuelve JSON con esta estructura:
{
  "tipo_actividad_concreta": "...",       // qué hacen exactamente, en sus palabras
  "tamano_aparente": "muy_pequeno|pequeno|mediano|grande|incierto",
  "tipo_obra_que_hacen": ["residencial","comercial","industrial","obra_nueva","reforma","rehabilitacion"],
  "proyectos_recientes": ["..."],          // máx 3, si los mencionan
  "noticias_o_novedades": "...",          // si hay algo reciente
  "lenguaje_que_usan": "tecnico|cercano|corporativo|familiar",
  "valores_que_destacan": ["..."],
  "hooks_de_personalizacion": ["..."],     // 2-3 ganchos concretos para conectar con la propuesta de DEMIN
  "personas_extraidas": [                  // AÑADIDO 2026-05-06 (D21) — para enriquecer T2 nominal-sin-cargo
    {
      "nombre": "...",                     // nombre completo si aparece (ej. "Martin Francisco Pérez")
      "cargo_si_aparece": "...",           // cargo literal de la web (ej. "Director Técnico"); "" si no aparece
      "fuente_url": "..."                  // URL de la página dentro del scrape donde apareció
    }
  ]
}

Si no puedes extraer algún campo, deja "" o []. No inventes nunca. **`personas_extraidas`: solo personas con nombre + cargo claros en el HTML; no inventes el cargo aunque sepas el nombre.** El campo es opcional — si no hay sección "Equipo" o equivalente, devuelve `[]`.
```

El JSON se guarda en `companies.research_data`. Coste: ~$0.005 por empresa, ~5€ para 1.000 empresas. **`personas_extraidas` lo consume `find_contacts.py` (§8.5) en el paso de cruce con resultados del email finder para reclasificar nominal-sin-cargo → nominal-con-cargo en T2 (D21).**

### 8.5 Búsqueda de contactos via email finder

**Reescrito 2026-05-06 (D19, D20). Refinado 2026-05-06 tras Frente E (D21, D22).** Sustituye al §8.5 de 2026-05-04 ("Búsqueda de decisores via Hunter Domain Search"). La validación empírica de Hunter dio AMARILLO al 8% decisor estricto (commit 3c5b7a9) pero el reanálisis Frente E con criterio D20 dio **T3=80% production-ready** (commit 36d5077), lo que justifica la arquitectura híbrida por tier de D21. El antiguo `scrape_emails.py` sigue eliminado del flujo activo, salvo que Hunter indexe `info@` por sí mismo (no por scraping ad-hoc).

Worker `find_contacts.py` (renombrado desde `find_decisors_hunter.py`). Para cada `company` con `ia_fit='fit'`, llama al adapter primario `HunterAdapter` (D21) y aplica la siguiente lógica:

1. **Llama Hunter Domain Search** con el dominio extraído de `companies.web` (T2/T3) o el nombre (T1, fuzzy — Frente C dio 0% pero queda como fallback gratis).
2. **Clasifica cada email devuelto según D20** (whitelists positiva/negativa por prefijo + cargos decisor/nominal/descartado por rol — implementado en `apps/workers/shared/email_policy.py`, pendiente Sprint 4):
   - **Decisor** — cargo en {gerente, director general, CEO, jefe de obra, responsable compras, director técnico, jefe de proyectos, jefe de operaciones, director comercial, director financiero, director ejecutivo, manager con contexto operativo}. → `email_type='decisor'`.
   - **Nominal** — cargo identificable aunque NO sea decisor estricto (Engineer, Coordinator, Project Manager generic, Architect, Technician, etc.). → `email_type='nominal'`.
   - **Corporativo pequeño** — prefijo en whitelist positiva, aceptado SOLO en **T1, T3 y T4** (D20 con calibración tras Frente E: T4 sin web pero pequeñas operativamente, ver §8.5 abajo). → `email_type='corporativo_pequeno'`.
   - **Descartado** — prefijo en whitelist negativa o cargo descartado por rol (marketing, comunicaciones, RRHH, prensa, prevention specialist, internal audit, etc.).
3. **CRUCE con `research_data.personas_extraidas` (D21, paso crítico para T2)**: si Hunter devolvió un email tipo `nombre@dominio` o `n.apellido@dominio` con NOMBRE pero SIN cargo, y la empresa es **T2**, busca en `personas_extraidas` (§8.4) una persona cuyo nombre case con el del email. Si hay match con cargo identificado en la web → reclasifica como `nominal` (con cargo); si no hay match → descarta (regla A3 confirmada en sesión 2026-05-06: T2 no acepta nombre-sin-cargo). Para T1, T3 y T4 el cruce también se intenta pero el descarte por A3 no aplica (T1/T3/T4 aceptan nominal-sin-cargo como fallback).
4. **Selección y priorización (D18 + D20)**: 2-3 candidatos máximo por empresa, ordenados por `email_priority` 1..4 (1 = decisor confidence alto; 4 = corporativo_pequeño solitario). Primero por prioridad → `is_primary=true`.
5. **Fallback humano** — si la empresa es **T2** y no hay decisor ni nominal (con o sin cargo enriquecido), pasa a la cola "decisor manual" del dashboard. Razón: empresas medianas filtran `info@`, mandar ahí degrada reply rate.

**Whitelist positiva** (aceptados como `corporativo_pequeno` en T1, T3 y T4 — calibrada tras Frente E):

```
info@, contacto@, contact@, hola@, hello@, gerencia@, gestion@,
direccion@, despacho@, oficina@, administracion@, obras@,
proyectos@, comercial@
```

**Whitelist negativa global** (rechazo en cualquier tier; marca `email_type='descartado'` y NO se usa para outreach):

```
marketing@, rrhh@, prensa@, comunicacion@, comunicaciones@,
atencion@, noreply@, no-reply@, facturas@, contabilidad@,
webmaster@, soporte@, support@, ayuda@, jobs@, empleo@, trabaja@
```

La whitelist positiva, la whitelist negativa y la política tier-segmentada viven en `apps/workers/shared/email_policy.py` (pendiente Sprint 4) para que sean editables sin tocar el worker.

**Selección y priorización (D18 + D20):** se eligen 2-3 candidatos por empresa máximo (D18). El campo `contacts.email_priority` (1-4) ordena los candidatos: 1 = decisor con confidence alto del adapter primario; 4 = corporativo_pequeño en T1/T3 cuando es el único candidato. El primero por prioridad lleva `is_primary=true`. `email_source` se rellena con el adapter que devolvió el dato (`'hunter'` | `'skrapp'` | `'apollo'` | `'manual'`).

**Empresas T4 (sin web): Sprint 5 con Opción C + empresite (D21).** Hunter validó **0% hit rate en T4** sobre el sample experimental (commit 3c5b7a9, 1 falso positivo descartado en Frente E). Apollo y Skrapp también descartados durante la sesión 2026-05-06 (Lección 21 aplicada 4×). T4 representa **288 fits / 518 = 55.6% del universo accionable** (Lección 24): no se puede ignorar. La estrategia es **Opción C completa en Sprint 5**: research IA web del prospecto si la empresa publica algo + permutación de patrones email (`nombre@`, `n.apellido@`, `nombre.apellido@`) + verificación con MillionVerifier + `empresite.com`/`einforma.com` como fuente complementaria de email visible (Lección 26 — prueba manual 3/3 con muestra ruidosa, mini-experimento estructurado pendiente). El flujo LinkedIn (Lección 25) queda como segunda alternativa si Opción C resulta insuficiente.

**Empresas T1 (con web pero pequeñas): Sprint 5 con Opción C completa (D21).** Hunter dio **0% en T1 también** (commit 36d5077, único email `ylozano@` sin nombre ni cargo). El índice de Hunter no cubre estas micro-PYMEs con web — el problema NO es de criterio (D20 ya está al máximo de permisivo en T1) sino de cobertura. Para los ~118 T1 fits, Sprint 5 aplica el mismo flujo Opción C que T4 (research IA + permutación + verificación), aprovechando que sí hay web indexable.

**Si ningún adapter cubre la empresa** (T1/T3 sin nada en la whitelist positiva, T2 sin decisor ni nominal): la empresa queda con `ia_fit_reason='no_contactos_encontrados'`. T2 entra a "decisor manual" como antes; T1/T3 quedan archivadas hasta que Sprint 5 las recupere con Opción C (no se reactiva scraping web genérico para `info@` — la decisión sobre canal `info@` rascado solo se relaja a través del índice del adapter primario o de empresite/einforma, nunca scraping ad-hoc).

### 8.6 Enriquecimiento — interfaz EmailFinder

**Reescrito 2026-05-04 (D17). Revisado 2026-05-06 (D19, D20). Cerrado 2026-05-06 tras Frente E (D21).** RocketReach descartado por API Ultimate $2.484/año (D17→D19). Skrapp descartado por API Enterprise $262/mes. Apollo descartado por people endpoints gated en Free. Hunter es el único adapter viable.

Worker `enrich_emails.py` consume una interfaz abstracta `EmailFinder`. La abstracción se mantiene desde el día 1 para no acoplar los workers río abajo a un cliente concreto:

- **`HunterAdapter`** (D21) — **única implementación concreta para Sprint 4**. Encapsula las llamadas de §8.5 más cualquier extensión futura (ej. Hunter Email Finder por nombre+dominio para T2 enriquecido si `find_contacts.py` no encuentra match en `personas_extraidas`).
- **`SkrappAdapter` / `ApolloAdapter` / `RocketReachAdapter`** — descartados como adapters operativos (Lección 21 aplicada 4×). Quedan como **hooks teóricos en el código** (clases vacías que cumplen el `Protocol` y devuelven listas vacías) por si en el futuro alguno cambia su pricing/access — el coste de mantenerlos así es nulo y evita reabrir la abstracción si alguno vuelve.

La interfaz fija el contrato (métodos renombrados de `find_decisors_*` a `find_contacts_*` para reflejar la jerarquía de aceptación de D20: decisor + nominal + corporativo_pequeno):

```python
class EmailFinder(Protocol):
    def find_contacts_by_domain(self, domain: str, company_name: str) -> list[Contact]: ...
    def find_contacts_by_company(self, company_name: str, location: str) -> list[Contact]: ...
    def find_email_by_name(self, full_name: str, domain: str) -> str | None: ...
```

**Fallback final si Hunter no cubre una empresa:** depende del tier (D21).
- **T2** sin decisor, sin nominal, sin match en `personas_extraidas` → cola "decisor manual" en dashboard para Gonzalo.
- **T1 y T4** sin emails de Hunter → Sprint 5 con Opción C (research IA + permutación + verificación + empresite/einforma para T4). Mientras tanto en Sprint 4 quedan archivadas con `ia_fit_reason='no_contactos_encontrados'`.
- **T3** sin emails de Hunter (~1 de cada 5 según Frente E) → archivada igual; el 80% de cobertura ya es production-ready.

NO se reactiva scraping web genérico para `info@` — sigue siendo decisión estratégica de calidad de canal, no técnica. Para T1/T3/T4 el `info@` puede entrar al flujo SOLO si Hunter lo devuelve indexado o si Sprint 5 (Opción C) lo recupera vía empresite/einforma con verificación previa, NUNCA por scraping ad-hoc.

### 8.7 Verificación de emails

Worker `verify_emails.py`. Por cada email nuevo (provenga del adapter primario, del secundario o de la cola manual de Gonzalo):

1. Sintaxis (regex)
2. MX record del dominio (DNS lookup)
3. SMTP probe opcional (cuidado: algunos providers bloquean; fallback a aceptar si MX existe)

Marca `email_verified = true/false`.

**Defensa en profundidad:** Hunter (D21, adapter primario único) devuelve `confidence` y verificación MX/SMTP propia. `verify_emails.py` corre igualmente como salvaguardia gratis — coste cero, latencia de DNS y nada más, y captura el caso en que Hunter dé un email obsoleto (la persona dejó la empresa entre el indexado y el envío real). En Sprint 5 (Opción C, D21) `verify_emails.py` toma rol más activo: verifica los emails permutados (`nombre@`, `n.apellido@`, `nombre.apellido@`) y descarta los que no respondan SMTP, antes de insertarlos en `contacts` — sin este filtro la permutación produciría bounces masivos.

---

## 9. Sistema de envío

### 9.1 Infraestructura de correo

- **Dominio:** comprar `demingroup.es` (verificar disponibilidad en Fase 0). Si no, `demin.es` o `demingroup.com`.
- **Workspace:** Google Workspace Business Starter (~6€/buzón/mes). 3 buzones:
  - `gonzalo@demingroup.es` (display name "Gonzalo Pérez")
  - `contacto@demingroup.es` (display name "Equipo DEMIN") — para 2º remitente
  - `hola@demingroup.es` (display name "DEMIN Group") — para 3º remitente
- **DNS:** SPF, DKIM, DMARC desde el día 1. Sin esto, todo va a spam.
- **Warmup:** conectar los 3 buzones a Lemwarm (~10-15€/buzón/mes). Mínimo 2 semanas de warmup antes de enviar nada en frío.
- **Cap por buzón:** 10/día primera semana → +5/semana → tope 50/día. **Nunca pasar de 50/día por buzón.**
- **Rampa de campaña:** primera semana 20 envíos/día totales, luego incremento gradual.

### 9.2 Cadencia (la secuencia "demin_v1")

3 toques por contacto con ángulos distintos:

| Step | Día | Ángulo | Objetivo del correo |
|---|---|---|---|
| 0 | D+0 | `opening` | Conexión genuina con lo que hace la empresa + propuesta de valor (la fase cero de sus reformas) |
| 1 | D+4 | `reframe` | Re-encuadre. Caso de uso, escenario concreto que les puede resonar, o pregunta abierta. Diferente al toque anterior. |
| 2 | D+10 | `closing` | Directo y breve. "Si no es momento, ¿quién en vuestro equipo coordina demoliciones?". Honesto, sin presión. |

Si no hay respuesta tras el step 2: marcar como `cold` y programar re-engage a +90 días con ángulo `re_engage_90`.

Si en cualquier step el lead responde: detener la secuencia inmediatamente.

### 9.3 Reglas anti-spam

- Texto plano. **No HTML, no pixel de tracking, no imágenes embebidas.** Los antispam modernos los penalizan duro.
- Firma simple: nombre, cargo, web, teléfono. Sin imágenes.
- Sin enlaces de tracking. Si necesitamos saber si han abierto, lo dejamos para v2.
- Cada correo lleva pie con opt-out claro: "Si no quieres recibir más mensajes, responde STOP o díselo y dejaremos de escribirte."
- Variabilidad de envíos: no enviar a horas idénticas (jitter de ±30 min). No enviar fines de semana.
- Horario: 9:00-13:00 y 15:00-18:00 hora Madrid.

### 9.4 Auto-pausa

Worker `auto_pause.py` corre cada hora. Pausa la campaña entera si:

- Bounce rate (últimos 7 días) > **2%**
- Spam complaints > **0.1%**
- Cualquier buzón es marcado como "warning" por Gmail

Pausa = todos los `messages` con `status='scheduled'` pasan a `status='paused'`. Notificación al dashboard. Reanudar es manual.

---

## 10. Personalización con IA (redacción)

### 10.1 Pipeline de generación

Por cada `message` a redactar:

1. Carga del contacto + empresa + research_data
2. Determinar etapa (`step_index` y `angle`)
3. Cargar correos previos enviados al mismo contacto (para que no se repita)
4. Hacer retrieval del KB (5 chunks más relevantes a la empresa + ángulo)
5. Construir el prompt
6. Llamar a Claude Sonnet 4.5
7. Validación post-generación (longitud, tono, no inventos)
8. Guardar en `messages.body` + `messages.subject` con `status='drafted'`

### 10.2 Prompt de redacción (esqueleto, completar en Fase 2)

Ubicación: `apps/workers/shared/prompts/generate_email_{angle}.md`

Plantilla común (no es la plantilla del correo — es la instrucción al LLM):

```
Eres Gonzalo Pérez, responsable de DEMIN Group, una empresa pequeña de
demoliciones interiores en Madrid. Estás escribiendo un correo de prospección
en frío a una empresa concreta.

REGLAS DE TONO (no negociables):
- Directo, sin floruras, sin emojis, sin signos de exclamación.
- Profesional pero cercano, como entre profesionales que se respetan.
- Concreto: refiérete a lo que hace la empresa en concreto, no en abstracto.
- Honesto: si no sabes algo, no lo inventes.
- Aprovecha que somos pequeños como ventaja: trato directo, decisiones rápidas,
  sin intermediarios. Pero NO digas "somos pequeños" textualmente — muestra
  esa ventaja en cómo escribes.
- Máximo 130 palabras en el cuerpo (sin firma).
- Asunto: máximo 6 palabras, sin clickbait, sin "Re:" falso.

INFORMACIÓN DE DEMIN (úsala con criterio, no la copies):
{kb_chunks}

INVESTIGACIÓN DE LA EMPRESA A LA QUE ESCRIBES:
Nombre: {nombre}
Tipo concreto de actividad: {tipo_actividad_concreta}
Tipo de obra: {tipo_obra_que_hacen}
Proyectos recientes: {proyectos_recientes}
Hooks de personalización: {hooks_de_personalizacion}

CORREOS PREVIOS QUE LE HAS MANDADO (si los hay):
{correos_previos}

OBJETIVO DE ESTE CORREO ({angle}):
{objetivo_segun_angulo}

Devuelve JSON:
{
  "subject": "...",
  "body": "...",          // sin firma, la pongo yo
  "razonamiento_breve": "..."  // por qué has elegido este ángulo concreto
}
```

Por ángulo (`opening`, `reframe`, `closing`, `re_engage_60`, `re_engage_90`), un prompt distinto que rellena `{objetivo_segun_angulo}`.

**Variantes por `email_type` (regla añadida 2026-05-06 con D20, prompt pendiente Sprint 4 o 5).** El prompt de redacción debe adaptar la apertura/llamada al destinatario según el campo `contacts.email_type` del destinatario:

- `decisor` — apertura directa al rol: *"te escribo directamente como responsable de obras de [empresa]…"*. Se asume nombre y cargo conocidos.
- `nominal` — apertura suavizada al perfil: *"te escribo a ti porque encajaba con el perfil que coordina demoliciones en [empresa]…"*. Nombre conocido, cargo no claramente identificado.
- `corporativo_pequeno` — apertura impersonal pero respetuosa al equipo: *"envío esto a [empresa] porque pensaba que podría interesar a quien coordina obras en vuestro equipo…"*. Sin nombre — buzón genérico de empresa pequeña que el gerente lee directamente (D20).

El KB y el research siguen alimentando el prompt igual; la variante solo cambia la apertura/llamada al destinatario, no el cuerpo. **Implementación fijada para Sprint 4 paso 5** (§14 reorganizado tras D22 — roll-out escalonado): los 3 prompts `generate_email_{opening,reframe,closing}.md` viven en `apps/workers/shared/prompts/` con bloque condicional por `email_type`, versionados según regla 8 del Apéndice A.

### 10.3 Validación post-generación

Antes de pasar a `status='drafted'`:

- Body entre 50 y 180 palabras
- Subject entre 3 y 8 palabras
- No contiene nombres inventados (verificar contra `research_data`)
- No promete plazos ni precios (regex de "garantizamos", "en X días", "por X€")
- No usa emojis ni signos de exclamación

Si falla validación: regenerar (máximo 2 reintentos, luego marcar para revisión humana).

---

## 11. Clasificación de respuestas

### 11.1 Pipeline

Worker `poll_imap.py` corre cada 5 min. Por cada respuesta nueva:

1. Match con el `message` original por `In-Reply-To` o `References`
2. Encolar job `classify_reply`
3. Worker `classify_replies.py`:
   - Llama a Claude con el cuerpo + asunto + contexto del último correo enviado
   - Devuelve categoría + flag de opt-out + razón + acción sugerida + draft de respuesta si aplica
4. Worker `handle_actions.py`:
   - Ejecuta la acción según §11.2

### 11.2 Acciones por categoría

| Categoría | Acción automática | Notificación |
|---|---|---|
| `interesado` | Detener secuencia. Marcar para escalado. Generar draft de respuesta. | Sí, urgente, a Gonzalo |
| `pide_info` | Detener secuencia. Generar respuesta automática con dossier adaptado. **HITL: requiere aprobación.** | Sí, normal |
| `no_ahora` | Detener secuencia. Programar re-engage a +60 días con ángulo `re_engage_60`. | No |
| `no_interesado` | Detener secuencia. Programar re-engage a +90 días con ángulo `re_engage_90`. | No |
| `rebote` | Marcar email como `email_verified=false`. Buscar email alternativo si lo hay. | No |
| `fuera_oficina` | Si el OOO menciona fecha de regreso, reprogramar siguiente toque a fecha+5d. Si no, +7d. | No |
| **Opt-out explícito** (flag, transversal) | `contacts.is_optout=true`. Excluir permanentemente. Enviar acuse "Te quitamos de la lista. Disculpa las molestias." | Sí, log |

**Calibración tras KB sesión 1 (2026-04-29):** la tabla de arriba asume
que las objeciones de tipo `pide_info` se responden con dossier adaptado +
HITL. La realidad capturada en sesión 1 con Gonzalo es que solo 2 de 9
objeciones clásicas tienen respuesta validada por él. Las otras 7 escalan
a Gonzalo en seco hasta nuevo aviso. Esto significa que la cola de respuestas
en v1 será mayoritariamente HITL (~80%, no el ~30% implícito en la tabla).
Ver KB documento `objeciones`, archivo `tasks/kb_objeciones_v1.json`, y
lección 10 en `tasks/lessons.md`. La regla operativa es no rellenar gaps
con respuestas inventadas — escalar es el comportamiento correcto.

### 11.3 Detección de opt-out

El clasificador devuelve `is_explicit_optout: true` si detecta:

- Frases tipo "no me escribáis más", "quítame de la lista", "stop", "unsubscribe", "no quiero recibir nada"
- Invocación legal: "RGPD", "GDPR", "LSSI", "ARCO", "derechos", "AEPD", "denuncia"
- Tono claramente molesto + petición de cese

Lista de palabras gatillo editable desde dashboard (`settings`).

### 11.4 Re-engage

Tras 90 días sin respuesta o tras "no interesado" de hace 90 días:

- Email único con ángulo `re_engage_90`. Tono: "ha pasado un trimestre, igual algo ha cambiado por vuestro lado".
- Si tampoco responde o vuelve a decir no: archivo frío. Re-intento a +12 meses (no insistir más durante un año).
- Si dice opt-out explícito en cualquier momento: permanente.

---

## 12. Dashboard

### 12.1 Pantalla 1 — Pipeline

Vista de todos los leads (`companies` + sus contactos). Filtros por tier, ia_fit, estado de enriquecimiento, estado de campaña. Búsqueda por nombre/NIF. Ordenable por facturación, crecimiento, fecha de último contacto.

Acción: ver detalle de empresa → research_data + contactos + historial de mensajes.

### 12.2 Pantalla 2 — Cola de aprobación (HITL)

La pantalla más importante en Fase 1. Lista de `messages` con `status='drafted'`. Por cada uno:

- Resumen del lead (nombre, web, descripción corta, hook)
- Asunto editable
- Cuerpo editable
- Razonamiento del LLM ("por qué este ángulo concreto")
- Botones: ✅ aprobar | ✏️ editar+aprobar | 🔄 regenerar | ❌ rechazar+excluir

Acciones por lotes: aprobar todos, regenerar todos los rechazados.

UX: navegación con teclado (j/k para mover, a para aprobar, r para regenerar). Gonzalo tiene que poder revisar 50 drafts en 15 minutos.

### 12.3 Pantalla 3 — Bandeja de respuestas

Lista de `replies` ordenadas por urgencia: primero `interesado`, luego `pide_info`, luego el resto. Por cada respuesta:

- Correo del prospecto
- Categoría detectada por IA + razón
- Draft de respuesta sugerida (si aplica)
- Botones: aprobar respuesta | editar+aprobar | escalar a Gonzalo | archivar | reclasificar

### 12.4 Pantalla 4 — KB editor

CRUD de `kb_documents`. Por categoría (`servicios`, `icp`, `objeciones`, etc.). Editor markdown simple. Al guardar se reembedda automáticamente.

### 12.5 Pantalla 5 — Métricas

- Embudo: leads → con email → enviados → entregados → respondidos → interesados → reuniones cerradas
- Por ángulo: reply rate de `opening` vs `reframe` vs `closing`
- Por buzón: deliverability, bounce rate, spam complaints
- Por tier (T1/T2/T3/T4): conversion
- Coste por mes (envíos + IA + enriquecimiento)

### 12.6 Pantalla 6 — Configuración

- Toggle HITL ↔ autónomo
- Caps de envío por buzón
- Lista de palabras gatillo de opt-out
- Horario de envío
- Pausa de emergencia (botón rojo)

### 12.7 Auth

Supabase Auth con magic link. Lista blanca de emails (Gonzalo + colaborador). Sin contraseñas.

---

## 13. Sitio web público de DEMIN

DEMIN no tiene web. **Esto es un bloqueador para outreach** por dos razones: prospectos serios googlean al remitente antes de responder; un dominio sin web puntúa peor en filtros de spam de Gmail. Por eso construimos una landing one-pager en Fase 0, en paralelo al setup de infra y al warmup de buzones — para cuando arranquen los envíos en Fase 2, la web ya esté indexada y caché por Google.

**Nota tras KB sesión 1 (2026-04-29) — tensión a resolver con Gonzalo:**

El dossier comercial actual (página 2) afirma "años de experiencia en el
sector". La realidad operativa que Gonzalo verbalizó en KB sesión 1 es
que la empresa arranca en 2020 pero su operación independiente como
autónomo arranca en 2024 (≈2 años efectivos, con parones). El KB
(`tono`, `diferenciador`) capitaliza esta juventud como activo, no como
problema, alineado con la frase real del cliente que cerró: "la confianza
que veía en un chico joven lanzándose".

**Decisión humana pendiente:** alinear el dossier comercial con la
realidad temporal capturada en el KB, o ajustar el KB. Recomendación
del humano que validó la sesión 1 (Alberto): actualizar el dossier,
porque el KB tiene que reflejar la realidad que alimenta los correos.

**Implicación para la web pública (Bloque C):** la web NO debe afirmar
"años de experiencia" mientras la decisión esté pendiente. Posiciona
DEMIN como operación dirigida directamente por su responsable, con
trato cercano, sin cifras de antigüedad.

### 13.1 Alcance (MVP, no proyecto de diseño)

Una sola página con anchors. Tiempo de construcción objetivo: **4-6 horas con Claude Code**. Stack idéntico al dashboard (Next.js 15 + Tailwind, sin shadcn aquí), monorepo en `apps/web/`, despliegue en Vercel free tier. Coste adicional: **0€**.

Routing:
- `demingroupmadrid.com` (root, público) → `apps/web/`
- `app.demingroupmadrid.com` (auth required) → `apps/dashboard/`

### 13.2 Secciones

| Sección | Contenido | Fuente |
|---|---|---|
| Hero | Nombre + propuesta de valor en una línea ("Demoliciones interiores en Madrid. La fase cero de tu reforma, sin contratiempos.") + CTA al formulario | Plan |
| Servicios | 4-6 servicios concretos con ícono y descripción breve | Dossier original |
| Cómo trabajamos | Los 6 pasos del dossier (contacto, presupuesto, demolición, control, retirada, entrega) | Dossier original |
| Por qué nosotros | 5 valores (compromiso, limpieza, comunicación, normativa, trato) | Dossier original |
| Galería / casos | 4-8 imágenes de obras reales (antes/después si las hay) | Aporta Gonzalo |
| Contacto | Formulario (nombre, empresa, teléfono, mensaje) + datos directos (teléfono, email, redes) | Plan |
| Pie | Aviso legal mínimo + política de privacidad + cookies | Plantilla |

### 13.3 Identidad visual

Hereda del dossier comercial existente: paleta gris oscuro + blanco + un acento (a definir con Gonzalo, probablemente naranja/teja según muestra de logos del sector). Tipografía sans-serif limpia (Inter o Geist). Sin stock photography genérica — solo imágenes reales de obras de DEMIN. Si no hay material visual al inicio, mejor menos secciones de imagen que rellenar con genéricas.

### 13.4 Formulario de contacto

POST a `/api/contact` (Next.js route handler) → inserta en tabla `web_leads` de Supabase + dispara email de aviso a Gonzalo. Estos leads entran al sistema por el lado de "inbound" — visibles en el dashboard como una sección separada (no se mezclan con outbound de Sabi).

```sql
create table web_leads (
  id           uuid primary key default gen_random_uuid(),
  nombre       text,
  empresa      text,
  telefono     text,
  email        text,
  mensaje      text,
  origen       text default 'web_form',  -- 'web_form' | 'whatsapp' | 'instagram' (futuro)
  status       text default 'nuevo',
  created_at   timestamptz default now()
);
```

### 13.5 Anti-spam del formulario

Honeypot field invisible + rate limit por IP + verificación básica del email antes de enviar la notificación. Sin reCAPTCHA en v1 (fricción innecesaria con el volumen previsto).

### 13.6 SEO y trust signals mínimos

- `<title>` y `<meta description>` cuidados (palabras clave: "demoliciones interiores Madrid", "demolición controlada", "vaciado de obra")
- Schema.org `LocalBusiness` con dirección, teléfono, área de servicio
- Sitemap.xml + robots.txt
- Open Graph tags para que cuando alguien comparta el enlace se vea bien

### 13.7 Lo que NO hace la web en v1

- ❌ Blog
- ❌ Calculadora de presupuesto
- ❌ Chat en vivo
- ❌ Multiidioma
- ❌ Login de clientes / portal

Eso es v2 si tiene sentido, no antes.

---

## 14. Fases de construcción

> **Estado actual 2026-05-06:** Fase 1 abierta, Sprint 4 a punto de arrancar paso 1. Sprint 4 cruza la línea Fase 1 → Fase 2 (pasos 1-6 cierran cierre técnico de Fase 1, pasos 7-8 abren Fase 2 con roll-out productivo cap 10/día, paso 9 revisión post-Sprint según Lección 19). El plan §14 se mantiene en cuatro Fases — el cruce se documenta en cada Fase pero no se renumera.

### Fase 0 — Setup (semana 1) — ✅ CERRADA salvo Gmail OAuth (espera Fase 2)

**Infra básica:**
- [x] Comprar dominio `demingroupmadrid.com` (Namecheap, expira 29/04/2027, auto-renew ON)
- [-] ~~Crear Google Workspace con 3 buzones~~ — **sustituido**: 1 buzón `gonzalo.perez@demingroupmadrid.com` activo + warm standby día 14 (Lección 4, §19 cierre Bloque A 2026-04-29)
- [x] Configurar SPF, DKIM, DMARC en DNS — Bloque A 2026-04-29, "DNS en verde"
- [ ] Activar APIs de Gmail en Google Cloud Console + crear OAuth client — **legítimamente pendiente** Fase 2 (envío real)
- [x] Crear cuenta de Supabase + proyecto — `demin-dev` (`oribmklyxzhpqcpmqsce`) y `demin-prod` (`stxicalzpwrcjpaqdkdb`) operativos
- [x] Crear cuenta de Vercel + conectar a GitHub — `demingroupmadrid.com` desplegado 2026-05-04
- [x] Crear cuenta de Anthropic + API key — Sprint 3 consumió $3.90 reales
- [x] Decidir embeddings (Voyage o OpenAI) + crear cuenta — **Voyage** `voyage-multilingual-2`, KB indexado en BD
- [x] Conectar buzones a Lemwarm + iniciar warmup — Lemwarm Essential 29€/mes activado 2026-04-29
- [x] Inicializar repo con la estructura de §5 — `demin-group/demin-system` público (Lección 12)
- [x] Crear `.env.example` con todas las variables esperadas — `apps/workers/.env.example` + `apps/web/.env.example` versionados

**Web pública (en paralelo, §13):** ✅ Bloque C CERRADO 2026-05-04
- [x] Inicializar `apps/web/` con Next.js 15 + Tailwind
- [x] Construir landing one-pager con las 7 secciones de §13.2
- [x] Recopilar de Gonzalo 4-8 imágenes de obras reales (7 fotos procesadas, ver §19 entrada 2026-05-01)
- [x] Implementar formulario `/api/contact` + tabla `web_leads`
- [x] Aviso legal + política de privacidad + cookies (plantillas RGPD-ready)
- [x] Configurar `demingroupmadrid.com` → web (apex + www, A record + CNAME en Namecheap → Vercel). `app.demingroupmadrid.com` → dashboard pendiente de despliegue del Bloque B (dashboard).
- [x] Test de envío del formulario end-to-end (smoke E2E en producción 2026-05-04: insert en `web_leads` de demin-prod + email a Gonzalo desde `noreply@demingroupmadrid.com`)

**Contenido:**
- [x] Sesión con Gonzalo (60-90 min) para producir el contenido inicial del KB (§7.1) — sesión 1 cargada 2026-04-29 + sesión 2 enriquecimiento 2026-05-04 (commits 768b915 y 6aa9da4)
- [ ] Exportar correos reales de Gonzalo (5-10) para `kb_documents.correos_gonzalo` — **STANDBY PERMANENTE** (Lección 11): los correos archivados aportados son plantilla SaaS genérica, no voz auténtica. Doc 7 no se construye salvo que Gonzalo aporte material espontáneo distinto. Las 7 frases gatillo derivadas de las respuestas reales de prospectos sí se aplicaron a `tasks/kb_objeciones_v1.json`.
- [x] Subir Excel de Sabi y los PDFs originales a `docs/` — `docs/sabi_export.xlsx` + dossier original presentes

**Criterio de salida Fase 0:** dominio activo con web pública desplegada y formulario funcional, buzones en warmup, repo inicializado con docs, KB con contenido de Gonzalo en bruto (Markdown plano, antes de embedding).

### Fase 1 — Pipeline + KB + dashboard mínimo (semanas 2-3) — EN CURSO

**Items productivos — completados:**

- [x] Schema de BD aplicado (migrations §6) — 01-08 aplicadas en dev y prod (Sprint 1)
- [x] Worker `ingest_sabi.py` carga el Excel a `companies` con tier asignado — 5.578 NIFs únicos en dev y prod (Sprint 2 paso 1)
- [x] Worker `classify_descr.py` corre sobre los 1.733 accionables — Haiku, 0 fallbacks API tras retries, $3.90 total acumulado (Sprint 3, dev+prod 2026-05-04 → 2026-05-06)
- [x] Worker `embed_documents.py` indexa el KB — 6 docs / 27 chunks en dev y prod (Sprint 1 paso 2)
- [x] Pantalla "KB editor" funcional (CRUD) — con re-embed inline al guardar (Sprint 1 paso 4)
- [x] Auth con magic link — operativa desde Bloque B3 (pre-Sprint 1)

**Investigación previa Sprint 4 (cerrada — sesión 2026-05-06):**

- [x] Validación experimental Hunter sobre 25 empresas SABI — VEREDICTO AMARILLO 8% decisor estricto (commit 3c5b7a9)
- [x] Frente D Apollo descartado — people endpoints gated en Free (Lección 21, sin commit, rollback limpio)
- [x] Frente E reanálisis Hunter+D20 — T3=80% production-ready, T1/T2/T4 sin cobertura útil (commit 36d5077)
- [x] Decisión arquitectura híbrida por tier D21 + roll-out escalonado D22 (commit ed6f593, refactor §8 + Lecciones 24/25/26/27)

**Sprint 4 productivo — orden fijo D22 (T3 primero, T2 después).** Sprint puente Fase 1 → Fase 2: pasos 1-6 cierran Fase 1, pasos 7-8 son operativamente Fase 2 (envío real cap 10/día), paso 9 revisión post-Sprint.

- [x] **Paso 1: migration BD** — `contacts.email_source` revisado + nuevas columnas `email_type` y `email_priority` (D19, D20, §6.1). Migration `20260506120000_09_*.sql` aplicada en dev y prod 2026-05-06 (commit 8bdbf2e), verificada con 36 tests en dev (schema + aceptación + rechazo de los tres CHECKs).
- [ ] **Paso 2: `apps/workers/shared/email_policy.py`** — whitelists positiva/negativa + patrones decisor/nominal/descartado-por-rol + función de clasificación reusada del script `reanalyze_hunter_d20.py` (commit 36d5077).
- [ ] **Paso 3: `HunterAdapter`** implementación concreta de la interfaz `EmailFinder` (§8.6, D21). `SkrappAdapter`/`ApolloAdapter`/`RocketReachAdapter` como stubs vacíos cumpliendo el `Protocol`.
- [ ] **Paso 4: `find_contacts.py`** con la lógica de §8.5 + cruce con `research_data.personas_extraidas` (D21) para enriquecer T2.
- [ ] **Paso 4b: `research_prospect.py` función dual (D21)** — dossier de personalización (D10 original, alimenta §10.2) + JSON output con `personas_extraidas: [{nombre, cargo_si_aparece, fuente_url}]` para enriquecer cargos T2 (§8.4). Ejecuta sobre los `ia_fit='fit'` con web (~5€).
- [ ] **Paso 5: prompts** `generate_email_{opening,reframe,closing}.md` en `apps/workers/shared/prompts/` con bloque condicional por `email_type` (decisor/nominal/corporativo_pequeno, §10.2).
- [ ] **Paso 6: validación E2E** sobre 5 empresas T3 reales (NO las 25 del Frente C — otras 5 al azar entre los `ia_fit='fit'` de prod) en HITL completo: research → find_contacts → generate_draft → cola aprobación.
- [ ] **Paso 7: roll-out Semana 1 [cruza a Fase 2]** — solo T3 a cap 10/día con envío real Gmail API, monitoring bounce/spam/reply. Si bounce >2% o spam >0.1% en cualquier momento, parar y revisar antes de paso 8.
- [ ] **Paso 8: roll-out Semana 2-3 [Fase 2]** — añadir T2 con `personas_extraidas` enriqueciendo cargos. Validar que el hit rate efectivo sube de 20% (Frente E) a 50-60% (estimado D21). Si no sube, parar y revisar `personas_extraidas` antes de continuar.
- [ ] **Paso 9: cierre Sprint 4** — métricas reales de Semana 1+2-3, revisión post-Sprint Lección 19 (¿alguna decisión §3 invalidada? ¿§8 sigue alineado? ¿Sprint 5 con Opción C tiene suposiciones tumbadas?), entrada §19, decisión go/no-go Sprint 5.

**Items productivos transversales al Sprint 4 (no atados a un paso concreto):**

- [ ] Worker `verify_emails.py` validado — se activa al insertar el primer `contact` con email no verificado (Sprint 4 paso 4 en adelante)
- [ ] Logs y observabilidad básica
- [ ] Pantalla "Pipeline" funcional (read-only) — pre-requisito UX de Sprint 4 paso 6/7 para que Gonzalo audite leads + research + contactos

**Criterio de salida Fase 1:** lista de ~400-500 leads cualificados, con email verificado, dossier de research, listos para campaña. Dashboard muestra el pipeline. KB indexado y editable. **Estado actual 2026-05-06: contacts=0, messages=0, pantalla pipeline scaffold. Cierre técnico llega al cumplir Sprint 4 paso 6 (validación E2E sobre 5 T3 reales).**

### Fase 2 — Generación IA + envío + cola HITL (semana 4)

> **Nota:** el roll-out productivo arranca DENTRO del Sprint 4 D22 (paso 7 Semana 1 solo T3, paso 8 Semana 2-3 añadir T2). Los items abajo se reparten entre Sprint 4 (lo mínimo para el envío T3+T2: prompts §10.2, generate_draft, Gmail API + OAuth, jitter/horario/caps, cola HITL teclado-friendly, plantilla pie con opt-out, test E2E 10 leads) y Sprint 5 si se necesita ampliar (T1+T4 con Opción C). Cuando arranque Sprint 4 paso 7, los `[ ]` de abajo que no estén cubiertos se priorizan o se difieren explícitamente.

- [ ] Prompts `generate_email_{opening,reframe,closing}.md` en repo
- [ ] Worker `generate_draft.py` con retrieval del KB
- [ ] Validación post-generación
- [ ] Pantalla "Cola de aprobación" funcional con teclado-friendly
- [ ] Integración Gmail API + OAuth + envío real
- [ ] Sistema de jitter, horario, caps por buzón
- [ ] Worker `follow_ups.py` programa D+4 y D+10
- [ ] Plantilla de pie con opt-out
- [ ] Test E2E: 10 leads con drafts → revisión Gonzalo → envío real → comprobar entregados

**Criterio de salida Fase 2:** Gonzalo puede aprobar lotes de 30-50 drafts en una sesión. Los correos llegan a la bandeja del destinatario (no spam). Follow-ups se programan automáticamente.

### Fase 3 — Respuestas + métricas + autonomía (semanas 5-6)

- [ ] Worker `poll_imap.py` lee respuestas de los 3 buzones
- [ ] Worker `classify_replies.py` con prompt afinado
- [ ] Detección de opt-out + acción permanente
- [ ] Pantalla "Bandeja de respuestas" funcional
- [ ] Worker `handle_actions.py` con re-engage 60d/90d
- [ ] Pantalla "Métricas" con embudo + ángulos + buzones
- [ ] Pantalla "Configuración" con toggle HITL/autónomo
- [ ] Worker `auto_pause.py` con thresholds (bounce 2%, spam 0.1%)
- [ ] Test de fuego: 1 semana en HITL con 30-50 envíos/día
- [ ] Si todo OK: Gonzalo activa modo autónomo

**Criterio de salida Fase 3 (= criterio de éxito v1):** sistema corriendo en autónomo. Gonzalo dedica <30 min/día (revisar bandeja de respuestas + decidir sobre escalados). Al menos 1 reunión cerrada en las primeras 4 semanas autónomas.

---

## 15. Métricas y criterios de éxito

### 15.1 Por fase
Definidos al final de cada fase (§14).

### 15.2 En producción (objetivo v1)

- Reuniones cerradas: **maximizar sin techo**. Decisión humana
  (2026-04-29): el sistema persigue todas las reuniones que pueda
  cerrar; la capacidad operativa de obra (≈3 obras/mes según Gonzalo)
  es restricción aguas abajo gestionada por él (rechazar, posponer,
  subcontratar parcialmente, crecer en plantilla), no por el sistema.
  El sistema NO modula caps de envío, cadencias ni ángulos en función
  de obras absorbidas/mes.
- Reply rate global: ≥5% (benchmark sector cold B2B sin personalización: 1-2%; con personalización profunda: 5-15%)
- Bounce rate: <2% sostenido
- Spam complaints: <0.1% sostenido
- Coste total mensual operativo: <130€
- Tiempo humano de Gonzalo: <60 min/día (calibrado tras KB sesión 1).
  Razón del ajuste: con HITL amplio permanente en cola de respuestas
  (~80% de respuestas requieren aprobación), el listón original de
  <30 min/día no es realista en v1. Si en producción el tiempo
  sostenido excede 60 min/día, evaluar si el HITL puede relajarse
  selectivamente para tipos de respuesta donde Gonzalo ya tenga
  ejemplos suficientes del tono real.

---

## 16. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Dominio nuevo quemado por error en warmup | Media | Alto | Warmup externalizado (Lemwarm), 2+ semanas, rampa conservadora |
| KB pobre → correos genéricos | Alta | Alto | Sesión inicial con Gonzalo dedicada. Iteración semanal en v1. |
| Cobertura Hunter validada en 8% decisor estricto / 80% T3 con D20 / 0% T1+T4 (commits 3c5b7a9 + 36d5077) | Validada | Medio | Apollo y Skrapp también descartados (Lección 21 ×4). Mitigación arquitectónica D21: Hunter como adapter primario para T3 (production-ready) y T2 (con research IA enriquece-cargo). T1+T4 con Opción C en Sprint 5. Roll-out escalonado D22 mitiga reputacionalmente. |
| Hunter cae / rate limit / cambia pricing — sin adapter secundario operativo (D21) | Baja | Alto | Apollo, Skrapp y RocketReach descartados (Lección 21 ×4). Si Hunter cae, Sprint 4 (T3+T2) queda sin alimentar. Mitigación: la interfaz abstracta `EmailFinder` (§8.6) mantiene `SkrappAdapter`/`ApolloAdapter`/`RocketReachAdapter` como stubs vacíos por si alguno cambia su pricing en el futuro. Mientras tanto, los stubs viven en el código pero no se activan. Plan B real es activar Sprint 5 (Opción C — research IA + permutación + verificación) antes para T2/T3 también, no solo T1/T4. |
| Cobertura email finders construcción ES PYME estructuralmente baja en sector | Validada | Medio | Confirmado empíricamente: Hunter 8% decisor / 20% D20 global; Apollo y Skrapp gateados a planes pagados sin posibilidad de medir hit rate (Lección 21). Mitigación arquitectónica D21: T3 cubierto al 80% por Hunter+D20 (production-ready Sprint 4); T2 enriquecido vía research IA (Sprint 4 paso 4); T1+T4 vía Opción C en Sprint 5. Lección 22 (no escalar a plan pagado para confirmar gap estructural) y Lección 23 (D20 segmenta por tier para mitigar cobertura baja) capturan la regla operativa. |
| Tier 4 sin web — sin cobertura por email finders convencionales | Validada | Medio | Hunter, Apollo y Skrapp todos descartados. T4 representa 55.6% del universo accionable (288/518, Lección 24) — no se puede ignorar. Sprint 5 abordará T4 con Opción C (research IA + permutación + verificación) + `empresite.com`/`einforma.com` como fuente complementaria (Lección 26). Riesgo residual: si Opción C tampoco supera 30% en T4, replantear si T4 entra al embudo o se gestiona vía formulario inbound de la web pública. |
| Reply rate puede ser estructuralmente bajo en T3 pese a Hunter+D20 al 80% cobertura | Media | Alto | Cobertura ≠ respuesta. Mitigación operativa: roll-out escalonado D22 permite calibrar antes de quemar T2. **Si reply rate Semana 1 (solo T3) <3%, parar Sprint 4 paso 8** y ajustar KB / prompts / segmento de envío antes de incluir T2. Si tras 2 semanas y ajustes sigue <3%, revisar con Gonzalo si el problema es el canal (cold email B2B PYME ES) o la propuesta de valor. |
| Reply rate bajo en primer batch | Alta | Medio | Era esperable. Iteramos KB y prompts; Fase 2 es de aprendizaje. |
| Complaint > 0.1% | Baja | Alto | Auto-pausa. Revisión humana de plantillas y opt-out flow. |
| Gmail API rate limits | Baja | Medio | Caps conservadores; código con backoff exponencial. |
| Coste IA escala mal | Baja | Medio | Cap mensual configurable; alarma si >80% del cap. |
| Datos legales (RGPD/LSSI) | Media | Muy alto | Pie de opt-out claro, opt-out permanente respetado, base = interés legítimo B2B documentado. |

---

## 17. Costes mensuales estimados

| Concepto | Coste |
|---|---|
| Dominio (`demingroupmadrid.com`) | ~1€/mes (~12€/año) |
| Google Workspace (1-2 buzones)        | 6-12€ (1 buzón ahora; +1 desde día 14)   |
| Lemwarm Essential (1-2 seats)         | 29-58€ (idem; cada seat son 29€/mes)      |
| Email finder — evaluación adapters (cerrada) | **0€** (Hunter probado AMARILLO/T3-verde, Apollo y Skrapp descartados sin gasto — Frentes C/D/E 2026-05-06) |
| Email finder — adapter primario Hunter (D21) | **0€** free tier (25 búsquedas/mes) basta para T3+T2 del primer batch (~115 leads). Plan Starter ~30-45€/mes solo si se escala a más volumen tras Sprint 4 productivo |
| Email finder — régimen mantenimiento  | 0€ esperable (free tier de Hunter cubre reposiciones puntuales tras procesar el universo SABI accionable) |
| Anthropic API (uso normal) | ~20-30€ |
| Embeddings (Voyage AI) | ~2-5€ |
| Hetzner VPS CX22 | ~5€ |
| Vercel | 0€ (free tier) |
| Supabase | 0€ (free tier) |
| **Total recurrente baseline** | **~75-95€/mes** (sin adapter pagado, hasta cierre prueba comparativa Sprint 4 paso 2) |
| **Total durante procesamiento puntual del adapter primario** | **+0-45€/mes** durante ~1 mes (depende del adapter elegido y de su pricing); pico puntual absorbible dentro del techo D15 |

**Coste actual evaluación adapters: 0€** (Hunter, Apollo y Skrapp probados/descartados sin gasto). Hunter es adapter primario con free tier (D21) — 25 búsquedas/mes basta para T3+T2 del primer batch; plan Starter solo si se escala más allá. Régimen estable Sprint 4 ~75-95€/mes con free tier de Hunter para reposiciones. Sigue dentro del techo D15 (150€/mes) con margen.

**Sprint 5 (T1+T4 con Opción C, D21) añade costes adicionales** estimados +50-80€/mes para cubrir:
- MillionVerifier o equivalente para verificación de emails permutados (~$0.001/verify, 1.000 verifies → ~1€)
- Anthropic API extra para research IA en empresas con web mínima (T1, ~$0.005/empresa × 118 = ~0.6€ una vez)
- Posiblemente Phantombuster (~$60/mes) si se activa el flujo LinkedIn (Lección 25) tras evaluación operativa
- Posiblemente plan Hunter Starter (~30-45€/mes) si T4 absorbe muchas búsquedas fuzzy-by-name

A confirmar tras Sprint 4 productivo. Total estimado Sprint 5 en régimen pico: 125-175€/mes — al límite del techo D15. Palancas: posponer Phantombuster a v2, lotes mensuales del adapter, aplazar buzón warm standby.

Palancas existentes para Sprint 4 si se supera el baseline: aplazar buzón warm standby más allá del día 14 (-29€/mes), o procesar Hunter en lotes mensuales (-30 a -45€/mes durante ese mes adicional).

---

## 18. Lo que aporta Gonzalo (dependencias humanas)

Esto NO lo construye Claude Code. Necesita coordinarse con el humano para obtenerlo:

- [x] Decisión final sobre dominio (`demingroupmadrid.com` — comprado en Bloque A)
- [ ] Acceso administrativo a Workspace
- [x] Sesión de 60-90 min para producir KB inicial (§7.1) — completada en 2 partes: sesión 1 (2026-04-29, KB v1 cargado) y sesión 2 (2026-05-04, parche de objeciones + correos referencia). Decisión humana: NO habrá 3ª sesión.
- [ ] 5-10 correos reales suyos (con permiso) para entrenar tono — **STANDBY PERMANENTE** tras sesión 2 (Lección 11)
- [x] **4-8 imágenes de obras reales** (idealmente antes/después) para la web (§13.3) — 7 fotos recibidas vía WhatsApp y procesadas 2026-05-01
- [x] **Aprobación del color de acento** y estilo general de la web — implícitamente aprobado al desplegar a producción 2026-05-04
- [ ] Aprobación de drafts en Fase 2 (presencia diaria 15-30 min)
- [ ] Validación de tono y mensajes tras primer batch
- [ ] Gestión de reuniones que cierre el sistema
- [x] **Cuenta de Hunter.io operativa** (Bitwarden item `Hunter API`, cuenta `gonzalo.perez@demingroupmadrid.com`) + `apps/workers/.env.dev` con `HUNTER_API_KEY`. Validación experimental ejecutada 2026-05-06 (commit 3c5b7a9, AMARILLO 8% decisor; commit 36d5077, T3=80% con D20). **Adapter primario Sprint 4** (D21).
- [x] ~~Cuenta Skrapp.io~~ — **descartado** 2026-05-06: API gateada al plan Enterprise $262/mes (Lección 21). Cuenta nunca creada.
- [x] ~~Cuenta Apollo.io~~ — **descartado** 2026-05-06: people endpoints gated en Free, sólo `organizations/*` accesible (Lección 21). Cuenta creada y testeada con health-check (rollback de cambios sin commit).
- [x] ~~Cuenta RocketReach~~ — **descartado** 2026-05-04 (D17→D19): API gateada al plan Ultimate $2.484/año (Lección 21).

**Pendientes Sprint 5 (Opción C para T1 y T4, D21):**

- [ ] **Mini-experimento empresite.com estructurado** sobre 10 empresas T4 sin web (lectura pública, sin scraping automatizado). Tabla de cobertura: `empresa` × `email_visible_en_perfil` × `calidad_dato` (persona física vs empresa, baja registral, etc.). Decisión go/no-go para integrar empresite/einforma como fuente complementaria de Sprint 5 (Lección 26).
- [ ] **Evaluación operativa flujo LinkedIn** (Lección 25): TOS check + cuenta Phantombuster de prueba + medición de hit rate sobre 25 empresas comparable a Frente C. Solo si reply rate Sprint 4 (T2+T3) resulta insuficiente. Coste estimado: $60/mes Phantombuster + $50/mes email finder por nombre.
- [ ] **MillionVerifier u otro verificador de emails permutados** (~$0.001/verify) para Sprint 5 Opción C — alta de cuenta, alta de API key, integración con `verify_emails.py`.

---

## 19. Revisión y log de ejecución

> Esta sección se llena conforme se ejecutan las fases. Cada cambio de estado, decisión nueva, desviación o lección se documenta aquí. Si un punto del plan cambia, se actualiza arriba Y se loggea aquí.

### 2026-04-29 — Plan inicial creado

Plan v1 escrito tras conversación de scoping. Pendiente de validación humana antes de iniciar Fase 0.

### 2026-04-29 — v1.1: añadido sitio web público

Se identificó que DEMIN no tiene web. Sin web, los prospectos que googleen al remitente del correo en frío no encuentran nada → conversion penalizada y deliverability empeorada. Solución: landing one-pager construida en Fase 0 en `apps/web/`, mismo stack que el dashboard, despliegue separado en `demingroup.es`. Coste adicional 0€. Ver §13.

### 2026-05-01 — Bloque C: web pública construida (pendiente de revisión humana en local)

Landing one-pager `apps/web/` montada según el spec del Bloque C. Stack: Next.js 15.5.15 (App Router, Turbopack) + Tailwind v4 + Geist Sans (`weight: 400, 600`). Sin shadcn, sin tracking de terceros, sin librerías de iconos.

**Build limpio.** `npm run build` genera 10 rutas estáticas (`/`, `/aviso-legal`, `/privacidad`, `/cookies`, `/api/contact` dinámica, `/sitemap.xml`, `/robots.txt`, `_not-found`). Home: 4.04 kB + 127 kB First Load (uncompressed; queda holgadamente bajo 100 kB gzipped). `npm run lint` pasa sin warnings.

**Procesado de fotos.** Las 7 fotos de `uploads-raw/` se inspeccionaron visualmente. Mapeo final a `apps/web/public/obras/`:

| Origen WhatsApp | Destino | Uso |
|---|---|---|
| `08.22.02.jpeg` | `hero-boveda-ladrillo.jpg` | Hero |
| `08.21.43.jpeg` | `obra-vigas-hormigon.jpg` | Galería destacada |
| `08.22.02 (2).jpeg` | `obra-columnas-numeradas.jpg` | Galería |
| `08.22.20.jpeg` | `obra-cables-proceso.jpg` | Galería |
| `08.22.21.jpeg` | `obra-espacio-diafano.jpg` | Galería + sección Proceso |
| `08.22.02 (1).jpeg` | `obra-boveda-detalle.jpg` | Galería (sustituye a `obra-acabada-ventana.jpg` que no aparecía en ninguna foto recibida) |
| `08.21.44.jpeg` | (no se usa) | Queda en `uploads-raw/` |

Logo `LOGO DEMIN GROUP.jpg` movido a `apps/web/public/logo-demin.jpg`. Como el logo viene blanco sobre gris (`--brand`), encaja directo en hero overlay y footer; en el header (fondo blanco) se renderiza wordmark de texto en Geist en lugar del bloque gris para no romper la nav.

**Desviación documentada del spec §4.** No existía foto que encajara con la descripción `obra-acabada-ventana.jpg` ("espacio acabado/doméstico, puerta marrón a la derecha"). Tras consulta a Alberto, se sustituye por una segunda variante de bóveda de ladrillo con columna central marcada (`obra-boveda-detalle.jpg`). La OG image queda como copia temporal del hero (TODO pre-launch).

**Backend del formulario.** `/api/contact` con runtime Node, valida payload con `zod`, honeypot `website` (200 OK silencioso), inserta en `web_leads` con service role key. Rate limit pendiente — actualmente protegido solo por validación + honeypot. Nota: la tabla `web_leads` (definida en §13.4) debe estar creada en Supabase `demin-dev` y `demin-prod` antes del primer envío.

**Decisiones UX implementadas.** Hero con overlay 55%, lightbox con `<dialog>` nativo (Esc/←/→/click fuera), WhatsApp float aparece a 800 ms con color `#25D366`, cookie banner en `localStorage` (`demin-cookies-ack-v1`). Form con estados idle/submitting/success/error y mensaje de éxito que reemplaza al formulario.

**TODOs pre-launch (bloquean ir a producción, no cierran Bloque C en local):**

1. **NIF de Gonzalo** en `app/(legal)/aviso-legal/page.tsx` — LSSI 10.1. Hay placeholder visible y comentario HTML `TODO BLOQUEO PRE-LAUNCH`.
2. **Alias `contacto@demingroupmadrid.com`** creado en Workspace Admin (apunta al buzón principal). El `mailto:` ya apunta al alias para que funcione automáticamente al activarlo. `CONTACT_NOTIFICATION_EMAIL` apunta a `gonzalo.perez@demingroupmadrid.com` directamente.
3. **OG image real** (1200×630 con logo + tagline + foto). Hoy es copia simple del hero.
4. **Tabla `web_leads` aplicada** en `demin-prod` y `demin-dev`. ✅ Aplicada en B7. **GRANTs corregidos** en migración 07 (Lección 7) — sin esto el route handler devolvía 403 vía REST API.
5. **Envío de email del formulario NO implementado.** Spec §13.4 dice "POST a `/api/contact` → inserta en `web_leads` + dispara email de aviso a Gonzalo". Hoy solo se hace lo primero. Documentado en `apps/web/README.md` (sección "Detalle: CONTACT_NOTIFICATION_EMAIL"). Detalle del trabajo aparcado en el bloque PENDIENTE de abajo.

**Cerrados durante sesión 2026-05-01:**

- ✅ **Notificación de leads inbound vía Resend implementada.** Recursos completados: cuenta Resend creada, dominio `demingroupmadrid.com` verificado en region `eu-west-1`, DNS de `send.demingroupmadrid.com` apuntado a Resend, `RESEND_API_KEY` generada (en Bitwarden, item `demin-resend-api-key`). Código: `apps/web/lib/resend.ts` exporta `sendLeadNotification()`; `/api/contact/route.ts` la invoca tras INSERT exitoso en `web_leads`. Contrato cumplido: si Resend falla por cualquier motivo (timeout, 4xx, 5xx, key/destinatario ausentes, dominio no verificado) → `console.error('[resend]', ...)` y se devuelve 200 igual; el lead nunca se pierde por un fallo de notificación. Variables nuevas en `.env.example`: `RESEND_API_KEY` (queda vacía, valor real solo en `.env.local` y Vercel) y `CONTACT_FROM_EMAIL` (default `DEMIN Group <noreply@demingroupmadrid.com>`). Dependencia: `resend@^6.12.2` añadida a `apps/web/package.json`.
- ✅ **Remitente final: dominio raíz (no subdominio).** Tras smoke test del envío real, el `CONTACT_FROM_EMAIL` definitivo es `DEMIN Group <noreply@demingroupmadrid.com>` (no `@send.demingroupmadrid.com`). Motivo: la API key de Resend está restringida al dominio raíz `demingroupmadrid.com`; enviar desde el subdominio devolvía `403 — API key not authorized to send emails from X`. La reputación de envío sigue aislada del Workspace de Gonzalo porque los DNS records de Resend (SPF/DKIM/return-path) viven en `send.demingroupmadrid.com`. Capturado como sub-regla en Lección 8.

Cierre del bloque queda **pendiente de revisión humana en local** (`npm run dev` + check visual + Lighthouse mobile real). Hasta entonces, no se marcan los items de Fase 0 §14 ("Web pública") como `[x]`.

### 2026-04-29 — Cierre Bloque A

- **Dominio:** `demingroupmadrid.com` (Namecheap, expira 29/04/2027, auto-renew ON).
- **Workspace:** Business Starter + 1 buzón activo `gonzalo.perez@demingroupmadrid.com` con display "Gonzalo Pérez". 2FA por SMS activado.
- **DNS:** SPF + DKIM + DMARC + MX en verde. CTD (Custom Tracking Domain) explícitamente NO se configura — justificación en `tasks/lessons.md` Lección 5.
- **Postmaster Tools** verificado para el dominio.
- **Cuentas creadas:** Anthropic ($25 créditos), Voyage AI (free tier), Supabase (2 proyectos: `demin-prod` y `demin-dev`), Vercel Hobby, GitHub `demin-group/demin-system` privado. Credenciales en Bitwarden, no en repo.
- **Lemwarm Essential** 29€/mes activado, warmup arrancado el 2026-04-29.
- **Decisiones operativas Bloque A** ya capturadas en `tasks/lessons.md` Lección 4: 1 buzón + warm standby día 14, cadencia D+0/D+12/D+30, caps 10 → +5/sem → 40, Postmaster Tools como monitor oficial.
- **TODO conocido pre-Fase 2:** `docs/dossier_demin.pdf` referencia el dominio antiguo (`demolicionesdemingroup.com`) y el gmail antiguo (`demin.groupmadrid@gmail.com`). Bloqueante de inicio de cadencia: regenerar el dossier con la identidad nueva antes de Fase 2.

### 2026-04-29 — KB sesión 1 cargada y plan calibrado

Cargados 6 documentos del KB inicial (servicios, icp, objeciones,
casos_exito, tono, diferenciador) en `kb_documents` de Supabase. Embedding
diferido a Fase 1: `kb_chunks` queda vacío hasta que se construya el worker
`apps/workers/kb/embed_documents.py` en Fase 1. Cuando se implemente, el
worker procesa todas las filas en `kb_documents` que no tengan chunks
asociados — la carga de hoy queda lista para iterar. Doc 7
(`correos_gonzalo`) en standby permanente (depende de aporte espontáneo
de Gonzalo).

Ediciones derivadas aplicadas a este documento: §1.2 (sweet spot 5k-100k),
§1.3 (calibración ICP + sectores excluidos), §11.2 (HITL amplio
permanente), §15.2 (maximizar reuniones sin techo, <60 min/día), §13
(tensión "años de experiencia" vs. realidad temporal).

Decisión operativa registrada: NO habrá 2ª ronda de captura con Gonzalo.
KB v1 cierra con material de sesión 1. Gaps documentados en
`tasks/gaps_conocidos_kb_v1.md` para trazabilidad y por si en algún
momento Gonzalo aporta material por iniciativa propia, pero NO son un
to-do activo del proyecto.

Nuevas lecciones en `tasks/lessons.md`: 9 (KB manda sobre plan en
divergencias) y 10 (no rellenar gaps con respuestas inventadas).

Material de soporte añadido al repo: `tasks/gaps_conocidos_kb_v1.md`,
`tasks/kb_objeciones_v1.json`. Pendiente para Fase 1: implementar
`apps/workers/kb/embed_documents.py` (cliente Voyage `voyage-multilingual-2`,
chunking ~500 tokens overlap 50, idempotente — ver Lección 3 para selección
de modelo y plan §7.2 para pipeline).

### 2026-05-04 — KB sesión 2: enriquecimiento tras revisión de correos reales

Revisión de 10 correos reales de Gonzalo (cold outreach previo al sistema
DEMIN + respuestas de prospectos). Hallazgos derivados aplicados al repo:

- Patch a `tasks/kb_objeciones_v1.json`: ampliada `frases_gatillo` de
  `obj_no_ahora_amable` con 7 variantes textuales reales; añadida nueva
  categoría `obj_interesado_condicional` para zona gris entre interesado
  puro y pide_info; añadida nueva acción `escalar_a_gonzalo_con_contexto`
  a `tabla_acciones`. Total objeciones en JSON: 9 → 10.
- Creado `tasks/correos_referencia_v1.md` — referencia interna del
  proyecto, NO contenido de KB. Archivo histórico de las 2 plantillas
  genéricas que Gonzalo usaba antes (referencia negativa) + patrones de
  respuesta reales de prospectos (insumo para validar clasificador en
  Fase 3).
- Añadida lección 11 a `tasks/lessons.md`: cuando los correos archivados
  de un humano son plantilla SaaS genérica, no son su voz auténtica — la
  entrevista verbalizada deliberadamente manda como fuente de tono.

NO se ha modificado el contenido cargado en `kb_documents` en sesión 1.
NO se ha construido el doc 7 (`correos_gonzalo`) — el material disponible
es plantilla genérica, no voz auténtica de Gonzalo. Doc 7 sigue en
standby permanente.

Decisión operativa confirmada: el sistema NUNCA copia plantillas en los
correos generados. Cada correo es redacción IA completa, personalizada
al prospecto, alimentada por el KB y por el research previo (decisión D8
del plan §3). Las plantillas archivadas de Gonzalo son referencia
negativa, no modelo a replicar.

### 2026-05-04 — Cierre Bloque C: web pública en producción

**Estado:** `https://demingroupmadrid.com` sirve la landing one-pager construida en sesiones anteriores. HTTPS (Let's Encrypt automático vía Vercel). `www.demingroupmadrid.com` redirige al apex. Bloque C cerrado.

**Vercel.** Proyecto `demin-web` en cuenta Hobby de `gonzalo.perez@demingroupmadrid.com`. Root directory `apps/web/`, framework Next.js detectado, build OK. 6 env vars en scope `Production` apuntando a `demin-prod`:

| Variable | Valor / origen |
|---|---|
| `NEXT_PUBLIC_SITE_URL` | `https://demingroupmadrid.com` |
| `NEXT_PUBLIC_SUPABASE_URL` | URL del proyecto `demin-prod` |
| `SUPABASE_SERVICE_ROLE_KEY` | secret key formato nuevo (`sb_secret_...`) de `demin-prod` |
| `RESEND_API_KEY` | API key Resend (dominio `demingroupmadrid.com` verificado) |
| `CONTACT_FROM_EMAIL` | `DEMIN Group <noreply@demingroupmadrid.com>` |
| `CONTACT_NOTIFICATION_EMAIL` | `gonzalo.perez@demingroupmadrid.com` |

Justificación de Production-only (no Preview/Development): las credenciales apuntan a infra real; activar Preview con los mismos valores haría que cualquier branch deploy escribiera leads reales en `web_leads` de prod y disparara emails reales desde URLs `*.vercel.app`. Capturado como Lección 14.

**GitHub.** Repo `demin-group/demin-system` pasó de privado a público durante el deploy. Motivo: Vercel Hobby no permite conectar repos privados de GitHub Organizations; la única alternativa gratis era hacerlo público (la otra sería migrar el repo a una cuenta personal). Decisión: público es seguro porque las credenciales viven exclusivamente en `.env.local` (gitignored) y en variables de entorno de Vercel; el repo nunca contuvo secretos en commits. Capturado como Lección 12.

**DNS Namecheap.** Registros borrados:
- URL Redirect `@` → parking de Namecheap.
- CNAME `www` → `parkingpage.namecheap.com`.

Registros añadidos:
- A Record `@` → `216.198.79.1` (IP de Vercel).
- CNAME `www` → `cname.vercel-dns.com`.

Resto de registros DNS intactos: SPF/DKIM/DMARC/MX de Workspace de Gonzalo + DNS de Resend (`send.demingroupmadrid.com`). Coordinación de DNS y validación con `dnschecker.org` antes de pulsar Refresh en Vercel capturada como Lección 13.

**Legal cerrado.** Aviso legal con NIF `06619073H` de Gonzalo Pérez Sánchez-Marín (LSSI 10.1 completo). Política de privacidad ampliada con sección 5 (Destinatarios y encargados de tratamiento): Supabase Inc. (`eu-west-1`, Fráncfort), Resend Inc. (`eu-west-1`, Dublín), Vercel Inc. (CDN global con presencia UE). Decisión editorial: la sección dice "el almacenamiento de los datos del formulario se realiza en la Unión Europea" en lugar de "no se realizan transferencias internacionales fuera del EEE", porque el CDN global de Vercel haría falsa esta segunda afirmación. Política de cookies sin cambios (solo técnicas necesarias, sin tracking de terceros).

**Assets visuales generados.** Script `apps/web/scripts/generate-assets.mjs` (ejecutable con `npm run generate-assets`) usa `sharp` (dep transitiva de Next 15, no añadida explícitamente) para producir:

- `public/favicon.ico` (32×32, ~1.3 KB, formato ICO con PNG embebido)
- `app/icon.png` (192×192, ~20 KB) y `app/apple-icon.png` (180×180, ~18 KB) — convención App Router de Next
- `public/og-image.jpg` (1200×630, 152 KB, foto hero `obras/hero-boveda-ladrillo.jpg` + overlay negro 55% + logo + claim "La fase cero de tu reforma")

`metadata.openGraph` y `metadata.twitter` en `app/layout.tsx` apuntan a `/og-image.jpg` con `width: 1200` / `height: 630`. Twitter card sin `creator`/`site` (DEMIN no tiene cuenta en X).

**Smoke test E2E en producción exitoso.** Submit del formulario en `demingroupmadrid.com` → fila insertada en `web_leads` de `demin-prod` + email de notificación a `gonzalo.perez@demingroupmadrid.com` desde `noreply@demingroupmadrid.com` con asunto "Nuevo lead — ...". Tiempo total ~2s. Fila de prueba "Alberto - SMOKE TEST PROD" pendiente de borrado en próxima sesión técnica.

**TODOs post-launch (no bloqueantes, ninguno cierra el Bloque C):**

- [ ] Borrar fila de prueba "Alberto - SMOKE TEST PROD" en `web_leads` de `demin-prod` (1 fila).
- [ ] Verificar dominio `demingroupmadrid.com` en Google Search Console y enviar `sitemap.xml`.
- [ ] Pedir a Gonzalo logo en negro sobre transparente para uso en headers claros (actualmente el header renderiza wordmark Geist Sans en lugar del bloque gris del logo, decisión documentada en entrada 2026-05-01 de §19).
- [ ] Rotar `RESEND_API_KEY` si en algún momento la API key actual se ha expuesto en canal no seguro (precaución estándar). La rotación durante la sesión ya se hizo una vez.

**Lecciones nuevas registradas en `tasks/lessons.md`:** 12 (GitHub privado vs Vercel Pro), 13 (coordinación DNS Vercel/Namecheap), 14 (scope Production-only en Vercel), 15 (nombres exactos de env vars: `NEXT_PUBLIC_SUPABASE_URL` ≠ `SUPABASE_URL`).

### 2026-05-04 — Fase 1 Sprint 1 paso 2: KB embebido en dev y prod

`apps/workers/kb/embed_documents.py` implementado y aplicado contra los dos entornos. Pipeline: chunking por chars (~2000 con overlap 200, respeta cierres de párrafo `\n\n` hasta 300 chars antes del corte) → Voyage `voyage-multilingual-2` (1024 dim, `input_type="document"`) → `kb_chunks` con `cast(:embedding as vector)` ANSI (la sintaxis `:bind::vector` colisiona con SQLAlchemy text(), bug documentado en el código).

**Estado tras la aplicación:**

| entorno | kb_documents | kb_chunks |
|---|---|---|
| `demin-dev` | 6 (replicados desde prod vía `seed_kb_dev.py`) | 27 |
| `demin-prod` | 6 (cargados en sesión 1 + sesión 2 patch) | 27 |

Distribución por categoría idéntica en ambos: `casos_exito` 5, `diferenciador` 5, `icp` 4, `objeciones` 4, `servicios` 3, `tono` 6.

**Bugs resueltos durante la implementación:**

1. **Cast pgvector incompatible con `:bind`** — el operador PostgreSQL `::cast` colisiona con la sintaxis de bind de SQLAlchemy text(). Solución: `cast(:embedding as vector)` ANSI. Aplica también al smoke retrieval.
2. **Voyage free tier 3 RPM** — el cap del backoff de tenacity en `shared/llm.py` (1+2+4=7s) no alcanzaba la ventana de 20s del rate limit. Solución sin tocar `shared/llm.py`: añadir `INTER_BATCH_SLEEP_S=30` + `INITIAL_WARMUP_SLEEP_S=25` en el worker, parametrizadas para bajar a 0 cuando se añada payment method en Voyage.
3. **`ivfflat` con bajo volumen y `probes=1`** — el índice vector(1024) creado sin filas en la migration 04 quedó con ~100 lists vacíos; con probes=1 (default), retrieval devolvía 0 rows pese a tener 27 chunks. Solución: `SET LOCAL ivfflat.probes = 10` antes de cada SELECT en el retrieval. Cuando el volumen pase de ~1000 chunks (Fase 2 con prospectos), reindexar con `lists` óptimo y revisar probes.

**Pivot técnico aplicado en `shared/llm.py`:** parámetro nuevo `input_type: Literal["document","query"]` en `embed()`. Embeddings asimétricos del SDK Voyage: `"document"` para indexar (`embed_documents`), `"query"` para recuperar (`smoke_kb_retrieval` y futuros workers que consulten el KB en Fase 2). Mezclar ambos roles degrada retrieval — son representaciones distintas.

**Smoke retrieval recalibrado** tras VEREDICTO AMARILLO inicial. Criterio nuevo basado en presencia de signals contextuales (palabras-clave/cifras/términos extraídos leyendo los 6 docs reales del KB), no en categorías intuidas a priori. Output auditable: preview de 400 chars del top-1 + signals matched, sin necesidad de abrir BD. **VERDE 3/3** con threshold ≥2 signals: q1 (constructora pequeña Madrid) → diferenciador (4 signals), q2 (precio demolición 200 m²) → casos_éxito (3 signals), q3 (coordinar con arquitectos) → servicios (6 signals). Distancias top-1 entre 0.64 y 0.71 (RAG discrimina). Aprendizaje sobre cómo se diseña un criterio de smoke capturado como Lección 17.

**Pendiente para cerrar Sprint 1:** paso 3 (ya cubierto por el smoke verde) y paso 4 (KB editor en dashboard, Bloque B). Sprint 1 NO se cierra hasta que el dashboard tenga la pantalla CRUD del KB.

**Lecciones nuevas registradas en `tasks/lessons.md`:** 16 (config se adapta a la convención del repo, no al revés — capturada en Sprint 1 paso 1), 17 (criterio de validación de smokes se diseña leyendo el contenido real, no a priori).

### 2026-05-04 — Cierre Sprint 1: cimientos + KB embebido + KB editor

Sprint 1 de la Fase 1 cerrado. Quedan disponibles los cuatro cimientos sobre los que se monta el resto de la fase: (1) `apps/workers/shared/` con config dual dev/prod, conexión SQLAlchemy 2.0 + psycopg3, cliente LLM con `MODEL_FOR_TASK` + Voyage asimétrico + retries; (2) KB embebido en ambos entornos (6 docs / 27 chunks) con smoke retrieval VERDE 3/3 y criterio recalibrado; (3) pantalla `/kb` en el dashboard con CRUD completo y re-embed inline al guardar (Node runtime, `maxDuration=60`, fetch directo a Voyage REST), validada manualmente en browser por Gonzalo + smoke E2E backend; (4) migration 08 que añade `kb_documents.embeddings_updated_at` con backfill `now()` para los 6 docs ya indexados.

**Mecanismo de re-embed elegido (Sprint 1 paso 4):** inline en Server Action / Route Handler del dashboard, con runtime Node y `maxDuration=60`. Descartadas (a) cola de jobs en Postgres (requería tocar `apps/workers/`, fuera de scope), (b) Edge Function (reescribir el chunker en Deno), (c) webhook a worker (no hay VPS aún). Justificado por: stack Node ya tiene `fetch` y `supabase-js`, sin infra nueva, feedback inmediato en UI, cabe en Vercel Hobby.

**14 commits del Sprint 1 (en orden cronológico):**

| paso | hash | mensaje |
|---|---|---|
| 1 | `b1dd6f1` | feat(workers/shared): config con pydantic-settings y selector dev/prod |
| 1 | `df4fb13` | feat(workers/shared): db con sqlalchemy 2.0 + psycopg3 |
| 1 | `011a418` | feat(workers/shared): llm con MODEL_FOR_TASK + voyage embed + retries |
| 1 | `e10c504` | test(workers): smoke script para validar shared/ |
| 2 | `0d6f215` | feat(workers/scripts): seed_kb_dev replica kb_documents prod -> dev |
| 2 | `f2ab698` | feat(workers/kb): embed_documents con chunking por chars + Voyage batch |
| 2 | `de3bc77` | feat(workers/shared): embed acepta input_type document/query asimetrico |
| 2 | `1545de9` | test(workers): smoke_kb_retrieval recalibrado con criterio de utilidad |
| 2 | `349fb96` | chore(workers): apply embeddings a prod (kb_chunks 0 -> 27) |
| 4 | `8e02b27` | feat(infra): migration 08 — kb_documents.embeddings_updated_at + backfill |
| 4 | `c75f28c` | feat(dashboard/lib): chunker + voyage + reembed + admin client para KB editor |
| 4 | `79da264` | feat(dashboard/api): rutas CRUD de kb_documents con reembed inline |
| 4 | `8b6fc77` | feat(dashboard/kb): UI editor con lista, edicion inline y eliminacion |
| 4 | `6dba553` | chore(dashboard): VOYAGE env + tsx/dotenv devDeps + smoke E2E del KB |

(El paso 3 — aplicar embeddings a prod — quedó cubierto por `349fb96` dentro del paso 2; no generó commit propio.)

**Pendiente para Sprint 2 (ingesta SABI, sesión nueva):**

- [ ] Worker `ingest_sabi.py` carga el Excel (5.619 filas × 19 columnas, ya en `docs/sabi_madrid_demoliciones.xlsx`) a `companies` con tier asignado según §8.2.
- [ ] Worker `classify_descr.py` con Claude Haiku sobre los ~1.737 con descripción válida (~2€).
- [ ] Worker `research_prospect.py` sobre los `ia_fit='fit'` con web search (~5€).
- [ ] Worker `scrape_emails.py` sobre los mismos.
- [ ] Worker `apollo_enrich.py` para Tier 4 (decisor sin email tras scrape).
- [ ] Worker `verify_emails.py` validado contra MillionVerifier.
- [ ] Pantalla `/pipeline` (read-only) en el dashboard.

Fase 1 NO se cierra hasta que el Sprint 2 entregue la lista cualificada de ~400-500 leads (criterio de salida §14).

### 2026-05-04 — Refactor a modelo híbrido SABI-first + Hunter como email finder

**Problema detectado.** El plan original §8 (`scrape_emails` desde web genérico + `apollo_enrich` para Tier 4 + `verify`) no encaja con la realidad de prospección B2B España: (a) los emails `info@` y `contacto@` rascados de la web tienen reply rate sostenidamente bajo en cold outreach por ser buzones genéricos no monitorizados por decisores, (b) Apollo tiene cobertura mediocre en PYME construcción Madrid (sector poco indexado en bases anglo), (c) el modelo company-first puro de SABI sin búsqueda de decisores reales obliga a redactar correos a destinatarios sin nombre, lo que degrada personalización y choca con el principio de D8 (redacción IA completa por correo, no plantillas).

**Discusión arquitectónica.** Evaluadas tres opciones:

| Opción | Veredicto |
|---|---|
| **LinkedIn outreach automatizado** (LinkedIn Sales Navigator + InMail) | Descartado. Riesgo legal (TOS de LinkedIn prohíbe automatización), riesgo de ban del perfil de Gonzalo, y ya estaba fuera de §2.2 anti-feature-creep desde el plan inicial. |
| **ExtractorLead** (modelo de filtros generales tipo "constructoras Madrid 1M-5M€") | No encaja con flujo SABI-first. SABI ya entrega el universo filtrado por CNAE + facturación + provincia con datos contables verificables. ExtractorLead duplicaría el universo desde otra fuente sin mejorar calidad. Apuntado como fuente potencial de descubrimiento de leads nuevos cuando se agote SABI (no a corto plazo: 1.733 accionables dan para varios meses de outreach a cap 40/día). |
| **Hunter.io Domain Search por dominio** | Encaja exactamente con flujo SABI-first: SABI da dominio, Hunter da decisores reales del dominio. Cobertura España PYME construcción incierta hasta validación empírica — riesgo asumido y mitigado con `RocketReachAdapter` de respaldo (D17). |

**Decisión final (D16, D17, D18).** SABI sigue siendo universo de empresas (5.578 cargadas tras dedup, ver Lección 18). Para cada empresa con `ia_fit='fit'`, Hunter Domain Search devuelve 2-3 decisores reales (D18), filtrados por cargo relevante (gerente, jefe de obra, responsable compras). Interfaz `EmailFinder` abstracta desde el día 1 con `HunterAdapter` activo y `RocketReachAdapter` inactivo de respaldo (D17), lo que permite swap sin refactor si Hunter falla. ExtractorLead queda apuntado para v2.

**Impacto en el plan:**

- §2.2 — añadido bullet "DEMIN solo usa email — sin teléfono en `contacts`, dashboard ni datos a Gonzalo" para zanjar la discusión sobre canales adicionales.
- §3 — D7 marcada SUPERSEDED por D17. Añadidas D16/D17/D18.
- §4 — fila "Enriquecimiento de decisores | Apollo.io API plan Basic" sustituida por dos filas (Hunter primario + RocketReach secundario).
- §6.1 — `contacts.email_source` CHECK ampliado a `('sabi','web_scrape','apollo','hunter','rocketreach','manual')`. Pendiente migration en Sprint 4.
- §8 — refactor mayor: §8.5 nuevo (Hunter Domain Search), §8.6 reescrito (interfaz `EmailFinder` + adapters), §8.7 verificación (renombrado desde §8.6 antiguo). El antiguo §8.5 (`scrape_emails`) eliminado del flujo activo; los stubs físicos `apps/workers/pipeline/scrape_emails.py` y `apollo_enrich.py` permanecen en el repo pero sin referencia desde el plan.
- §14 Fase 1 — Sprint 4 pasa de "scrape_emails + Apollo + verify" a "find_decisors_hunter + enrich_emails (interfaz abstracta) + verify_emails". Sprint 3 (classify_descr) sin cambios.
- §16 — riesgo Apollo eliminado; añadidos riesgo Hunter (cobertura PYME) y riesgo Hunter (caída/pricing).
- §17 — Apollo Basic (45€/mes) eliminado; Hunter dividido en validación (free tier) + procesamiento puntual (Starter 30-45€/mes durante 1-2 meses) + mantenimiento (free tier). Total recurrente ~110-130€/mes post-procesamiento, dentro del techo D15.
- §18 — añadida dependencia humana "Cuenta Hunter.io + API key + .env actualizados".

**Lección capturada:** Lección 19 en `tasks/lessons.md` — al cerrar cada Sprint, antes de arrancar el siguiente, revisar §8/§14 del plan contra lo aprendido y las decisiones acumuladas. Si hay desfase, refactor de plan ANTES de código. Aplicado aquí post-Sprint 2 paso 1 cuando el desfase debió detectarse al cierre de Sprint 1.

### 2026-05-06 — Cierre Sprint 3: classify_descr en dev y prod

`apps/workers/pipeline/classify_descr.py` aplicado a las 1.733 empresas accionables T1-T4 en ambos entornos. Worker idempotente (filtro `ia_fit='pendiente'`) con ThreadPoolExecutor configurable, validación post-LLM tolerante a code fences, fallback a `dudoso` con `ia_fit_reason` explicando el fallo si el LLM da output inválido o si la API falla tras retries de tenacity. Prompt versionado en `shared/prompts/classify_fit.md` (regla 8) recoge §8.3 + las 3 exclusiones operativas de Gonzalo (Lección 9 punto 3): obras públicas, demoliciones de fachadas, plantilla > 20 personas.

**Distribución final (1.733 accionables, ambos entornos):**

| categoría | dev | prod |
|---|---|---|
| `fit` | 520 (30.0%) | 518 (29.9%) |
| `no_fit` | 776 (44.8%) | 780 (45.0%) |
| `dudoso` | 437 (25.2%) | 435 (25.1%) |
| pendiente | 0 | 0 |
| fallback API | 0 | 0 |

Diferencia inter-entorno <0.2pp por categoría — Haiku 4.5 da resultados consistentes contra el mismo prompt sobre el mismo universo. Distribución sana por criterio del smoke (3 categorías presentes, ningún extremo, fallbacks API a cero tras retries).

**Coste real:** $3.90 USD acumulado (cap configurado a $5). Plan §8.3 estimaba $2 — la desviación viene de los reintentos de las filas que cayeron por `RateLimitError 429` durante la primera pasada en dev del 2026-05-04 (8 workers paralelos saturaron el rate limit del tier inicial; los retries con 2 workers funcionaron limpios). El cap no se alcanzó pero queda como dato calibrado para futuras estimaciones.

**Calibración operativa adquirida:**

- Concurrencia segura para Anthropic en este tier de cuenta: **2 workers paralelos**. Con 8 workers la primera pasada del 2026-05-04 generó 506 RateLimitError 429 sobre 1.680 (30% fallback). Con 2 workers todas las pasadas posteriores (156 dev + 1.733 prod + 19 retries) terminaron con 0 errores API. Tiempo de procesamiento aceptable: ~33 min para 1.733 con 2 workers.
- Tiempo de respuesta promedio Haiku en este tier: ~1.1s por llamada con prompt de ~860 tokens input + ~50 tokens output.

**5 commits del Sprint 3 (en orden cronológico):**

| hash | mensaje |
|---|---|
| `74a459a` | feat(workers/pipeline): classify_descr.py + prompt classify_fit.md (smoke verde en dev, full run pendiente por inestabilidad Anthropic 2026-05-04) |
| `9cddde4` | docs(tasks): cierre Sprint 3 + revisión post-Sprint según Lección 19 |

(El cierre cuenta como un commit añadido a este §19; el hash exacto se rellena tras crear el commit final.)

#### Revisión de plan post-Sprint (trigger Lección 19)

**1. ¿Hay alguna decisión §3 invalidada por lo aprendido en Sprint 3?**

No. Las decisiones D1-D18 siguen vigentes. La D6 (filtrado por reglas tier T1-T4 + clasificador IA por descripción) se confirma con datos reales: el clasificador IA es necesario y útil (descarta 44.8% del universo accionable que no encaja en el ICP de DEMIN). La D14 (aprendizaje manual en v1) se mantiene: las 437 dudosos de prod son candidatos a revisión humana en futuras sesiones con Gonzalo, no a re-clasificación automática.

**2. ¿§8 sigue alineado con la realidad o necesita refactor?**

Alineado en lo esencial. Tres ajustes menores que NO bloquean Sprint 4:

- §8.3 menciona "1.737 accionables" — el universo real tras el dedup SABI (Lección 18) son **1.733**. La cifra 1.737 sigue mencionada en §8.2 como salida de las reglas de tier sobre el Excel pre-dedup. Coherente, pero conviene unificar en una próxima pasada.
- §8.3 estima coste de Haiku en $0.001 × 1.737 = ~$2 — el coste real fue $3.90 (factor 2x) por reintentos de rate limits. El plan está dentro del techo D15 con margen pero la estimación literal está infraponderada. Conviene anotar "$2-4 con reintentos" en la próxima sesión que toque §8.3.
- §8.5 (Hunter Domain Search) planeaba procesar "~1.000 empresas SABI accionables" para dimensionar el plan Hunter Starter. El número real de `ia_fit='fit'` con web es **518 en prod**, ~la mitad de lo asumido. Ver punto 3 abajo.

**3. ¿Sprint 4 (find_decisors_hunter + enrich_emails) tiene suposiciones tumbadas por lo visto en Sprint 3?**

Una suposición a revisar antes de Sprint 4 — NO bloqueante, pero relevante para el dimensionamiento:

- **El universo `ia_fit='fit'` con dominio web es ~518, no ~1.000.** El plan §17 dimensionó Hunter Starter a 30-45€/mes durante 1-2 meses para procesar "~1.000 empresas". Con 518 empresas, la free tier de Hunter (25 búsquedas/mes) tarda ~21 meses en cubrirlas y el Starter (típicamente 500 búsquedas/mes) las cubre en **1 mes** (no 1-2). Esto reduce el coste total puntual del procesamiento de Hunter de 60-90€ a 30-45€ (1 mes), y abre la posibilidad de que la free tier baste si el procesamiento se planifica en 2 lotes mensuales. Decisión a tomar antes de comprometer Starter.
- **Los 437 dudosos** (con descripción ambigua o tautológica) NO entran al pipeline de Hunter por el filtro `ia_fit='fit'`. Son leads potencialmente perdidos. Tres opciones: (a) ignorar, (b) revisar con Sonnet 4.6 para mejor discriminación (coste ~$10), (c) muestrear manualmente con Gonzalo. Decisión humana, no urgente para Sprint 4.
- **No hay suposiciones tumbadas que invaliden la arquitectura de Sprint 4.** La interfaz `EmailFinder` + `HunterAdapter` + `RocketReachAdapter` sigue siendo el diseño correcto. Solo cambia el dimensionamiento de coste/calendario.

**Veredicto:** No se requiere refactor de plan antes de Sprint 4. Se anotan los dos ajustes menores (1.737→1.733 y "~1.000"→518) para incorporar en la próxima sesión que toque el §8 o el §17.

### 2026-05-06 — Hunter AMARILLO + RocketReach descartado + nueva política de emails por tier + pivote a Skrapp/Apollo

Tras cerrar Sprint 3, la validación experimental de Hunter sobre 25 empresas SABI (5/5/5/10 por tier, sample diverso por localidad y descripción, lectura sólo de demin-prod) terminó con **VEREDICTO AMARILLO al 8% hit rate decisor** (commit 3c5b7a9). Por tier: T1=0% (5 empresas), T2=20% (1 de 5), T3=20% (1 de 5), T4=0% (10 sin web; 1 falso positivo Hunter mapeando "ONES" a "ACER"). Cuando Hunter cubría, los cargos devueltos eran exactamente decisores relevantes (Director Técnico, Project Manager, Director of Procurement) con confidence 96-99 — el problema no era ruido sino cobertura del índice. Los 8% quedan muy por debajo del threshold §16 (30%) que justificaba comprometer plan Starter pagado.

**RocketReach descartado.** El plan original (D17) lo apuntaba como adapter secundario inactivo. Verificación 2026-05-06: la API de RocketReach NO está disponible en planes inferiores a Ultimate ($2.484/año, ~207€/mes), excediendo el techo D15 (150€/mes) por sí solo. No tiene sentido mantenerlo como respaldo si activarlo nos saca del presupuesto. Decisión D19 lo descarta y captura la regla en Lección 21: validar pricing y disponibilidad de API en free tier ANTES de fijar proveedor en el plan.

**Política nueva de aceptación de emails por tier (D20).** El criterio "solo decisor estricto vale" (lectura inicial de D18) resulta demasiado restrictivo en B2B España PYME. Inspección manual de los 9 casos donde Hunter devolvía emails sin cargo en el sample reveló patrón claro: empresas T1 (1k-5k k€) y T3 (0.5k-1k k€), microempresas o muy pequeñas, tienen `info@`, `contacto@` y `gerencia@` leídos directamente por el gerente sin filtro humano intermedio — NO son buzones desatendidos, son la vía estándar de contacto en empresas de 1-10 empleados. Empresas T2 (5k-20k k€) sí tienen filtros administrativos: ahí mantenemos exigencia de decisor o nominal con cargo identificable.

Política aplicada (D20):

- **T1 y T3:** decisor (cargo claro: gerente / director / responsable) + nominal (`nombre.apellido@` con cargo no claro) + corporativo_pequeno (whitelist positiva por prefijo: `info@`, `contacto@`, `hola@`, `gerencia@`, `obras@`, `proyectos@`, `comercial@`, `direccion@`, `oficina@`, `administracion@`).
- **T2:** decisor o nominal con cargo identificable. Sin nominal ni decisor → fallback humano (cola "decisor manual" para Gonzalo).
- **T4:** decisión pendiente tras prueba comparativa.
- **Whitelist negativa global (todos los tiers):** `marketing@`, `rrhh@`, `prensa@`, `comunicacion@`, `noreply@`, `facturas@`, `contabilidad@`, `webmaster@`, `soporte@` se descartan siempre.

**Pivote a Skrapp y Apollo** (D19). Antes de comprometer plan pagado, prueba comparativa de los tres proveedores sobre el mismo sample de 25 empresas SABI con **criterio dual** (decisor + any email útil según D20). Free tiers de los tres cubren la prueba — coste 0€. Adapter primario y secundario se deciden tras tener los 3 hit rates comparables. Captura adicional como Lección 22: hit rate de email finders en construcción ES PYME puede ser estructuralmente bajo, regla operativa = probar 2-3 adapters antes de comprometer plan pagado.

**Cambios aplicados en este commit (sin código, sin migration SQL, sin prompts completos):**

- §3 — D17 marcada SUPERSEDED por D19. Añadidas D19 (descarte RocketReach, pivote a Skrapp/Apollo) y D20 (política emails por tier).
- §4 — fila "Hunter primario / RocketReach secundario" sustituida por dos filas en evaluación.
- §6.1 — `contacts.email_source` lista revisada (`rocketreach` fuera, `skrapp` dentro). Añadidas columnas `email_type` (enum decisor / nominal / corporativo_pequeno / descartado) y `email_priority` (1-4) como pendientes para migration al arrancar Sprint 4.
- §8.5 — renombrado a "Búsqueda de contactos via email finder". Política jerárquica decisor > nominal > corporativo_pequeno (T1/T3) > fallback humano (T2). Whitelists positivas y negativas explícitas. Worker renombrado de `find_decisors_hunter.py` a `find_contacts.py`.
- §8.6 — interfaz `EmailFinder` se mantiene; adapters concretos (primario/secundario) pendientes hasta cierre prueba comparativa. Métodos del Protocol renombrados de `find_decisors_*` a `find_contacts_*`.
- §10.2 — añadida regla "Variantes por `email_type`": el prompt de redacción adapta apertura/llamada al destinatario según `contacts.email_type`. SIN escribir el prompt completo en este commit. Implementación pendiente Sprint 4 o 5 según orden final.
- §14 Sprint 4 — primer paso es prueba comparativa Skrapp + Apollo (free tier, 0€) con métricas duales. Solo tras comparar los 3 hit rates se decide adapter primario y se implementa el flujo productivo.
- §16 — riesgo Hunter actualizado de "incierta" a "validada AMARILLO 8%". Riesgo nuevo: cobertura email finders construcción ES estructuralmente baja, mitigado por D20 + 3 proveedores en evaluación. Riesgo RocketReach eliminado.
- §17 — Hunter Starter quitado del coste recurrente. Vuelve a línea base ~75-95€/mes hasta adapter primario. Coste evaluación adapters: 0€.
- §18 — añadidas dependencias humanas Skrapp y Apollo (cuentas + API keys). Hunter marcada como operativa.

**Pendientes que NO entran en este commit y se ejecutan en Sprint 4 o posterior:**

- Migration SQL de `contacts.email_source` ampliado (skrapp añadido, rocketreach eliminado) + nuevas columnas `email_type` y `email_priority` con CHECK constraints. Migration al arrancar Sprint 4.
- Variante por `email_type` en el prompt de redacción §10.2 (apertura/llamada al destinatario adaptada). Implementación en Sprint 4 o 5.
- Pruebas comparativas Skrapp + Apollo sobre el mismo sample 25 empresas con criterio dual D20.
- Decisión final de adapter primario + secundario tras pruebas.
- Resolución T4 (gestión manual o fuera del primer batch) según outcome de pruebas.

**Lecciones nuevas registradas en `tasks/lessons.md`:** 21 (validar pricing y API en free tier antes de fijar proveedor — RocketReach gateado a Ultimate gatilló la regla), 22 (hit rate email finders construcción ES PYME estructuralmente bajo — probar 2-3 antes de comprometer plan pagado), 23 (criterio "solo decisor vale" demasiado restrictivo en B2B PYME ES — política segmentada por tier con whitelist por prefijo).

### 2026-05-06 — Sesión exploratoria intensiva de email finders + refactor arquitectónico mayor

Sesión maratón con tres frentes consecutivos sobre 25 empresas SABI del mismo sample (sembrado `demin-probe-hunter-2026-05-06`), más descubrimiento de la distribución real del universo accionable y dos ideas operativas adicionales (LinkedIn flow, empresite). Resultado: arquitectura híbrida por tier (D21) + roll-out escalonado (D22) + 4 lecciones nuevas (24, 25, 26, 27).

**Frente C — Hunter (commit 3c5b7a9).** Validación experimental: VEREDICTO AMARILLO 8% hit rate decisor estricto sobre 25 empresas (T1=0%, T2=20%, T3=20%, T4=0%). Calidad cuando cubría: excelente (cargos directamente accionables, confidence 96-99). Capturado en entrada §19 anterior.

**Frente D — Apollo (sin commit, rollback limpio).** Health-check confirmó cuenta operativa y `organizations/search` + `organizations/enrich` funcionando, pero todos los people endpoints (`mixed_people/search`, `people/search`, `people/match`, `people/show`, `mixed_people/organization_top_people`) devolvieron 403 `API_INACCESSIBLE` o 404/422. Apollo Free expone metadata de empresa pero NO personas — incompatible con el experimento comparativo planificado. Lección 21 aplicada por **4ª vez** (RocketReach Ultimate $2.484/año, Skrapp Enterprise $262/mes, Apollo Free no-people, antes Hunter cuenta inicialmente restringida pero recuperable). Cambios `.env.example` / `shared/config.py` / `.env.dev` rollbackeados.

**Frente E — Reanálisis Hunter+D20 sin nuevas llamadas (commit 36d5077).** Script `apps/workers/scripts/reanalyze_hunter_d20.py` (591 líneas) procesa el output crudo de Frente C bajo política D20 confirmada con humano (4 decisiones interactivas: A3 híbrido por tier, B whitelist positiva ampliada con `administracion`/`oficina`/`gestion`, C1 falso positivo Hunter T4 descartado, clasificaciones cargo sin ambigüedad). Resultado por tier:

| Tier | n | Decisor estricto | **D20 completo** |
|------|---|------------------|------------------|
| T1   | 5  | 0%  | **0%**  |
| T2   | 5  | 20% | **20%** (A3 estricto cancela ganancia) |
| T3   | 5  | 20% | **80%** (info@/comercial@/obras@ aceptados) |
| T4   | 10 | 0%  | **0%**  |
| Glob | 25 | 8%  | **20%** (ROJO global por threshold §16, pero con T3 verde aislado) |

**Distribución real del universo accionable (queries directas a prod):**

| Tier | Total SABI | `ia_fit='fit'` | % del universo accionable |
|------|------------|----------------|---------------------------|
| T1   | 455 | 118  | 22.8% |
| T2   | 171 | 48   | 9.3%  |
| T3   | 252 | 64   | 12.4% |
| T4   | 855 | **288** | **55.6%** |
| **Total** | 1.733 | **518** | 100% |

T4 sin web es 55.6% del universo accionable — el plan original asumía mayoría con web. La realidad PYME construcción ES es opuesta. Implicación: NO se puede ignorar T4 (Lección 24).

**Empresite.com como fuente complementaria (mini-experimento manual N=3).** Búsqueda manual sobre 3 empresas T4 sin web devolvió email visible en 3/3 casos. Calidad variable: Helian con email persona física en otra empresa (ruido), Velázquez Internacional en baja registral, Velzia Luxury Homes con web pese a marcado T4 en SABI. N=3 es ruido estadístico — mini-experimento estructurado pendiente sobre 10 empresas con tabla de cobertura. Pero apunta a empresite/einforma como fuente útil para Sprint 5 Opción C T4 (Lección 26).

**Flujo LinkedIn (idea Alberto desde experiencia M&A).** Búsqueda LinkedIn → filtro por cargo → URL del perfil → email finder con URL como input. Hit rate típico industrial 60-80% (vs 8-30% por dominio o nombre+empresa). Coste estimado Phantombuster ~$60/mes + email finder ~$50/mes. Riesgos: TOS LinkedIn prohíbe scraping (cuenta puede ser baneada), RGPD requiere base legal documentada para procesar datos personales públicos. Apuntado para Sprint 5+ si reply rate Sprint 4 con Hunter+D20 sobre T2+T3 resulta insuficiente (Lección 25).

**Decisiones tomadas:**

- **D21 — Arquitectura híbrida de email finder por tier** (camino 1). T3 = Hunter+D20 production-ready Sprint 4. T2 = Hunter+D20 + research IA enriquece-cargo Sprint 4 paso 4. T1 y T4 = Opción C completa Sprint 5 (research IA + permutación + verificación + empresite para T4).
- **D22 — Roll-out escalonado de Sprint 4 productivo por tier**. Semana 1 solo T3, Semana 2-3 añadir T2, Semana 4+ mantenimiento + Sprint 5 si T3+T2 valida. Razón: calentar dominio con leads de alta confianza antes de escalar a inciertos (Lección 27).

**Cambios aplicados en este commit (sin código, sin migration SQL, sin prompts completos):**

- §3 — añadidas D21 (arquitectura híbrida) y D22 (roll-out escalonado).
- §4 — Hunter como adapter primario único viable (`A decidir tras prueba comparativa` → entrada concreta). Apollo y Skrapp marcados descartados con razón. Research IA en §8.4 con función dual.
- §6.1 — nota "Implementación migration al arrancar Sprint 4 productivo" sobre `email_type` y `email_priority`.
- §8.4 — research_prospect.py expandido con `personas_extraidas: [{nombre, cargo_si_aparece, fuente_url}]` para enriquecer T2.
- §8.5 — lógica de `find_contacts.py` con paso 3 nuevo (cruce con `personas_extraidas` para T2). Whitelist positiva calibrada (añadidos `despacho`, `hello`, `contact`, `gestion`). Whitelist negativa añadido `atencion`. T1 y T4 explícitamente apuntan a Sprint 5 Opción C.
- §8.6 — `HunterAdapter` única implementación concreta. `SkrappAdapter`/`ApolloAdapter`/`RocketReachAdapter` como hooks teóricos (clases que cumplen `Protocol` pero devuelven listas vacías).
- §10.2 — variantes por `email_type` fijadas en Sprint 4 paso 5 (antes "4 o 5"). Sin tocar prompt completo.
- §14 Sprint 4 — reorganizado en 9 pasos con roll-out escalonado D22 explícito.
- §16 — riesgo nuevo "reply rate estructuralmente bajo en T3" con threshold operativo de 3% Semana 1. Riesgo T4 actualizado de "incierta" a "validada — Opción C en Sprint 5".
- §17 — costes Sprint 5 estimados +50-80€/mes, total pico 125-175€/mes (al límite D15, palancas listadas).
- §18 — Hunter operativa, Apollo/Skrapp/RocketReach descartados. Pendientes Sprint 5: empresite, LinkedIn, MillionVerifier.

**Pendientes que NO entran en este commit:**

- Migration SQL `contacts.email_source` ampliado + columnas `email_type` + `email_priority` (Sprint 4 paso 1).
- `apps/workers/shared/email_policy.py` reusando lógica de `reanalyze_hunter_d20.py` (Sprint 4 paso 2).
- `HunterAdapter` implementación concreta (Sprint 4 paso 3).
- `find_contacts.py` con cruce a `personas_extraidas` (Sprint 4 paso 4).
- `research_prospect.py` expandido con personas_extraidas (Sprint 4 paso 4b).
- 3 prompts `generate_email_{angle}.md` con bloque condicional `email_type` (Sprint 4 paso 5).
- Mini-experimento empresite estructurado sobre 10 T4 (Sprint 5 dependencia humana).
- Evaluación TOS + Phantombuster del flujo LinkedIn (Sprint 5 dependencia humana).

**Lecciones nuevas registradas en `tasks/lessons.md`:** 24 (universo PYME construcción ES dominado por T4 sin web 55.6% — validar input mínimo de cada tier antes de comprometer arquitectura), 25 (flujo LinkedIn → URL → email finder hit rate 60-80% industrial — apuntado Sprint 5+ con riesgos TOS/RGPD), 26 (empresite/einforma como fuente complementaria T4, mini-experimento estructurado pendiente), 27 (roll-out escalonado por probabilidad de respuesta — primeros 100 envíos marcan reputación de remitente, práctica industrial estándar).

---

## Apéndice A — Reglas no negociables (resumen para Claude Code)

1. **Nunca** envíes un correo sin pasar por la cola de aprobación (en HITL). En autónomo, nunca sin pasar las validaciones de §10.3.
2. **Nunca** ignores un opt-out explícito. Es exclusión permanente.
3. **Nunca** inventes datos del prospecto. Si el research no lo dice, no lo digas.
4. **Nunca** prometas plazos, precios o disponibilidad en nombre de DEMIN.
5. **Nunca** uses `localhost` o credenciales hardcoded en commits.
6. **Nunca** desactives auto-pausa sin aprobación humana explícita.
7. **Siempre** usa `pgvector` para el KB, no servicios externos de embeddings con almacenamiento.
8. **Siempre** versiona los prompts en el repo (`apps/workers/shared/prompts/*.md`).
9. **Siempre** que detectes desviación del plan, para y pregunta antes de seguir.
10. **Siempre** captura lecciones en `tasks/lessons.md` tras cualquier corrección humana.
11. **Nunca** inventes clientes, testimonios, casos de éxito o cifras en la web pública. Solo material que Gonzalo aporte y autorice.
12. **Siempre** mantén la separación de despliegue: `demingroupmadrid.com` (web pública, sin auth) ≠ `app.demingroupmadrid.com` (dashboard, auth obligatoria). Nada del dashboard debe ser accesible desde el dominio raíz.
