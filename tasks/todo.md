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
| D18 | 2-3 decisores por empresa (gerente + jefe de obra + responsable de compras donde aplique). Más allá de 3 genera percepción de spam para el destinatario; menos pierde el lead si el primero no responde. → **Refinamiento paso 6.6 (2026-05-12):** dentro del bucket nominal de la priorización, "con cargo identificado" precede a "sin cargo" en `email_priority` (3 vs 4) antes que el desempate por confidence Hunter. La unidad de cadencia operativa sigue siendo 1 contact (`is_primary=true`) por empresa — los otros 1-2 candidatos son respaldo manual visible en el dashboard (paso 6.5). Lección 29. | [DECIDIDO 2026-05-04 · refinado 2026-05-12] |
| D19 | RocketReach descartado por API gateada al plan Ultimate ($2.484/año, excede techo D15). Hunter validado AMARILLO (8% hit rate decisor sobre 25 empresas SABI, commit 3c5b7a9). Plan revisado: probar **Skrapp y Apollo** (free tier con API) sobre el mismo sample 25 empresas con criterio dual (decisor + any email útil según D20). Adapter primario y secundario decididos tras prueba comparativa, no antes. La interfaz abstracta `EmailFinder` se mantiene. Sustituye a D17. | [DECIDIDO 2026-05-06] |
| D20 | Política de aceptación de emails por tier de empresa. **T1 y T3** (1k-5k€ y 0.5k-1k€) aceptan decisor + nominal con cargo + corporativo_pequeno (whitelist positiva por prefijo: `info@`, `contacto@`, `gerencia@`, `obras@`, etc.). **T2** (5k-20k€) acepta decisor o nominal con cargo identificable; sin eso, fallback humano. **T4** (sin web) pendiente de resolver tras prueba comparativa (D19). Whitelist negativa global (todos los tiers): `marketing@`, `rrhh@`, `prensa@`, `noreply@`, etc. Razón: empresas micro/pequeñas no filtran `info@` — el gerente lo lee directamente; medianas sí filtran y exigen al menos email nominal. | [DECIDIDO 2026-05-06] |
| D21 | **Arquitectura híbrida de email finder por tier** (camino 1 tras Frente E ROJO global 20%). El reanálisis Hunter+D20 sobre las mismas 25 empresas (commit 36d5077) dio **T3=80%** (production-ready) pero **T1=0%, T2=20%, T4=0%**. Apollo y Skrapp también descartados durante la sesión (Apollo people endpoints gateados Free, Skrapp API gateada Enterprise — Lección 21 aplicada por 4ª vez). Decisión: Hunter es adapter primario único viable; otros adapters quedan como hooks futuros tras la interfaz `EmailFinder`. Plan de cobertura por tier: **T3** = Hunter+D20 production-ready en Sprint 4. **T2** = Hunter+D20 + research IA enriquece-cargo en Sprint 4 paso 4 (sube estimado 20%→50-60%, validar empíricamente). **T1 y T4** = Opción C completa en Sprint 5 (research IA web + permutación de patrones email + verificación con MillionVerifier; T4 complementada con `empresite.com` como fuente de email visible). | [DECIDIDO 2026-05-06] |
| D22 | **Roll-out escalonado de Sprint 4 productivo por tier**. **Semana 1 post-warmup: solo T3** (~51 empresas accionables tras `ia_fit='fit'` con cap inicial 10/día). **Semana 2-3: añadir T2** con research IA enriquece-cargo. **Semana 4+: mantenimiento** (revisión de métricas) + arrancar Sprint 5 (T1+T4 con Opción C) si reply rate de T3+T2 valida el sistema. Razón: empezar con leads de alta probabilidad de respuesta calienta dominio y genera baseline de reputación antes de escalar a leads inciertos. Los primeros ~100 envíos marcan la reputación de remitente para los siguientes ~1.000 — práctica industrial estándar capturada en Lección 27. → **Refinamiento paso 7 (2026-05-12):** cap Semana 1 sube de 10 a **20/día** tras 2 semanas de Lemwarm con score 92 y reply rate 80%. Rampa nueva 20→25→30→40 (§9.3). Lección 30 captura el patrón. | [DECIDIDO 2026-05-06 · refinado 2026-05-12] |

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
4. **Selección y priorización (D18 + D20, refinado en paso 6.6)**: 2-3 candidatos máximo por empresa, ordenados por `email_priority` 1..5 (1 = decisor confidence≥80; 2 = decisor confidence<80; 3 = nominal CON cargo identificado; 4 = nominal SIN cargo; 5 = corporativo_pequeno). Dentro del bucket nominal, el cargo claro (Director, Manager, Engineer, Architect, etc. — roles que `classify_email` no eleva a decisor estricto pero existen como función conocida) prevalece sobre el desempate por confidence: persona identificada con función conocida es mejor primary que persona sin función conocida aunque la confianza del email finder sea más alta (Lección 29 — el desempate silencioso por confidence enterraba esa distinción operativa). Primero por prioridad → `is_primary=true`.
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

**Selección y priorización (D18 + D20, refinado paso 6.6):** se eligen 2-3 candidatos por empresa máximo (D18). El campo `contacts.email_priority` ordena los candidatos en rango **1..5** (extendido desde 1..4 en migration 10): 1 = decisor con confidence≥80; 2 = decisor con confidence<80 o sin confidence; 3 = nominal CON cargo identificado; 4 = nominal SIN cargo; 5 = corporativo_pequeño en T1/T3/T4 cuando entra como respaldo. El primero por prioridad lleva `is_primary=true`. La distinción granular dentro del bucket nominal (3 vs 4) la introdujo el paso 6.6 tras detectar que el desempate por confidence enterraba la señal operativa del cargo (caso real: LENA CONSTRUCCIONES donde el nominal-sin-cargo zaragoza ganaba al nominal-con-cargo jaime.nozaleda "Business Development Director" por mejor confidence Hunter — Lección 29). `email_source` se rellena con el adapter que devolvió el dato (`'hunter'` | `'skrapp'` | `'apollo'` | `'manual'`).

**Los candidatos no-primary son respaldo manual, NO envío automático** (clarificado en paso 6.5, 2026-05-08). `generate_draft.py` filtra por `is_primary=true` y solo redacta para el primario. Los 1-2 candidatos no-primary quedan visibles en `/pipeline/[id]` como respaldo: si en Fase 3 el primario entra en `no_interesado` tras la cadencia D+0/D+4/D+10, Gonzalo puede escalar manualmente al secundario desde el dashboard. NO entran a la cadencia automática: enviar a varios contacts de la misma empresa el mismo día es señal de spam para los filtros del receptor (Gmail, Outlook) y degrada la reputación del dominio durante los primeros 100 envíos (Lección 27).

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
- **Cap por buzón (rampa refinada en paso 7, 2026-05-12):** Semana 1 = 20/día, Semana 2 = 25/día, Semana 3 = 30/día, Semana 4+ = 40/día (tope absoluto = 50/día por §9.1; nunca superarlo). El cap original del plan era "10/día +5/sem"; los datos reales de Lemwarm tras 2 semanas de warmup (score 92, reply rate 80%) justificaron arrancar más alto (Lección 30, refinamiento de D22). `mailboxes.daily_cap` arranca en 20 (migration 11 seed).
- **Rampa de campaña:** alineada con el cap por buzón (1 buzón activo según Lección 4 = cap_buzon = cap_campaña). 100 envíos en Semana 1 dan muestra estadística suficiente para evaluar bounce/spam/reply antes de subir.

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

1. Carga del contacto + empresa + research_data. **El worker filtra por `contacts.is_primary=true`** (D18 + §9.2: cadencia 1:1 contacto-secuencia, NO envío simultáneo a varios contacts de la misma empresa). Los contacts no-primary quedan como respaldo manual visible en `/pipeline/[id]`; entran a la cadencia automática solo si en Fase 3 el primary entra en `no_interesado` y se escala manualmente desde el dashboard. Filtrar por `is_primary` se añadió en paso 6.5 (commit pendiente al cierre — antes el worker iteraba todos los contacts elegibles, generando hasta 3 drafts simultáneos al mismo dominio = señal spam y degradación de los primeros 100 envíos del paso 7, Lección 27).
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
- [x] **Paso 2: `apps/workers/shared/email_policy.py`** — whitelists positiva/negativa + patrones decisor/nominal/descartado-por-rol + función de clasificación reusada del script `reanalyze_hunter_d20.py` (commit 36d5077). Implementado 2026-05-06 (commit e693f66) con whitelist negativa de 17 prefijos del plan §8.5 (supersede los 12 del script). 128 tests pasan (parametrizados sobre whitelists, decisores, roles negativos, A3 híbrido, normalización, edge cases). El script de exploración queda intacto como audit trail del Frente E.
- [x] **Paso 3: `HunterAdapter`** implementación concreta de la interfaz `EmailFinder` (§8.6, D21). `SkrappAdapter`/`ApolloAdapter`/`RocketReachAdapter` como stubs vacíos cumpliendo el `Protocol`. Implementado 2026-05-06 (commit af60296). `shared/email_finder.py` (Protocol + Contact + 3 stubs) y `shared/hunter_adapter.py` (Domain Search + Email Finder con tenacity retry sobre 429/5xx/timeout, 401→HunterAuthError sin retry, 400/404→[]). 42 tests con httpx.MockTransport (170 totales, sin créditos Hunter consumidos).
- [x] **Paso 4: `find_contacts.py`** con la lógica de §8.5 + cruce con `research_data.personas_extraidas` (D21) para enriquecer T2. Implementado 2026-05-06 (commit 56289aa). `apps/workers/pipeline/find_contacts.py` (449 líneas) — sequential, cap defensivo `--max-hunter-calls 20` (Free 25/mes), idempotente con `NOT EXISTS` + `ON CONFLICT DO NOTHING`, T1/T4 sin web fallback `find_contacts_by_company`, T2/T3 sin web skip silencioso, marca `ia_fit_reason='no_contactos_encontrados'` cuando Hunter respondió pero ningún email pasó filtro. 58 tests nuevos (228 totales) verdes, mypy --strict limpio (la deuda de `config.py:94` sigue siendo la única). Smoke real en dev sobre 3 T3 (`--limit 3 --max-hunter-calls 10`) consumió 3 búsquedas Hunter, insertó 3 contacts en LENA CONSTRUCCIONES (2 nominal + 1 corporativo_pequeno), marcó 2 empresas sin contactos.
- [x] **Paso 4b: `research_prospect.py` función dual (D21)** — dossier de personalización (D10 original, alimenta §10.2) + JSON output con `personas_extraidas: [{nombre, cargo_si_aparece, fuente_url}]` para enriquecer cargos T2 (§8.4). Implementado 2026-05-06 (commit ee10c54). `apps/workers/pipeline/research_prospect.py` (~600 líneas) + `apps/workers/shared/prompts/research_prospect.md` versionado (regla 8). Scraping httpx síncrono con UA Chrome desktop, home + 9 subpaths de §8.4, abort tras 4 fallos consecutivos, fallback https→http, threshold thin_html=500 chars (warning, no abort). Texto extraído con selectolax (sin script/style/nav/footer/header) concatenado con `--- <url> ---` como anchor para `personas_extraidas[].fuente_url`, truncado a 32k chars (~8k tokens). LLM Sonnet 4.6 vía `call_llm(task='research_prospect')`, parsing tolerante a code fences, validación tier-segmentada de campos (tamaño/tipo_obra/lenguaje filtrados a valores conocidos), defaults vacíos para campos faltantes. Cap defensivo `--max-cost-usd 5.0`. Idempotente con `--rerun` (re-procesa todo) y `--retry-failed` (solo las que tienen `_failed`) mutuamente exclusivos — añadido tras razonar que esperamos 7-17% de fallos por scraping ruidoso (SSL caduco, redirects, SPAs) + ruido transitorio de Anthropic, y un solo `--rerun` quemaría el universo entero ($0.56) para recuperar 8-15 fallos. 55 tests nuevos (283 totales verdes), mypy --strict sobre `research_prospect.py` limpio. Smoke real en dev sobre 3 T2 (`--limit 3 --max-cost-usd 0.50`): 2/3 OK (BRILLAS AGUSTI + RUTHERFORD con dossiers de calidad — hooks anclados al material real de la web), 1 falló con `llm_error` por Anthropic 529 overload (Sonnet 4.6 caído al momento del smoke, mismo patrón que Sprint 3 sesión 2026-05-04). Coste total $0.034. `--retry-failed` sobre la fallida volvió a fallar por mismo Anthropic 529 — comportamiento correcto del worker, recuperable cuando Anthropic se estabilice.
- [x] **Paso 5: prompts** `generate_email_{opening,reframe,closing}.md` en `apps/workers/shared/prompts/` con bloque condicional por `email_type` (decisor/nominal/corporativo_pequeno, §10.2). Implementado 2026-05-06 (commit 31e6d72). 3 archivos versionados (regla 8). Bloque condicional implementado vía decisión C: el LLM autoregula leyendo la variable `{email_type}` del user template (más simple que marcadores en el .md o selección en código; valida que añadir un cuarto email_type futuro = añadir un párrafo). Sub-objetivos diferenciadores: opening = presentación + UN hook elegido + propuesta de conversación corta (sin `{correos_previos}`, primer toque); reframe (día +4) = no-respuesta sin presión + hook B distinto del A del opening + asunto distinto; closing (día +10) = cortesía + opción explícita "no insistir" + **pregunta sí/no estructurante** que fuerza categorización entre `no_ahora` y `no_interesado` para alimentar §11 + D13 (body ≤100 palabras, más corto que los otros dos). 53 tests estructurales nuevos (336 totales verdes): existencia + parsing, 9 variables comunes + `{correos_previos}` solo en reframe/closing, email_type×3 mencionado en system, identidad DEMIN/Gonzalo, regla sin emojis, JSON output con 3 keys, no-markdown, placeholders bien formados, sub-objetivos diferenciadores, versionado de cabecera. Sin smoke LLM en paso 5 — la señal "prompt produce JSON parseable y prosa coherente" sobre data dummy es parcial vs lo que paso 6 dará con 5 T3 reales + criterio Gonzalo, así que esperar al paso 6 da el filtro correcto sin un paso intermedio que no agrega información distinta.
- [x] **Paso 6: validación E2E** sobre 5 empresas T3 reales (NO las 25 del Frente C — otras 5 al azar entre los `ia_fit='fit'` de prod) en HITL completo: research → find_contacts → generate_draft → cola aprobación. Implementado 2026-05-06 (commits b44913b + 64c2a8e + 66166b2). **Opción C** confirmada PM-side: `generate_draft.py` worker + `/pipeline` read-only en dashboard + script HITL terminal (`hitl_review.py`) + smoke E2E sobre 5 T3 reales en dev. Approval Queue dashboard difiere a paso 7. Smoke real: 5 T3 procesados por research_prospect (5/5 OK, $0.085, 0 personas_extraidas en 4/5 — confirma señal del paso 4b — y 3 personas extraídas en NOG INTERIORISMO — primera evidencia positiva), 5 procesados por find_contacts (1 contact insertado en NOG, cobertura Hunter T3 efectiva del smoke 20%, no el 80% del Frente E — señal a cruzar en paso 9), 4 drafts generados con calidad anclada al research real (1 nominal-con-cargo en LENA + 1 nominal-sin-cargo en LENA + 1 corporativo en LENA + 1 corporativo en NOG — las 3 variantes por email_type del paso 5 aplican correctamente en producción, decisión C validada). Coste total smoke: $0.18 LLM + 6 búsquedas Hunter (37→31 restantes). Validación humana posterior con `hitl_review.py` la hace Alberto/Gonzalo cuando lo decida. **Monitor de falsos positivos classify_descr** (PM nota): se detectaron **2 FPs en los 5 T3 reales** — SERVISHOP MANLOGIST (servishop.com vacío en Hunter, dudoso por el research) y SB 63 (pinnea.com) requieren auditoría humana del research dossier para confirmar/descartar. RUTHERFORD ESPAÑOLA del paso 4b queda como tercer FP probable. **Si la auditoría confirma >1 FP**, classify_descr necesita iterar antes de paso 7 (cruce explícito en paso 9).
- [ ] **Paso 7: roll-out Semana 1 [cruza a Fase 2]** — solo T3 a **cap 20/día** (refinado 2026-05-12, Lección 30) con envío real Gmail API, monitoring bounce/spam/reply. Si bounce >2% o spam >0.1% en cualquier momento, parar y revisar antes de paso 8.

    **Construcción técnica cerrada 2026-05-12** (pre-requisitos de envío real):
    - [x] Migration 11 + seeds mailbox `gonzalo.perez@demingroupmadrid.com` (cap 20) + sequence `demin_v1` (D+0/D+4/D+10) + campaign `T3 Semana 1` (aplicadas dev + prod).
    - [x] `shared/gmail_adapter.py` con OAuth refresh_token + tenacity retry 429/5xx + tests MockTransport.
    - [x] `outreach/send_gmail.py` con ventana 9-13/15-18 Madrid, jitter, cap rolling 24h, footer opt-out + firma + tests.
    - [x] `outreach/follow_ups.py` programa step+1 cuando sent_at >= delta_days y sin reply (D+4 reframe, D+10 closing).
    - [x] `outreach/auto_pause.py` vigila bounce 2% / spam 0.1% rolling 7d con sample minimo 50 (§9.4).
    - [x] `/approval-queue` dashboard con server actions + keyboard nav (j/k/a/e/x/s).
    - [x] `/metrics` dashboard read-only: embudo + rates 7d + coste mes.
    - [x] `/settings` dashboard con pausa de emergencia + reanudar (Apéndice A regla 6).

    **Bloqueadores humanos pendientes antes del primer envío real**:
    - **(B1) Gmail OAuth** — Google Cloud Console (cuenta Gonzalo): proyecto + Gmail API enabled + OAuth client (Desktop) con scope `gmail.send`. Flow OAuth standalone para `gonzalo.perez@demingroupmadrid.com` → guardar refresh_token en `mailboxes.oauth_refresh_token_encrypted`. Scripts auxiliares listos (2026-05-12): `scripts/gmail_oauth_setup.py` corre el flow OAuth (descarga credentials.json + browser local) y `scripts/seed_oauth_token.py` persiste el token en BD (intenta Supabase Vault, fallback plaintext con prefijo `PLAINTEXT:`). `send_gmail.resolve_refresh_token` soporta los 3 formatos (UUID Vault / PLAINTEXT prefix / plaintext directo) en runtime. Sin B1 resuelto, `send_gmail.py` aborta con exit code 2.
    - **(B2) Despliegue dashboard prod** — `app.demingroupmadrid.com`. Ver §19 entrada 2026-05-12 paso 7 sub-sección "Instrucciones B2".
    - **(B3) Hunter Starter API key** (PM pagando 2026-05-12) — sustituir `HUNTER_API_KEY` en `.env.prod` cuando llegue. Subir `DEFAULT_MAX_HUNTER_CALLS` de 20 a 100 en `find_contacts.py` (decisión PM 1.6 paso 7).
    - **(B4) ALLOWED_EMAILS en Vercel prod** — coordinar `gonzalo.perez@demingroupmadrid.com,albertobueno10@gmail.com` como whitelist.
    - **(B5) Smoke E2E pre-envío real (decisión PM 1.5 paso 7)** — usar contact dev real (LENA jaime o NOG administracion) con `--override-to albertobueno10@gmail.com`. Verificar: OAuth flow, footer opt-out renderizado, gmail_message_id capturado, evento `message_sent` insertado. NO arrancar envío productivo (cap 20/día sobre T3) hasta validar este smoke.
    - **(B6) HITL approval del primer batch productivo** — Gonzalo aprueba en `/approval-queue` web tras B1+B2+B4.

    **Pre-condiciones operativas acumuladas del paso 6.5/6.6** (siguen vigentes):
    - **(a) Auditoría humana de drafts** — tras paso 6.6 ya hay 2 drafts vivos correctos (jaime LENA primary + administracion NOG primary). PM aprobó ambos vía HITL. Compleción del gate de calidad literaria.
    - **(b) Hunter Starter activación** — gestionado en B3.
    - **(c) Monitor cobertura Hunter T3 efectiva** — smoke paso 6 dio 20% (1/5), Frente E proyectaba 80%. Métrica a registrar desde envío 1: `(empresas con ≥1 contact aceptable) / (empresas T3 fit con web procesadas)`. Si <30% en primeros 30-50 envíos, D21 hay que revisar.

    **Condición de activación `verify_emails.py` durante paso 7** (decisión PM 1.2 paso 7): si **bounce rate >1% en el primer batch de 50 envíos**, construir `verify_emails.py` (§8.7) ANTES del paso 8. Hunter ≥60 confidence se asume suficiente; si la realidad muestra >1% bounce, ese supuesto cae y necesitamos verificación MX + SMTP probe explícita.
- [ ] **Paso 8: roll-out Semana 2-3 [Fase 2]** — añadir T2 con `personas_extraidas` enriqueciendo cargos. Validar que el hit rate efectivo sube de 20% (Frente E) a 50-60% (estimado D21). Si no sube, parar y revisar `personas_extraidas` antes de continuar. **Verificar cobertura `personas_extraidas` con muestra grande** (PM nota tras paso 4b smoke): el smoke de paso 4b sobre 3 T2 dejó 0/2 OK con personas enriquecidas — señal a confirmar al correr research_prospect sobre las 49 T2 enteras. **Threshold operativo: si <30% de las T2 con research OK terminan con `personas_extraidas` no vacío, el supuesto D21 (hit rate 20%→50-60%) cae** y la decisión arquitectónica del paso 9 tiene que cruzar explícitamente esta señal en lugar de asumir que el flujo dual funcionó.
- [ ] **Paso 9: cierre Sprint 4** — métricas reales de Semana 1+2-3, revisión post-Sprint Lección 19 (¿alguna decisión §3 invalidada? ¿§8 sigue alineado? ¿Sprint 5 con Opción C tiene suposiciones tumbadas?), entrada §19, decisión go/no-go Sprint 5. **Cruces explícitos obligatorios** (PM notas acumuladas durante el sprint): (a) D21 vs cobertura efectiva `personas_extraidas` medida en paso 8 — si <30% T2 OK con personas enriquecidas, el hit rate 20%→50-60% no se materializa y revisar arquitectura híbrida; (b) clasificación Sprint 3 vs falsos positivos detectados en paso 6 — si >1 FP confirmado en las 5 T3 reales (paso 6 ya identificó 2 candidatos: SERVISHOP MANLOGIST y SB 63 pinnea.com, más RUTHERFORD ESPAÑOLA del paso 4b), classify_descr necesita iterar antes de Sprint 5; (c) cobertura Hunter T3 efectiva vs Frente E (smoke paso 6 dio 20% sobre 10 empresas, frente al 80% que Frente E proyectaba sobre 5 — la divergencia merece análisis: ¿muestreo? ¿el ICP real T3 con web tiene peor cobertura Hunter de lo asumido?); (d) **pasada de saneamiento `mypy --strict` de `shared/` + `tsc --noEmit` del dashboard** — 4 deudas acumuladas (config.py:94, llm.py:72, llm.py:190, scripts/smoke_kb_e2e.ts:76/94/107), todas triviales individualmente pero acumuladas en módulos transversales merecen un arreglo conjunto al cerrar Sprint 4 o como primer paso de Sprint 5.

**Items productivos transversales al Sprint 4 (no atados a un paso concreto):**

- [ ] Worker `verify_emails.py` validado — se activa al insertar el primer `contact` con email no verificado (Sprint 4 paso 4 en adelante)
- [ ] Logs y observabilidad básica
- [ ] Pantalla "Pipeline" funcional (read-only) — pre-requisito UX de Sprint 4 paso 6/7 para que Gonzalo audite leads + research + contactos

**Deuda técnica conocida (no scope Sprint 4):**

- `apps/workers/shared/config.py:94` — `mypy --strict` reporta `Argument 1 to "env_file_path" has incompatible type "Literal['dev','prod'] | None"; expected "Literal['dev','prod']"`. Detectado al ejecutar mypy en Sprint 4 paso 3 (commit af60296). No bloquea ningún flujo runtime — `os.environ.get("ENV","dev")` siempre devuelve string. Fix trivial (`assert env is not None` o cambiar la firma). Se aborda cuando bloquee algo o en una pasada de saneamiento general.
- **httpx loguea api_key en cleartext en URLs de Hunter.** `logging.getLogger("httpx")` imprime cada request en INFO con `?api_key=140fd9...` completo en la URL — viene del comportamiento por defecto de httpx, no de nuestro código. Detectado al ejecutar el smoke de Sprint 4 paso 4 (commit 56289aa). Mientras los logs queden en local no hay leak real, pero **antes de cualquier flujo donde los logs salgan del entorno** (Sentry, CloudWatch, ELK, Vercel logs si en algún momento un worker corre allí, etc.) hay que mitigarlo. Fix: `logging.getLogger("httpx").setLevel(logging.WARNING)` en `shared/hunter_adapter.py` y `shared/llm.py` (o globalmente en `shared/config.py`); alternativa más fina, un filtro que redacte query params sensibles. La API de Hunter solo acepta key como query param, así que no se puede mover a header. NO urgente para Sprint 4 paso 4-7 (logs locales solo); SÍ obligatorio antes de Fase 3 (autonomía → probable export de logs a sistema central) o si algún paso intermedio activa export de logs.
- `apps/workers/shared/llm.py:72` — `mypy --strict` reporta `Module "voyageai" does not explicitly export attribute "Client"`. SDK upstream sin `__all__` ni `py.typed`. Detectado al ejecutar mypy en Sprint 4 paso 4b (commit pendiente). Fix trivial: añadir `# type: ignore[attr-defined]` en la línea de `voyageai.Client(...)`. No bloquea runtime.
- `apps/workers/shared/llm.py:190` — `mypy --strict` reporta `Incompatible return value type (got "list[list[float]] | list[list[int]]", expected "list[list[float]]")`. El SDK Voyage tipa `embeddings` como heterogéneo en sus stubs aunque en runtime devuelve solo floats. Detectado al ejecutar mypy en Sprint 4 paso 4b. Fix trivial: cast explícito `list[list[float]]` o `# type: ignore[return-value]`. No bloquea runtime — el smoke `embed_documents` en Sprint 1 cargó 27 chunks y tests Voyage validaron dim 1024 sin issues.
- `apps/dashboard/scripts/smoke_kb_e2e.ts:76,94,107` — `tsc --noEmit` reporta 3 errores TS2345: `Argument of type 'SupabaseClient<any, "public", "public", any, any>' is not assignable to parameter of type 'SupabaseClient<unknown, { PostgrestVersion: string; }, never, never, { PostgrestVersion: string; }>'`. Detectado al ejecutar `npx next build` en Sprint 4 paso 6 (commit 66166b2 al construir `/pipeline`). El error viene de un type drift entre @supabase/supabase-js (cliente que devuelve SupabaseClient<any, "public", ...>) y la firma del helper local que el script consume (espera el shape genérico de PostgREST). Preexistente — el script `smoke_kb_e2e.ts` se mergeó en Sprint 1 antes de que el SDK actualizara sus genéricos. Fix trivial: añadir un `as unknown as` cast en las 3 llamadas o ajustar la firma del helper. NO bloquea runtime (el `next build` compila las páginas correctamente; sólo falla la fase de typecheck en CI). NO afecta a `/pipeline` ni a `/kb`. Atacar conjuntamente con las 3 deudas mypy de `shared/` en la pasada de saneamiento del paso 9 o inicio Sprint 5.

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
| Email finder — adapter primario Hunter (D21) | **30-45€/mes** (Starter, 500 búsquedas/mes) activado en paso 7 (2026-05-12). Free 50/mes no aguantaba el cap 20/día sostenido. PM autorizó el upgrade explícitamente. Régimen Sprint 4 productivo. |
| Email finder — régimen mantenimiento  | 0€ esperable (free tier de Hunter cubre reposiciones puntuales tras procesar el universo SABI accionable) |
| Anthropic API (uso normal) | ~20-30€ |
| Embeddings (Voyage AI) | ~2-5€ |
| Hetzner VPS CX22 | ~5€ |
| Vercel | 0€ (free tier) |
| Supabase | 0€ (free tier) |
| **Total recurrente paso 7 en adelante (Sprint 4 productivo)** | **~105-140€/mes** (Hunter Starter activado). Dentro de techo D15 (150€/mes) con margen ajustado. |

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

### 2026-05-06 — Cierre Sprint 4 paso 4: find_contacts.py + smoke verde sobre 3 T3 dev

`apps/workers/pipeline/find_contacts.py` (449 líneas) cierra el paso 4 del Sprint 4 (D21, D22). El worker itera companies con `ia_fit='fit'` del tier solicitado, llama `HunterAdapter` con el dominio extraído de `companies.web` vía `tldextract` (o `find_contacts_by_company` como fallback gratis para T1/T4 sin web), clasifica cada email con `email_policy.classify_email`, opcionalmente enriquece nominal-sin-cargo con `research_data.personas_extraidas` (D21, no-op mientras paso 4b no haya corrido), aplica `is_acceptable_for_tier`, prioriza 1..4 (decisor+conf≥80=1, decisor=2, nominal=3, corporativo_pequeno=4) y elige hasta 3 candidatos por empresa (D18). Inserta con `email_source='hunter'`, `email_verified=false`, `is_primary=true` solo en el primero; `ON CONFLICT (company_id, email) DO NOTHING` cubre re-runs. Las empresas que llamaron Hunter pero quedaron sin candidatos aceptables se marcan con `ia_fit_reason='no_contactos_encontrados'` (sentinel para paso 6/7).

**Política operativa interna:** procesamiento sequential (no thread pool — Hunter Free 25/mes hace que la paralelización no compense y aumenta el riesgo de rate limit), cap defensivo `--max-hunter-calls 20` por defecto (deja 5 de margen al Free 25/mes), `--tier {T1..T4}` obligatorio (forzar al humano a pensar qué tier ataca, no hardcoded a T3 aunque D22 lo ordene primero), `--reprocess` para sobrescribir empresas ya pobladas (default: skipea con `NOT EXISTS`).

**Tests (58 nuevos, 228 totales verdes).** `tests/test_find_contacts.py` cubre las 5 funciones puras (`resolve_domain_from_company` con tldextract, `assign_priority` con tabla parametrizada incluyendo el umbral 80 inclusivo, `select_top_candidates` con orden por priority asc + confidence desc, `enrich_with_personas_extraidas` con normalización y casos defensivos, `classify_and_filter` con T2 vs T1/T3/T4 y A3 con/sin enriquecimiento) más `process_company` con `MagicMock` del adapter (T1/T4 sin web → fallback, T2/T3 sin web → skip silencioso, truncado a 3, todo filtrado tras llamar Hunter). Mypy `--strict` sobre `pipeline/find_contacts.py` limpio — la única alerta restante en el repo sigue siendo la deuda `config.py:94` documentada en §14, fuera de scope.

**Smoke real en dev (3 búsquedas Hunter consumidas):**

```
find_contacts  env=dev  tier=T3  limit=3  max_hunter_calls=10  reprocess=False
[fetch] 3 empresas a procesar
  [3/3]  hunter_calls=3  insertados=3  sin_contactos=2  skip_no_dom=0  errs=0

contacts insertados (3):
  A78062601 LENA CONSTRUCCIONES   zaragoza@nozar.es        nominal  prio=3 primary=True
  A78062601 LENA CONSTRUCCIONES   jaime.nozaleda@nozar.es  nominal  prio=3 primary=False  (Business Development Director)
  A78062601 LENA CONSTRUCCIONES   info@nozar.es            corporativo_pequeno  prio=4 primary=False
empresas sin contactos aceptables: 2 (servishop.com y pinnea.com — Hunter devolvió 0 emails)
```

Antes del smoke: 64 T3 fit en dev, 0 con contacts. Después: 1 con contacts (LENA CONSTRUCCIONES, 3 contacts), 2 marcadas `ia_fit_reason='no_contactos_encontrados'`. Comportamiento end-to-end como esperado: prioridad asignada correcta, `is_primary` solo en el primero, todos `email_verified=false` (lo rellenará `verify_emails.py`).

**Observación lateral (deuda nueva, NO scope paso 4):** `httpx` loguea por defecto la URL completa de cada request en INFO, lo cual incluye `?api_key=<REDACTED-2026-05-13-tras-leak-GitGuardian>` en cleartext. Si en algún momento los logs viajan a un sistema central (Sentry, CloudWatch, ELK), la API key queda expuesta. El leak viene del `HunterAdapter` (paso 3) y de la API de Hunter, que solo acepta key como query param. Fix futuro: silenciar `logging.getLogger("httpx").setLevel(WARNING)` en `shared/llm.py`/`hunter_adapter.py`, o filtrar en handlers. Apuntado, no urgente.

**Compromiso de cap Hunter:** plan Free 25/mes. 3 búsquedas consumidas hoy + ~25 que ya gastó Frente C en sesión 2026-05-06 (commit 3c5b7a9) + algunas residuales. El contador se resetea mensualmente. Sprint 4 paso 6 (validación E2E sobre 5 T3 reales) consumirá otras 5; paso 7 Semana 1 con cap 10/día consumirá ~70/semana — **techo Free agotado en pocos días**. Decisión consciente: para Sprint 4 paso 4 el Free es suficiente; activar Hunter pago (Starter 30-45€/mes con 500 búsquedas/mes) cuando arranque el roll-out productivo del paso 7. Recordatorio guardado en memoria para volver a plantearlo antes de paso 7.

### 2026-05-06 — Cierre Sprint 4 paso 4b: research_prospect.py función dual + smoke verde 2/3 T2 dev

`apps/workers/pipeline/research_prospect.py` (~600 líneas) cierra el paso 4b del Sprint 4 (D21). Sustituye al stub vacío que existía desde Bloque B. Implementa la función dual de §8.4: dossier de personalización (D10 original, alimenta el prompt de redacción §10.2 de paso 5) **más** `personas_extraidas: [{nombre, cargo_si_aparece, fuente_url}]` que `find_contacts.py` (paso 4) consume para reclasificar T2 nominal-sin-cargo a nominal-con-cargo (§8.5 paso 3). El prompt vive versionado en `apps/workers/shared/prompts/research_prospect.md` (regla 8 del Apéndice A) con secciones `## System` y `## User template`, dejando la regla "no inventes datos; personas_extraidas solo con nombre + cargo literales" como NO negociable explícita.

**Pipeline por empresa.** Resuelve URL canónica con `tldextract` + scheme `https://<dominio>` (sin subdominios; `www.` se ignora para estabilizar el target). Scrapea home + 9 subpaths de §8.4 (`/contacto`, `/servicios`, `/proyectos`, `/sobre-nosotros`, `/equipo`, `/team`, `/about`, `/quienes-somos`) con `httpx` síncrono, timeout 8s, UA Chrome desktop, follow_redirects=True. Si home falla con `https://`, intenta `http://` automáticamente. Si los primeros 4 subpaths dan 404, aborta los 4 restantes (heurística: si la web no usa los paths estándar, es muy probable que ninguno exista). Detecta SPAs por home con <500 chars de texto extraído y marca `_warning='thin_html_possibly_spa'` (no aborta). Texto de cada página se extrae con `selectolax` eliminando `<script>`, `<style>`, `<noscript>`, `<nav>`, `<footer>`, `<header>`; se concatena con `--- <url> ---` como anchor (el LLM usa esa cabecera para rellenar `personas_extraidas[].fuente_url`); se trunca a 32k chars (~8k tokens, límite §8.4). LLM Sonnet 4.6 vía `call_llm(task='research_prospect')` con `max_tokens=2000`. Parser tolerante: code fences se quitan, JSON inválido o no-dict levanta excepción → `_failed='json_parse'` con `raw_excerpt` para auditar; campos faltantes se rellenan con defaults (""/[]); valores fuera de los enum permitidos para `tamano_aparente`/`tipo_obra_que_hacen`/`lenguaje_que_usan` caen al default "incierto"/[]/"" en lugar de propagarse. UPDATE atómico de `companies.research_data` (jsonb) y `companies.research_done_at = now()`.

**Decisiones operativas tomadas en sesión** (al delegar el PM las 4 decisiones técnicas):

- **Playwright fallback fuera de v1.** Coste de instalación (~150MB chromium) + complejidad async/lifecycle no compensa hasta validar volumen real de SPAs. Si en el smoke o en el run pleno T2/T3 vemos >20% de empresas con `_warning='thin_html_possibly_spa'`, segunda iteración con playwright en Sprint 5.
- **Cap defensivo `--max-cost-usd 5.0` por defecto.** Plan §8.4 estima ~$0.005/empresa con Sonnet 4.6; T3+T2 = 113 empresas con web ≈ $0.56 → margen 9× sobre el run completo. Mismo umbral que `classify_descr.py` (Sprint 3) para coherencia operativa.
- **`--rerun` y `--retry-failed` ambos, mutuamente exclusivos** (`argparse.add_mutually_exclusive_group`). Razonamiento: scraping web es ruidoso por naturaleza (SSL caduco, redirects raros, SPAs sin SSR, dominios caducados, errores intermitentes Anthropic) y se espera 7-17% de fallos sobre 113 empresas — eso son 8-19 fallos, una cohorte significativa, no anomalías sueltas. Si solo existiera `--rerun`, recuperar esos 8-19 fallos exigiría re-procesar las 113 enteras quemando ~$0.56 por nada. `--retry-failed` cuesta 2 líneas (un `WHERE c.research_data ? '_failed'`) y deja la opción quirúrgica. Smoke validó este razonamiento: la primera ejecución dejó 1/3 con `_failed` por Anthropic 529, recuperable con `--retry-failed` cuando Anthropic se estabilice — sin gastar tokens en las 2 que ya estaban OK.
- **Cliente httpx compartido entre threads.** httpx>=0.27 es thread-safe, así que un solo `httpx.Client(...)` se inyecta a todos los workers del `ThreadPoolExecutor`. Reduce overhead de connection pool y simplifica el lifecycle (un solo `with` en `main()`).

**Tests (55 nuevos, 283 totales verdes).** `tests/test_research_prospect.py` cubre el contrato del worker sin red ni LLM real:

- Funciones puras: `resolve_base_url` (canonicalización + casos inválidos), `extract_text_from_html` (selectolax con tags decorativos eliminados, whitespace colapsado, HTML sin body), `truncate_to_budget` (corte por palabra + marcador), `compose_pages_text` (anchor `--- url ---`, skip de páginas vacías), `clean_personas_extraidas` (entradas válidas + 7 patrones malformados parametrizados + coerce de tipos no-string), `parse_research_json` (happy path, code fences, valores fuera de enum, truncado de listas, campos faltantes, no-dict, JSON inválido).
- Scraping con `httpx.MockTransport`: home OK + subpaths OK, abort tras 4×404, `ConnectError` en home → failure, 4xx en home → failure, thin_html=True con home corto, fallback https→http cuando https falla.
- E2E con `httpx.MockTransport` + `monkeypatch` sobre `shared.llm.call_llm`: happy path con dossier completo, `_failed='invalid_web'` cuando `resolve_base_url` devuelve None, `_failed='scraping_failed'` cuando home unreachable, `_failed='llm_error'` cuando call_llm levanta, `_failed='json_parse'` cuando LLM devuelve garbage, `_warning='thin_html_possibly_spa'` propagado al research_data, `_meta.base_url` y `_meta.n_pages_scraped` rellenos.

mypy `--strict` sobre `pipeline/research_prospect.py` limpio (0 errores en el archivo del paso). Mypy reporta 3 errores en módulos pre-existentes (`shared/config.py:94` ya documentada + `shared/llm.py:72` y `:190` recién descubiertas porque `research_prospect.py` es el primer worker que importa `shared.llm` desde mypy --strict). Las 2 nuevas se anotan en "Deuda técnica conocida" de §14 — todas tienen fix trivial (`# type: ignore` en la línea concreta) y NO bloquean runtime; se abordan en una pasada de saneamiento general.

**Smoke real en dev (3 T2, $0.034 USD).**

```
research_prospect  env=dev  tier=T2  limit=3  workers=2  max_cost_usd=0.5  rerun=False  retry_failed=False
[fetch] 3 empresas a procesar

  [3/3]  ok=2  failed=1  personas=0  thin_html=0  tok=6541+961  est_usd=0.034

failure breakdown: {'llm_error': 1}  (Anthropic 529 overload × 3 reintentos)
```

Audit detallado de los 2 OK:

| nif | empresa | tipo | tamaño | tipos_obra | hooks | personas |
|---|---|---|---|---|---|---|
| `A28193209` | CONSTRUCCIONES BRILLAS AGUSTI | "Constructora con 100 años de historia: obra nueva, rehabilitación, reforma integral y mantenimiento de edificios residenciales, educativos e industriales en Madrid" | mediano | residencial+comercial+industrial+obra_nueva+reforma+rehabilitacion (6/6) | 3 hooks anclados (calle Murcia, centros educativos, hoteles) | 0 |
| `A28167567` | RUTHERFORD ESPAÑOLA | "Construcción y mantenimiento de piscinas, spas, fuentes, complejos deportivos y rehabilitación de instalaciones acuáticas desde 1966" | mediano | comercial+reforma+rehabilitacion | 3 hooks anclados (60 años, ISO 9001, hoteles/deportivos) | 0 |

La empresa fallida (`A28124519` CABBSA) quedó con `research_data={"_failed": "llm_error", "reason": "RetryError: Last retry attempt 529 overload", "base_url": "https://cabbsa.com"}`. Un `--retry-failed` posterior la volvió a tirar abajo por mismo Anthropic 529 — el proveedor tenía una ventana de inestabilidad en el momento del smoke. Recuperable con otro `--retry-failed` cuando Anthropic se estabilice; el contrato del worker es correcto.

**Observación 0 personas_extraidas en 2/2 OK.** No es bug del worker. Las webs de BRILLAS y RUTHERFORD probablemente no listan equipo con cargos literales (típico en PYMEs construcción ES sin sección "Equipo"/"Sobre nosotros" de calidad). El LLM aplicó la regla "no inventar cargo aunque sepas el nombre" del prompt. Señal real para Sprint 4 paso 8: la cobertura efectiva de `personas_extraidas` se medirá cuando research_prospect corra sobre las 49 T2 enteras; si <30% tienen alguna persona enriquecida, la mejora del hit rate T2 esperada por D21 (20% → 50-60%) no se materializa y hay que revisar el plan (Lección 19, post-Sprint).

**Observaciones laterales del smoke (no bloquean cierre):**

- RUTHERFORD ESPAÑOLA tiene `ia_fit='fit'` pero su negocio es piscinas/spas — el research lo identifica correctamente. Es señal posible de falso positivo del classify_descr (Sprint 3) sobre descripciones SABI ambiguas. NO scope del paso 4b. Anotar para auditoría humana de la lista de fits cuando paso 6 muestre los candidatos a Gonzalo.
- Anthropic 529 overload en una ventana ~10 min al momento del smoke. Mismo patrón que Sprint 3 (`Lección 23`). El `--retry-failed` está diseñado exactamente para esto.
- httpx loguea las URLs de scraping completas en INFO (sin api_key — Hunter sí, no es un issue aquí). Pero confirma la deuda apuntada del scope de logging (§14 deuda técnica): cuando los logs salgan del entorno local hay que filtrarlos, y el filtrado debería cubrir tanto Hunter URLs como cualquier otro request URL si en el futuro decidimos que las URLs visitadas son sensibles.

### 2026-05-06 — Cierre Sprint 4 paso 5: 3 prompts generate_email versionados con bloque condicional por email_type

`apps/workers/shared/prompts/generate_email_{opening,reframe,closing}.md` cierran el paso 5 del Sprint 4 (D20). 3 archivos versionados (regla 8 del Apéndice A) con la estructura `## System` + `## User template` que comparten los demás prompts del repo (`classify_fit.md`, `research_prospect.md`).

**Decisión arquitectónica de las variantes por `email_type` (D20).** §10.2 dejaba abierta la implementación; las 3 opciones consideradas eran: (A) 9 archivos = 3 ángulos × 3 email_types — sobre-fragmentación inviable; (B) marcadores condicionales tipo `<!-- if email_type=decisor -->` en el .md con selección en el worker — frágil al editar prompt y código simultáneamente; (C) un bloque "instrucciones por email_type" en el system + el LLM se autoregula leyendo `{email_type}` del user template — más simple, robusto a añadir un cuarto email_type futuro. **Decisión: C.** El smoke de paso 4b validó que Sonnet 4.6 sigue condicionales sin problema (research_prospect aplicó la regla "personas_extraidas solo con nombre+cargo claros, no inventes el cargo aunque sepas el nombre" sin desviación). Si en algún futuro el LLM ignora la condicional, hay refactor a B disponible.

**Estructura común a los 3 ángulos.** Identidad Gonzalo, reglas de tono no negociables (sin emojis ni "!", profesional pero cercano, condicional al hablar de DEMIN, ≤130 palabras body en opening/reframe y ≤100 en closing, asunto ≤6 palabras), reglas no-invento (Apéndice A reglas 3 y 4), bloque condicional con 3 patrones de apertura por email_type incluyendo ejemplos textuales para anclar el estilo, output JSON con `subject` + `body` + `razonamiento_breve` y prohibición explícita de markdown/code fences.

**Sub-objetivos diferenciadores (la parte que cambia entre los 3 archivos):**

- **opening** — primer toque (`step_index=0`). Presentación breve de DEMIN anclada en lo que hace la empresa concreta. Elige UN hook de los `hooks_de_personalizacion` que mejor case con `tipo_actividad_concreta` — instrucción explícita de NO usar los tres ("uno bien elegido vale más que tres mencionados de paso"). Propone conversación corta (15-20 min), NO venta. Asunto orientado a la empresa o al hook elegido, NO a DEMIN. **Sin `{correos_previos}`** en user template — es el primer toque y no hay correos previos que pasarle al LLM.
- **reframe** — segundo toque, día +4 (`step_index=1`). Reconocer la posibilidad real de que no hayan visto el primer correo o de que no fuera buen momento — sin presionar, sin reproches. **Hook B distinto del A del opening** — instrucción explícita "si en el opening usaste el hook A, en este reframe usa el hook B distinto. NO repitas el mismo gancho — eso convierte el reframe en un recordatorio molesto". El LLM lee el opening en `{correos_previos}` para ejecutar esta regla. Asunto distinto al del opening.
- **closing** — tercer toque, día +10 (`step_index=2`). Cierre cortés con opción explícita de "no insistir" como gesto de respeto. **Pregunta sí/no estructurante** que fuerza categorización del prospecto entre "más adelante" y "descartado definitivamente". Confirmación PM-side: este framing tiene valor estructural más allá del paso 5 — alimenta directamente el clasificador de respuestas (§11, 6 categorías) y la lógica de re-engage 60d/90d (D13). Sin esta pregunta, el clasificador trabaja sobre silencio ambiguo y la categorización entre `no_ahora` y `no_interesado` es heurística pura. La formulación canónica del prompt es "¿es algo que pueda interesar más adelante o lo descartamos definitivamente?" — el LLM puede adaptarla al tono pero las dos opciones excluyentes son obligatorias. Body ≤100 palabras, el más corto de los tres.

**Tests (53 nuevos, 336 totales verdes).** `tests/test_prompts_generate_email.py` cubre invariantes estructurales del archivo .md sin LLM real: existencia + parsing en `## System` y `## User template`, todas las 9 variables comunes en cada user template (`{nombre}`, `{email_type}`, `{nombre_destinatario}`, `{cargo_destinatario}`, `{tipo_actividad_concreta}`, `{tipo_obra_que_hacen}`, `{proyectos_recientes}`, `{hooks_de_personalizacion}`, `{kb_chunks}`), `{correos_previos}` SOLO en reframe y closing, los 3 valores de `email_type` mencionados en system para los 3 ángulos (validación de la decisión C de autoregulación), identidad DEMIN/Gonzalo, regla "sin emojis" explícita, las 3 keys del JSON output (`subject`, `body`, `razonamiento_breve`), instrucción de no-markdown, placeholders bien formados (regex contra `{var` huérfanos sin `}` cierre — pillar errores típicos de copy-paste), sub-objetivos diferenciadores (reframe instruye "hook B distinto", closing instruye dicotomía sí/no entre "más adelante" y "descartar"), límite de body 100 vs 130 palabras, cabecera con versión (regla 8). Sin mypy aplicable — paso 5 no añade código Python.

**Sin smoke LLM en paso 5 (decisión consciente).** La señal "el prompt produce JSON parseable y prosa coherente" sobre data dummy (contact dummy + research dummy + KB dummy) es parcial: distingue prosa decente de prosa rota, pero NO distingue prosa decente sobre research auténtico de prosa decente sobre research sintético. La validación que de verdad importa para cerrar Sprint 4 (¿Gonzalo aprobaría este correo?) la dará paso 6 sobre 5 T3 reales con HITL completo, así que un paso intermedio con dummies no agregaría señal distinta — solo retrasaría el filtro real. El coste ($0.015) era despreciable, pero la decisión no es de coste sino de qué señal aporta el paso. Por eso paso 5 cierra solo con tests estructurales, y paso 6 hereda el filtro de calidad literaria.

**Anotaciones operativas in flight (PM notas tras los pasos 4 y 4b)** ya integradas en §14:

- **Paso 6 — monitor de falsos positivos classify_descr**: si en las 5 T3 reales aparece >1 falso positivo similar a RUTHERFORD ESPAÑOLA (piscinas con `ia_fit='fit'`), el clasificador IA de Sprint 3 necesita iterar (Haiku→Sonnet, prompt más estricto, o muestreo manual) ANTES de paso 7.
- **Paso 8 — verificación cobertura `personas_extraidas`**: el smoke de paso 4b dejó 0/2 OK con personas enriquecidas. Threshold operativo: si <30% de las T2 con research OK terminan con `personas_extraidas` no vacío, el supuesto D21 (hit rate 20%→50-60%) cae y la decisión arquitectónica del paso 9 tiene que cruzar explícitamente esta señal.
- **Paso 9 — cruces obligatorios + saneamiento mypy**: además de los dos cruces anteriores, pasada de saneamiento mypy `--strict` sobre `shared/` (3 deudas acumuladas en `config.py:94` + `llm.py:72` + `llm.py:190`, todas triviales individualmente pero acumuladas en módulo transversal merecen un fix conjunto al cerrar Sprint 4 o como primer paso de Sprint 5).

### 2026-05-06 — Cierre Sprint 4 paso 6: generate_draft + hitl_review + /pipeline + smoke E2E

Opción C confirmada PM-side: cierre del paso 6 con 4 sub-componentes en lugar de la pantalla Approval Queue completa (que difiere a paso 7). 3 commits de código + 1 docs.

**Pre-check Hunter quota (gate obligatorio).** `apps/workers/scripts/check_hunter_quota.py` llama `GET /v2/account` (no consume búsquedas) y aborta con código 3 si quedan <10 disponibles antes del smoke. Confirmación PM-side: Hunter pago no se activa por iniciativa propia. **Hallazgo importante**: el plan Free de Hunter da **50 búsquedas/mes**, no 25 como las entradas §19 anteriores asumían (Frente C / paso 4 / paso 4b). El pre-check antes del smoke devolvió `requests.searches.available=50`, `used=13`, `remaining=37`, `reset_date='2026-06-06'`. Memoria `project_hunter_paid_plan.md` actualizada con el dato correcto. La asunción de 25/mes nunca se verificó contra la API; el plan Free real es el doble. Esto reduce la urgencia de activar pago, pero NO la elimina — paso 7 con cap 10/día consume ~70/semana, agota Free en 5 días aún con 50/mes.

**1. `apps/workers/pipeline/generate_draft.py` (commit b44913b, ~600 líneas).** Worker que itera contacts cuya `companies.research_done_at IS NOT NULL` (sin `_failed`) del tier solicitado, recupera 5 chunks del KB con Voyage query embedding + pgvector cosine similarity, carga el prompt versionado del ángulo solicitado, llama Sonnet 4.6, valida post-generación según §10.3 (4 reglas — body 50-180 palabras, subject 3-8, sin emojis ni `!`, sin patrones tipo "garantiz"/"en N días"/"por N €"; la 5ª regla "no nombres inventados" la cubre el HITL humano), e inserta en `messages.status='drafted'` con `research_snapshot` que incluye `_failed_validations` si aplica. Hasta 2 reintentos LLM si validación falla; tras retries el draft entra igualmente con marca para que el HITL decida (en lugar de descartarlo silenciosamente). **Single-worker secuencial por defecto** (Voyage Free 3 RPM impone ritmo de ~22s entre embeds; paralelizar saturaría rate limit, mismo patrón que `embed_documents.py` y `smoke_kb_retrieval.py` de Sprint 1). Cap defensivo `--max-cost-usd 5.0`. Idempotente con `--rerun` que ignora el filtro de "no message previo para (contact, step_index)".

**2. `apps/workers/scripts/hitl_review.py` (commit 64c2a8e, ~370 líneas).** Terminal interactivo que itera `messages.status='drafted'` ordenados por `(company.nif, step_index, created_at)` y muestra cada draft con contexto + prompt de acción `[a/e/r/x/s/q]`. Editor inline con marcador `EOF` (multiplataforma — no requiere `$EDITOR`/`notepad`/`vim`, lee stdin hasta una línea con sólo "EOF"). Acciones: aprobar / editar+aprobar / regenerar (cancela el draft con `_cancelled_reason='regenerated_in_hitl'` via `jsonb_set`, llama `process_one_contact`, re-presenta el nuevo) / rechazar+excluir contact (Apéndice A regla 2 — opt-out permanente) / saltar / quit. **NO envía emails** — el envío real es paso 7. Paso 6 valida que el flujo HITL funciona end-to-end y que los drafts son aprobables.

**3. Pantalla `/pipeline` read-only en dashboard (commit 66166b2).** Sustituye el `PlaceholderPanel` del scaffold. Patrón espejo de `/kb`: server components puros con `createAdminClient`, sin tests UI, sin JS adicional para filtros (form HTML estándar con query params). Lista paginada 50/página con filtros tier + ia_fit + búsqueda por NIF/nombre, columnas NIF + empresa (link a detalle) + tier + ia_fit + ia_fit_reason truncado + localidad + web (link externo) + count contacts + count messages por status (compacto "dra=N app=N sen=N") + research_done_at. Ruta detalle `/pipeline/[id]` con header (nombre + NIF + tier + ia_fit + localidad + web + ia_fit_reason completo), 3 cards (facturación k€, descripción SABI, research dossier), tabla de contacts con todos los campos, lista de messages cronológica desc con metadata + asunto + body completo. `ResearchBlock` renderiza el JSON de `research_data` por secciones, manejo defensivo de `_failed` (destructive styling) y `_warning` (amber). `next build` compila ambas rutas correctamente; las 3 errores `tsc` preexistentes en `scripts/smoke_kb_e2e.ts` (no scope paso 6) quedan anotadas como deuda técnica nueva en §14.

**4. Smoke E2E real en dev sobre 5 T3 (88 tests nuevos, 424 totales verdes; mypy --strict limpio en `pipeline/generate_draft.py` y `scripts/hitl_review.py`).** Cherry-pick determinístico (los workers ordenan por NIF asc + LIMIT 5):

| NIF | empresa | web | resultado research | resultado find_contacts | resultado generate_draft |
|---|---|---|---|---|---|
| `A41974684` | SERVISHOP MANLOGIST | servishop.com | OK | 0 emails (Hunter sin cobertura) | — |
| `A78062601` | LENA CONSTRUCCIONES | nozar.es | OK | (ya tenía 3 contacts del paso 4) | **3 drafts OK [BUG: ver paso 6.5]** |
| `A80454598` | SB 63 (pinnea) | pinnea.com | OK | 0 emails | — |
| `B02707198` | TRAZO REHABILITACIONES | trazo.net | OK | 0 emails | — |
| `B05294269` | CUADRATURA SOLUCIONES | cuadraturasoluciones.com | OK | 0 emails | — |
| `B06973846` | NOG INTERIORISMO (extra +1 research para tener 2 empresas con drafts) | noginteriorismo.com | OK + **3 personas_extraidas** | 1 contact corporativo_pequeno | **1 draft OK** |

Métricas reales del smoke:
- research_prospect: **6/6 OK** ($0.10 USD, 0 _failed, 1 thin_html_possibly_spa, 0+3 personas extraídas — primera evidencia positiva del cruce D21).
- find_contacts: cobertura Hunter T3 efectiva = **20%** (1 contact en 5 empresas + 1 más al añadir NOG; 6 búsquedas Hunter consumidas, 37→31 restantes). **Frente E proyectaba 80%** sobre 5 T3 — divergencia significativa que merece análisis en paso 9.
- generate_draft: **4/4 drafts OK** ($0.077 USD, 0 con validation warnings, 18.661 tokens in + 1.390 out). Las 3 variantes por `email_type` aplican correctamente en producción (decisión C de paso 5 validada con datos reales): 1 nominal-con-cargo (jaime.nozaleda Director de Business Development), 1 nominal-sin-cargo (zaragoza, A3 T3), 2 corporativo_pequeno (info@nozar, administracion@noginteriorismo). **[CORREGIDO en paso 6.5, 2026-05-08: este reporte erróneamente describió el escenario como deseado. La realidad es que generar 3 drafts simultáneos a 3 contacts del mismo dominio (nozar.es) es un BUG operativo — viola D18 + §9.2 + §10.1 (cadencia 1:1 contacto-secuencia) y degrada deliverability del primer batch del paso 7. Bug detectado por auditoría humana antes de autorizar paso 7. Adicionalmente este reporte indicó "primary=jaime" cuando la BD muestra primary=zaragoza — error de transcripción mío al redactar §19. Tras paso 6.5: jaime + info quedan `cancelled` con `_cancelled_reason='paso65_fix_solo_primary'` y `_cancelled_from_status='approved'`; queda 1 draft vivo en LENA = zaragoza primary actual. Paso 6.6 abre el sub-issue de si zaragoza (sin cargo) debería ser primary sobre jaime (con cargo Business Development Director) — al cerrar paso 6.6 puede revertirse.]**
- Calidad cualitativa de los drafts: hooks anclados al material auténtico del research ("Tabit IV en El Cañaveral", "Torre de Poniente, Residencial Marina", "espacios comerciales como el de Chamberí"), tono Gonzalo (sin emojis, sin "!", condicional al hablar de DEMIN, ≤130 palabras body), cierre con pregunta directa de conversación corta (15-20 min). 0 invenciones detectadas en muestra.
- Coste total smoke E2E: **$0.18 USD + 6 búsquedas Hunter**.

**Señales operativas a cruzar en paso 9 (anotadas in flight en §14):**

- **Falsos positivos classify_descr en T3 — 2-3 candidatos visibles**. SERVISHOP MANLOGIST (servishop.com) y SB 63 (pinnea.com) tienen research OK pero Hunter no encontró emails — podría ser ICP fit pero negocio low-profile, o falso positivo del clasificador. Pendiente auditoría humana del research dossier para confirmar/descartar. RUTHERFORD ESPAÑOLA del paso 4b (piscinas) sigue como tercer FP probable. **Si la auditoría confirma >1 FP**, classify_descr necesita iterar antes de paso 7 — Lección 19 trigger.
- **Cobertura Hunter T3 efectiva 20% vs 80% Frente E**. La divergencia es grande y merece análisis: ¿muestra estadísticamente distinta? ¿el ICP real T3 con web tiene peor cobertura de lo que el sample del Frente C sugería? Se cruza en paso 9 con el dato de paso 7 (cap 10/día sobre T3) cuando haya volumen estadístico real.
- **`personas_extraidas` cobertura hetero**: 0/5 en las T3 cherry-pick principales + 3/3 en NOG INTERIORISMO. La cobertura no es plana — depende de si la web tiene sección "Equipo" con cargos literales. La señal del paso 4b (T2 con 0/2) se confirma. Threshold operativo del paso 8 (<30% → revisar D21) sigue pertinente.

**Próximos pasos con esto:**

- **Auditoría humana inmediata**: Alberto/Gonzalo corren `python -m scripts.hitl_review --env dev` y revisan los 4 drafts. La aprobación/rechazo en HITL valida la UX terminal end-to-end. Si Gonzalo aprueba ≥2 de 4 drafts sin editar, el paso 5 (prompts) se confirma como production-ready.
- **Decisión sobre Hunter pago**: pendiente para arranque de paso 7. Memoria `project_hunter_paid_plan.md` con dato corregido (50/mes).

### 2026-05-08 — Paso 6.5: fix bug envío simultáneo a múltiples contacts/empresa + Lección 28

**Bug detectado en auditoría humana** (Alberto, rol PM) tras cerrar paso 6: el smoke E2E generó 3 drafts simultáneos a 3 direcciones del mismo dominio (jaime + zaragoza + info @ nozar.es) en LENA CONSTRUCCIONES. Operativamente: spam interno para el prospecto + señal de spam para los filtros del receptor + degradación de los primeros 100 envíos del paso 7 (Lección 27).

**Diagnóstico** (auditoría completa documentada en sesión 2026-05-08):
- `generate_draft.py:fetch_pending_contacts` filtraba por las condiciones obvias (research OK, no opt-out, no message previo del mismo step_index) **pero NO por `is_primary=true`**. Cogía todos los contacts elegibles → 1 draft por cada uno.
- `find_contacts.py` **sí asignaba `is_primary=true` correctamente** al candidato de mejor priority por empresa. El bug era de paso 6, no de paso 4.
- El plan ya autorizaba el comportamiento correcto (D18 "menos pierde el lead **si el primero no responde**" + §8.5 "Primero por prioridad → `is_primary=true`" + §9.2 "**3 toques por contacto**" + §10.1 "Carga **del contacto** + empresa") — pero §10.1 no decía explícitamente "filtra por is_primary". Mi planificación de paso 6 nunca cruzó D18+§8.5+§9.2 con la query de selección.
- Suite de 88 tests del paso 6 cubrió el comportamiento erróneo como si fuera correcto: parametrizó `email_type` decisor/nominal/corporativo pero NUNCA verificó que `fetch_pending_contacts` respeta `is_primary`.

**Fix aplicado:**
- **Código** (`apps/workers/pipeline/generate_draft.py`): `AND ct.is_primary = true` añadido al WHERE de `fetch_pending_contacts` + docstring extendido con justificación cruzada a D18+§9.2+§10.1.
- **Test** (`apps/workers/tests/test_integration_generate_draft.py`, marker `@pytest.mark.integration`): test integración nuevo con BD dev real que inserta company + 2 contacts (1 primary + 1 no) y verifica que `fetch_pending_contacts` devuelve solo el primary. Más test secundario que cubre opt-out > is_primary. Marker `integration` registrado en `pyproject.toml` con `addopts = "-m 'not integration'"` (excluido por default; opt-in via `pytest -m integration`).
- **Limpieza datos dev** (`apps/workers/scripts/cleanup_paso65.py`): UPDATE quirúrgico sobre los 4 drafts del smoke paso 6, cancelando los 2 cuyo contact no era is_primary (jaime + info de LENA). PM-confirmed: las aprobaciones humanas previas (status='approved') fueron de calidad de prosa, no de coherencia operativa — el bug se detectó después. Las 4 aprobaciones se preservan en event trail con `status='cancelled'` + `_cancelled_reason='paso65_fix_solo_primary'` + `_cancelled_from_status='approved'`. Estado tras cleanup: 2 drafts vivos (zaragoza LENA primary + administracion NOG primary).
- **Plan**:
  - §10.1 paso 1: explícito ahora — "**El worker filtra por `contacts.is_primary=true`** (D18 + §9.2: cadencia 1:1 contacto-secuencia, NO envío simultáneo a varios contacts de la misma empresa)".
  - §8.5 selección/priorización: añadida frase aclaratoria — "Los candidatos no-primary son respaldo manual, NO envío automático".
  - §19 cierre paso 6: añadidos dos `[CORREGIDO ...]` inline (uno tildando "3 drafts OK" como BUG en la tabla por empresa, otro corrigiendo la transcripción errónea "primary=jaime" → "primary=zaragoza" + apuntando paso 6.6). Trazabilidad sobre limpieza: la entrada original NO se reescribe silenciosamente; se anota la corrección.
- **Lección 28** en `tasks/lessons.md`: meta-patrón de proceso. La causa raíz no es la línea de código que faltaba; es de proceso — al planificar el paso 6 leí "el worker itera contacts" en §10.1 y construí los filtros consultando solo §10 + §6.1. NO crucé esa decisión con D18 + §8.5 + §9.2 que apuntaban inequívocamente a "1 contact activo por empresa". Regla resultante: cuando un worker itere sobre una entidad, **enumerar las decisiones del plan que afectan a esa entidad** (no solo la sección donde el worker está documentado) y traducir cada una a un filtro o aserción concreta. Tests de SQL de selección requieren cobertura de filtro explícita (insert 2 con condición distinta, verificar que solo 1 aparece). Auditoría humana ANTES de autorizar acciones operativas con efecto externo (envío real, integraciones API, mutación downstream) — la validación E2E técnica es necesaria pero insuficiente.

**Verificación**:
- Suite default 424/424 verde + 2 deselected (los integration excluidos por default, ejecutables con `pytest -m integration` y verdes 2/2).
- mypy `--strict pipeline/generate_draft.py` limpio (deudas pre-existentes en `shared/` siguen igual).
- Estado dev tras cleanup verificado con `scripts/debug_contact_state.py`: 2 messages vivos (zaragoza LENA approved + administracion NOG approved), 2 cancelled con razón trazable.

**Sub-issue abierto que paso 6.5 NO arregla:**

El primary actual de LENA es zaragoza (nominal **sin cargo**) en lugar de jaime (nominal **con cargo** "Business Development Director"). `find_contacts.assign_priority` empata ambos en prio=3 dentro del bucket nominal y resuelve por confidence Hunter, donde zaragoza ganó. Intuitivamente jaime es mejor candidato (cargo claro = perfil decisor). **Paso 6.6 abierto inmediatamente tras 6.5**: revisar `assign_priority` para que dentro del bucket nominal, "nominal-con-cargo" gane a "nominal-sin-cargo" antes que el desempate por confidence. Re-correr `assign_priority` sobre los contacts ya existentes en dev (probablemente vía recompute de `email_priority` + `is_primary` por empresa) para que el cleanup del 6.5 quede coherente. Paso 7 sigue bloqueado hasta que 6.6 cierre y la auditoría humana sobre el set final de drafts (1 jaime LENA + 1 administracion NOG, esperado tras 6.6) confirme que ahora hay 2 drafts vivos correctos.

**Coste paso 6.5**: ~70 min trabajo (estimación inicial cumplida). Sin coste LLM (tests + cleanup SQL puros). 0 búsquedas Hunter consumidas (Free quota sigue en 31).

### 2026-05-12 — Paso 6.6: assign_priority distingue nominal-con-cargo + Lección 29

**Sub-issue heredado del paso 6.5 cerrado.** El cleanup del 6.5 dejó como primary de LENA al nominal-sin-cargo zaragoza@nozar.es en lugar del nominal-con-cargo jaime.nozaleda@nozar.es (cargo "Business Development Director"). Ambos contacts caían en `email_priority=3` (bucket nominal único) y `select_top_candidates` resolvía el empate por confidence Hunter desc — donde zaragoza ganaba. La auditoría humana del 6.5 identificó esto como sub-bug y autorizó paso 6.6 inmediato antes de paso 7. Bloquea **calidad del paso 7** (reply rate del primer batch, dispara gate <3% Lección 27) más que seguridad operativa.

**Diagnóstico:**
- `find_contacts.assign_priority` mapeaba `nominal → 3` sin distinguir presencia de cargo, con el desempate cayendo en `confidence desc` del email finder. El plan §8.5 punto 2 sí distinguía conceptualmente "nominal con cargo" vs "nominal sin cargo" (regla A3 T2 descarta sin cargo) pero NO lo formalizaba en la priorización numérica para T1/T3/T4.
- El sort `(priority asc, confidence desc)` enterraba la distinción operativa: confidence mide calidad del email (sintaxis, fuente Hunter), no calidad del rol. Cuando ambas señales compiten dentro del mismo bucket, rol manda — pero el sort no lo decía. **Patrón meta capturado como Lección 29: tiebreaker silencioso en sort_key = bug en espera.**
- El plan no respaldaba literalmente "nominal-con-cargo > nominal-sin-cargo" — criterio de parada 2 (regla 9 Apéndice A) activado durante planificación. Se añadió como refinamiento explícito de D18 + §8.5 antes de codear.

**Fix aplicado:**
- **Schema** (migration 10, `infra/supabase/migrations/20260512120000_10_email_priority_extend_to_5.sql`): `CHECK (email_priority BETWEEN 1 AND 5)` reemplaza el `BETWEEN 1 AND 4` previo. Default 4→5. COMMENT actualizado con la enumeración nueva. No mueve datos.
- **Código** (`apps/workers/pipeline/find_contacts.py`): `assign_priority` cambia firma a `(email_type, confidence, position=None)`. Lógica nueva:
  - 1 = decisor confidence≥80 (sin cambio)
  - 2 = decisor confidence<80 / None (sin cambio)
  - **3 = nominal CON cargo identificado** (position no vacío tras `enrich_with_personas_extraidas`)
  - **4 = nominal SIN cargo** (nuevo bucket)
  - **5 = corporativo_pequeno** (antes 4)
  
  `classify_and_filter` pasa `enriched.position` a `assign_priority`. `select_top_candidates` no se toca (el sort `(priority asc, confidence desc)` ya distingue gracias al bucket más fino).
- **Tests** (`apps/workers/tests/test_find_contacts.py`): `test_assign_priority_table` parametrizada con 16 casos cubriendo position vacío/None/strip-vacío + presencia de cargo en cada tipo. Test nuevo `test_assign_priority_nominal_con_cargo_gana_a_sin_cargo` con el caso real LENA. Test nuevo `test_select_top_nominal_con_cargo_gana_a_nominal_sin_cargo_alto_conf` como regresión operativa (jaime priority=3 conf=60 vs zaragoza priority=4 conf=95 → jaime primero, sin depender de confidence). Tests existentes actualizados (`test_classify_and_filter_t3_*` extendido para incluir el caso nominal-sin-cargo separado; `test_classify_and_filter_t1_accepts_a3_nominal_sin_cargo` ahora verifica priority=4).
- **Re-cómputo dev** (`apps/workers/scripts/recompute_priorities_paso66.py`, ~230 líneas, `--dry-run` por defecto en planificación). Lee contacts JOIN companies, recalcula `email_priority` con la regla nueva (sin necesitar `confidence` — preserva decisor 1/2 del valor antiguo, llama `assign_priority` para nominal usando solo `cargo`, fuerza 5 en corporativo), reasigna `is_primary` por empresa con orden `(new_priority asc, email asc)` determinístico. Idempotente. Aplicado en dev: 3 priority updates (zaragoza 3→4, info 4→5, administracion 4→5) + 2 is_primary updates (jaime False→True, zaragoza True→False). Segunda corrida = 0 cambios (idempotencia verificada).
- **Cleanup messages** (`apps/workers/scripts/cleanup_paso66.py`, espejo de `cleanup_paso65.py` con razón distinta). El draft `status='approved'` de zaragoza queda incoherente tras la reasignación de primary (zaragoza ya no es primary, paso 7 enviaría a non-primary = bug 6.5 reabierto). Cancelado con `_cancelled_reason='paso66_primary_reassign'` + `_cancelled_from_status='approved'` preservando event trail. La aprobación humana original de zaragoza en paso 6.5 fue de calidad de prosa, no de coherencia operativa post-recompute — misma justificación que paso 6.5 aplicada a la cancelación de zaragoza.
- **Regenera draft jaime** (`generate_draft --env dev --tier T3 --rerun --limit 1`): tokens 4653 in + 326 out, $0.0188 LLM, validación post-generación 100% OK (0 warnings, 0 failed). Apertura nominal del prompt paso 5 aplicada correctamente (`email_type='nominal'`, ángulo opening). Subject 5 palabras, body ~120 palabras, hooks reales del research ("Tabit IV en El Cañaveral", "Residencial Marina en Murcia"). PM aprobará formalmente via `hitl_review --env dev` en su terminal post-cierre técnico.
- **Plan**:
  - §8.5 punto 4: reescrito explícitamente con priority 1..5 y sub-distinción nominal + justificación operativa (cargo claro > confidence en el bucket nominal).
  - §8.5 bullet "Selección y priorización (D18 + D20)" detallado: actualizado paralelamente con la enumeración 1..5 y el caso LENA como justificación empírica.
  - §3 D18: nota inline de refinamiento paso 6.6 (no D23 nueva — preserva trazabilidad de la cadena de decisiones de priorización en una sola entrada).
- **Lección 29** en `tasks/lessons.md`: meta-patrón sobre tiebreaker silencioso en sort. Distinto de Lección 28 (que cubrió "cruzar filtros con cadena de decisiones del plan"). Lección 29 cubre el caso específico de sort sobre entidades con múltiples señales operativas: cuando el plan distingue dimensiones cualitativas (cargo vs confidence email), el sort debe ponerlas en orden de **discriminación operativa** (rol manda sobre email), no de **disponibilidad numérica** (confidence siempre disponible, cargo a veces).

**Observación cualitativa del PM (no bloquea):** la apertura del draft nuevo de jaime ("Jaime, te escribo a ti porque encajaba con el perfil que puede tener esta conversación en Lena Construcciones") es ligeramente más vaga que la del draft cancelado original de paso 6.5 ("perfil que coordina el desarrollo de nuevas promociones"). Ambos pasan §10.3 limpio. No regeneramos — pero si en paso 7-8 vemos patrón sistemático de aperturas vagas vs específicas en `email_type='nominal'`, iteramos el prompt `generate_email_opening.md` en paso 9.

**Verificación:**
- Suite default verde: 431/431 passed + 2 deselected (integration). 7 tests nuevos sobre los 424 del cierre paso 6.5.
- Migration 10 aplicada en dev (CHECK 1..5, default 5). Verificación: `pg_constraint` confirma `contacts_email_priority_check = CHECK (email_priority BETWEEN 1 AND 5)`.
- Estado dev tras recompute + cleanup + regenerate (vía `scripts/debug_contact_state.py`):
  - LENA jaime.nozaleda@nozar.es — type=nominal prio=3 **is_primary=True** msg=06f63306 **status=drafted** (nuevo, pendiente HITL PM)
  - LENA zaragoza@nozar.es — type=nominal prio=4 is_primary=False status=cancelled (paso66_primary_reassign)
  - LENA info@nozar.es — type=corporativo_pequeno prio=5 is_primary=False status=cancelled (paso65)
  - NOG administracion@noginteriorismo.com — type=corporativo_pequeno prio=5 is_primary=True status=approved (sin cambio operativo desde paso 6.5)

**Pendiente de cierre formal:**
- Aplicar migration 10 en prod (CHECK 1..5, default 5). Prod tiene 0 contacts (pre-flight `SELECT count(*) FROM contacts` confirmó suposición "solo dev"), así que la migración es schema-only y segura. Confirmación interactiva `yes` requerida por `apply_migrations.py --env prod`.
- HITL approval del draft jaime msg=06f63306 vía `hitl_review --env dev` por el PM.

**Sub-issue 6.5/6.6 cerrado:** la cadena D18 + §8.5 + §9.2 + §10.1 + is_primary queda ahora coherente desde el plan hasta el código. Auditoría humana antes de paso 7 valida que hay **2 drafts vivos correctos** (jaime LENA primary + administracion NOG primary, ambos con prosa aprobada por humano).

**Coste paso 6.6:** ~75 min trabajo. **$0.0188 LLM** (1 draft regenerado). 0 búsquedas Hunter (recompute es SQL puro). 0 cambios prod (pendiente migration 10 trivial).

### 2026-05-12 — Paso 7 (pre-requisitos): construcción técnica completa + Lección 30 + Hunter Starter contratado

**Alcance del cierre:** todos los pre-requisitos técnicos de paso 7 que Code puede construir sin bloqueadores humanos. El envío real productivo NO arranca aquí — bloqueado por B1 (Gmail OAuth), B2 (despliegue dashboard prod), B4 (ALLOWED_EMAILS prod) y B5 (smoke E2E pre-envío real con `--override-to`).

**Construido (3 bloques, 11 sub-tareas, ~7h, suite 489 verde + 2 deselected):**

**Bloque 0 — Migration 11 + seeds idempotentes** (commit `feat`):
- `infra/supabase/migrations/20260512130000_11_seed_outreach_and_clean_seq_comment.sql`. Seeds: 1 mailbox (`gonzalo.perez@demingroupmadrid.com`, daily_cap=20, warmup_status='ready', status='active', oauth_refresh_token_encrypted=NULL pendiente B1), 1 sequence (`demin_v1` con steps D+0/D+4/D+10 alineados §9.2), 1 campaign (`T3 Semana 1`). Limpia comentario obsoleto de migration 02 que aún hablaba de D+0/D+12/D+30 (heredado del Bloque A pre-D22). NO añade 'paused' al CHECK de messages.status (decisión PM 1.4 paso 7 opción A: pausa solo a nivel mailbox).
- Aplicada en dev y prod (`apply_migrations.py`). Verificado con SELECT post-apply.

**Bloque 1 — Workers de envío + auto-pausa** (mismo commit feat):
- `shared/gmail_adapter.py` (~290 líneas): cliente Gmail API por buzón. OAuth refresh_token → access_token con cache in-memory y refresh automático cuando quedan <60s. POST a `/messages/send` con RFC 2822 base64 url-encoded, headers In-Reply-To/References para follow-ups. Tenacity retry 3x sobre 429/5xx/timeout, 401 levanta `GmailAuthError` sin retry. SendResult dataclass con `success`/`gmail_message_id`/`error`/`http_status`. 13 tests MockTransport (sin credenciales reales).
- `outreach/send_gmail.py` (~360 líneas): worker que envía messages approved. Guards: ventana 9-13/15-18 Madrid (`zoneinfo.ZoneInfo("Europe/Madrid")`, weekday only — fines de semana skip silencioso), mailbox active con refresh_token, cap rolling 24h via `count(events.type='message_sent')`. Footer opt-out + firma anexados al body (decisión PM 1.3 paso 7: NO en generate_draft). Jitter aleatorio 0-N min entre envíos (default 5). `--override-to` para smoke pre-envío real (decisión PM 1.5 paso 7). Clasifica 4xx no-auth en bounce sync vs failed según keywords ("Invalid To", "Recipient", "domain", etc.). 21 tests puros (is_business_hours, build_full_body, classify_error_as_bounce + footer).
- `outreach/follow_ups.py` (~190 líneas): programa step+1 (reframe D+4, closing D+10) cuando step previo fue sent y sin reply. Lee sequences.steps. Llama `pipeline.generate_draft.process_one_contact` + `insert_draft` reusando lógica del paso 6. 3 tests puros (estimate_cost_usd + FollowUpStep).
- `outreach/auto_pause.py` (~150 líneas): cada mailbox active, calcula bounce/spam rates 7d via events. Threshold §9.4 (bounce >2%, spam >0.1%) con sample mínimo 50 envíos. Pausa solo `mailboxes.status='paused'` + `pause_reason` (decisión PM 1.4 opción A) + INSERT event `mailbox_paused`. 11 tests puros (decide_pause_reason + MailboxStats properties).
- `shared/config.py`: añadidos `GMAIL_OAUTH_CLIENT_ID`/`SECRET`/`REFRESH_TOKEN` + `SENDING_DOMAIN` (todos opcionales hasta B1).
- Limpieza: borrado `outreach/generate_draft.py` (stub duplicado del worker real en `pipeline/`).
- **Total bloque 1**: 48 tests nuevos (default suite pasa de 431 a 489). mypy --strict limpio en código nuevo (3 deudas pre-existentes en `shared/config.py:104` + `shared/llm.py:72,190` intactas — §14 deuda técnica).

**Bloque 2 — Dashboard pantallas funcionales** (commit `feat dashboard`):
- `/approval-queue` (sustituye PlaceholderPanel): server actions `approveMessageAction` + `rejectAndOptoutAction`. Client component `<ApprovalQueueContent>` con keyboard nav (j/k navegar, a aprobar, e editar+aprobar, x rechazar+optout, s skip). Editor inline subject + body. Aprobar registra `approved_by=user.email`+`approved_at=now()`. Rechazar marca contact `is_optout=true` + opt-out permanente (Apéndice A regla 2) + message cancelled con razón `hitl_rejected`. Cero regenerar via web — si Gonzalo quiere nueva prosa, edita inline (decisión simplicidad paso 7; regenerar web es feature Fase 3 cuando haya cola de jobs).
- `/metrics` (sustituye PlaceholderPanel): RSC read-only. Embudo por messages.status (drafted/approved/scheduled/sent/bounced/failed/cancelled). Rates 7d (bounce/fail/reply via events + replies). Coste mes (SUM messages.generation_cost_usd month-to-date) + avg coste/draft. Bounce rate marca tono destructive si supera 2% con sample ≥50. Sin gráficas (refinamiento Fase 3 con datos reales).
- `/settings` (sustituye PlaceholderPanel): RSC + server actions `emergencyPauseAction` + `resumeAllAction`. Pausa de emergencia (botón rojo + window.confirm) UPDATE mailboxes status='paused' WHERE active + INSERT events mailbox_paused. Reanudar todos UPDATE active + INSERT events mailbox_resumed. Apéndice A regla 6 reforzada en UI (texto explícito "has investigado el motivo antes de reanudar?"). Sin toggle HITL/autónomo, sin caps editables, sin horario configurable — Fase 3.
- `tsc --noEmit` limpio en código nuevo (3 errores pre-existentes en `scripts/smoke_kb_e2e.ts` intactos — §14 deuda).

**Bloque 3 — Plan + Lección** (commit `docs`):
- `tasks/todo.md` §9.3: rampa nueva cap 20/25/30/40 (Sem 1→4+) con justificación inline (Lección 30).
- `tasks/todo.md` §3 D22: nota inline "refinamiento paso 7 — cap 20/día Semana 1 tras Lemwarm score 92".
- `tasks/todo.md` §14 paso 7: bullet reescrito con sub-tareas marcadas + bloqueadores humanos B1-B6 + pre-condiciones operativas heredadas paso 6.5/6.6 + **condición activación `verify_emails.py` durante paso 7** (si bounce >1% en primer batch 50 → construir antes paso 8, decisión PM 1.2 paso 7).
- `tasks/todo.md` §17: Hunter Starter (~30-45€/mes) activado, total recurrente paso 7+ = 105-140€/mes. Margen vs techo D15 (150€/mes) sigue holgado.
- `tasks/lessons.md` Lección 30: meta-patrón "los datos reales del warmup superan las asunciones conservadoras del plan original cuando estaba pre-warmup". Distinta de Lección 29 (tiebreaker silencioso) y Lección 28 (cruzar filtros con decisiones). Lección 30 cubre el patrón inverso: el plan dice X conservador, los datos del proveedor dicen Y mejor — actualizar plan, no operar con X obsoleto.
- Esta entrada §19.

**Instrucciones B2 (PM, despliegue dashboard prod)**:

Cuando estés listo para activar `app.demingroupmadrid.com`:

1. **Vercel project nuevo** (separado del proyecto actual de `apps/web/`):
   - Crear nuevo proyecto Vercel apuntando a este repo, root directory `apps/dashboard`, build command `next build --turbopack`.
   - Domain: añadir `app.demingroupmadrid.com` en Project Settings → Domains.

2. **DNS Namecheap**:
   - Añadir CNAME: `app.demingroupmadrid.com` → `cname.vercel-dns.com` (Vercel te da el target exacto al añadir el domain).
   - TTL: Automatic (5 min) está bien para arranque.
   - Verificar `nslookup app.demingroupmadrid.com` resuelve a Vercel tras propagación (≤30 min usual, hasta 48h teórico).

3. **Env vars Vercel prod** (Project Settings → Environment Variables, scope = Production):
   - `NEXT_PUBLIC_SUPABASE_URL` = URL del proyecto Supabase **prod** (`demin-prod`, ref `stxicalzpwrcjpaqdkdb`). Formato `https://<ref>.supabase.co`.
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = anon key prod (Project Settings → API en Supabase prod).
   - `SUPABASE_SERVICE_ROLE_KEY` = secret key prod (Bitwarden `demin-supabase-prod-service-role`).
   - `ALLOWED_EMAILS` = `gonzalo.perez@demingroupmadrid.com,albertobueno10@gmail.com` (whitelist auth middleware — B4).
   - **NO añadir** las env vars de Gmail OAuth (`GMAIL_OAUTH_*`) — el dashboard no las usa directamente; los workers Python las leen de `.env.prod`. Tampoco `HUNTER_API_KEY` — solo workers.

4. **Verificación post-deploy**:
   - Visitar `https://app.demingroupmadrid.com/login`, login con magic link desde `gonzalo.perez@demingroupmadrid.com`. Debe redirigir a `/pipeline` tras click email.
   - Si el email no whitelisteado intenta login, debe redirigir a `/login?error=unauthorized`.
   - Visitar `/approval-queue` — debe mostrar "No hay drafts pendientes" (prod tiene 0 contacts hasta arrancar paso 7).
   - Visitar `/metrics` — debe mostrar embudo todo a 0.
   - Visitar `/settings` — mostrar mailbox `gonzalo.perez@demingroupmadrid.com` con status `active`, cap 20.

5. **Después de B2 verificado**: resolver B1 (Gmail OAuth) → seed `oauth_refresh_token_encrypted` en prod → smoke E2E con `--override-to albertobueno10@gmail.com` (B5) → primer batch productivo HITL Gonzalo (B6).

**Pendientes pre-envío real (orden esperado)**:

1. B3 — Hunter Starter API key (PM ya pagando 2026-05-12). Cuando llegue, integro en `.env.prod` + actualizo memoria + subo `DEFAULT_MAX_HUNTER_CALLS` de 20 a 100.
2. B1 — Gmail OAuth coordinación PM + Gonzalo. Resultado: refresh_token en `mailboxes.oauth_refresh_token_encrypted` (dev y prod).
3. B2 — Despliegue dashboard prod (PM, instrucciones arriba).
4. B4 — ALLOWED_EMAILS Vercel prod (parte de B2).
5. B5 — Smoke E2E con `--override-to albertobueno10@gmail.com` en dev. Verificar: OAuth flow, footer renderizado, gmail_message_id, evento sent. Coste estimado: $0 (re-aprovecha drafts existentes de paso 6.6) + 0 búsquedas Hunter.
6. B6 — Gonzalo HITL approval primer batch productivo en `/approval-queue` prod. Arranque envío real.

**Coste paso 7 (pre-envío real)**: ~7h trabajo + $0 LLM + 0 búsquedas Hunter consumidas + 0 envíos reales. Coste recurrente desde aquí: +Hunter Starter (~30-45€/mes) cuando B3 active. Total proyectado régimen Sprint 4 productivo: 105-140€/mes (§17).

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
