# DEMIN — Plan de construcción del sistema de captación automática

> **Documento maestro.** Es la fuente de verdad para Claude Code. Todo lo que no esté aquí no se hace sin preguntar al humano. Todo lo que esté aquí marcado como `[DECIDIDO]` no se cuestiona — son decisiones tomadas tras conversaciones largas; cambiarlas requiere consulta explícita.

**Estado:** plan v1.2 — sincronizado con cierre de Bloque A (dominio, embeddings, warmup, costes; ver §19)
**Última actualización:** 2026-04-29

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
Servicios de demolición interior: desmontaje de falsos techos, tabiquería, vaciados técnicos, gestión de escombros. Proyectos típicos van de 7k€ (trabajo pequeño) a 100k€+ (proyecto grande). Sweet spot operativo: 25k-50k€.

### 1.3 ICP (Ideal Customer Profile)
Empresas que **coordinan obras integrales y subcontratan la fase de demolición**. Es decir:

- Constructoras de obra residencial
- Promotoras inmobiliarias
- Estudios de arquitectura que llevan ejecución
- Reformistas medianos
- Administradores de fincas (para reformas en comunidades)

**Lo que NO es ICP** (aunque pase el filtro CNAE): instaladores especialistas (climatización, fontanería, electricidad, asfaltado, conductos…). Esos son gremios al mismo nivel que DEMIN, no clientes.

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
| D7 | Enriquecimiento: scraping custom para 880 con web; Apollo (~45€/mes) para 857 sin web | [DECIDIDO] |
| D8 | Personalización: redacción IA completa por correo, no plantillas con variables | [DECIDIDO] |
| D9 | KB del negocio: vía RAG con `pgvector` en Supabase, editable desde dashboard | [DECIDIDO] |
| D10 | Investigación pre-redacción: scrapeo + extracción IA del dossier del prospecto | [DECIDIDO] |
| D11 | Cadencia: 3 toques (D0, D4, D10) con ángulos distintos por toque | [DECIDIDO] |
| D12 | Clasificación de respuestas: 6 categorías + flag de opt-out explícito | [DECIDIDO] |
| D13 | Re-engage: "no ahora" → +60 días; "no interesado" → +90 días; opt-out → permanente | [DECIDIDO] |
| D14 | Aprendizaje: manual en v1 (humanos ajustan KB/prompts viendo métricas) | [DECIDIDO] |
| D15 | Tope SaaS: 150€/mes | [DECIDIDO] |

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
| Enriquecimiento de decisores | Apollo.io API plan Basic (~$49/mes) | Para Tier 4 sin web |
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
│       │   ├── ingest_sabi.py        # Carga el Excel
│       │   ├── classify_descr.py     # Filtro IA por descripción
│       │   ├── research_prospect.py  # Scrapeo + extracción IA
│       │   ├── scrape_emails.py      # info@/contacto@ desde web
│       │   ├── apollo_enrich.py      # API de Apollo para Tier 4
│       │   └── verify_emails.py      # MX + SMTP check
│       ├── outreach/
│       │   ├── generate_draft.py     # Genera correo personalizado
│       │   ├── send_gmail.py
│       │   └── follow_ups.py         # Programador D4 / D10 / re-engage
│       ├── replies/
│       │   ├── poll_imap.py
│       │   ├── classify_replies.py
│       │   └── handle_actions.py     # Acción por categoría
│       ├── monitoring/
│       │   └── auto_pause.py         # Bounce >2%, spam >0.1%
│       ├── kb/
│       │   └── embed_documents.py    # Pipeline de embeddings
│       └── shared/
│           ├── db.py                 # SQLAlchemy
│           ├── llm.py                # Cliente Anthropic
│           ├── prompts/              # Carpeta con todos los prompts
│           └── config.py
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
  email_source    text check (email_source in ('sabi','web_scrape','apollo','manual')),
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

- El Excel `SABI_Export_1__1_.xlsx` ya está analizado: hoja `Resultados`, header en fila 1, 5.619 filas, 19 columnas (ver §6.1 estructura `companies` para mapping).
- Worker `ingest_sabi.py`: lee el Excel, mapea columnas, normaliza `n.d.` → NULL, calcula `rev_growth_pct`, calcula `tier` por reglas (ver §8.2).
- Idempotente por `nif` (upsert).

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

### 8.4 Investigación de prospecto (research)

Worker `research_prospect.py`. Para cada empresa con `ia_fit='fit'` y web disponible:

1. Scrapea con `httpx` la home y hasta 3 páginas internas (`/contacto`, `/servicios`, `/proyectos`, `/sobre-nosotros`, etc.).
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
  "hooks_de_personalizacion": ["..."]      // 2-3 ganchos concretos para conectar con la propuesta de DEMIN
}

Si no puedes extraer algún campo, deja "" o []. No inventes nunca.
```

El JSON se guarda en `companies.research_data`. Coste: ~$0.005 por empresa, ~5€ para 1.000 empresas.

### 8.5 Enriquecimiento de emails

**Tier 1+2+3 (con web):** worker `scrape_emails.py`. Visita la web, extrae todos los `mailto:` y patrones `[a-z]+@<dominio>`. Prioriza por orden: `comercial@`, `obras@`, `proyectos@`, `gerencia@`, `contacto@`, `info@`, `hola@`. Guarda hasta 2 emails por empresa, marca `is_primary` el primero por prioridad. Si encuentra un email con nombre (`pedro.garcia@`), lo trata como decisor potencial.

**Tier 4 (sin web):** worker `apollo_enrich.py`. Llama a la API de Apollo con NIF + nombre. Apollo devuelve dominio + decisores. Toma hasta 2 contactos con cargo relevante (gerente, director técnico, jefe de obra, comprador, responsable de operaciones).

**Si Apollo no encuentra nada:** marca la empresa como `tier='descartado'` con razón explícita. No insistir.

### 8.6 Verificación de emails

Worker `verify_emails.py`. Por cada email nuevo:

1. Sintaxis (regex)
2. MX record del dominio (DNS lookup)
3. SMTP probe opcional (cuidado: algunos providers bloquean; fallback a aceptar si MX existe)

Marca `email_verified = true/false`.

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

### Fase 0 — Setup (semana 1)

**Infra básica:**
- [x] Comprar dominio `demingroupmadrid.com` (Namecheap, expira 29/04/2027, auto-renew ON)
- [ ] Crear Google Workspace con 3 buzones
- [ ] Configurar SPF, DKIM, DMARC en DNS
- [ ] Activar APIs de Gmail en Google Cloud Console + crear OAuth client
- [ ] Crear cuenta de Supabase + proyecto
- [ ] Crear cuenta de Vercel + conectar a GitHub
- [ ] Crear cuenta de Anthropic + API key
- [ ] Decidir embeddings (Voyage o OpenAI) + crear cuenta
- [ ] Conectar buzones a Lemwarm + iniciar warmup (mínimo 2 semanas)
- [ ] Inicializar repo con la estructura de §5
- [ ] Crear `.env.example` con todas las variables esperadas (sin valores)

**Web pública (en paralelo, §13):**
- [ ] Inicializar `apps/web/` con Next.js 15 + Tailwind
- [ ] Construir landing one-pager con las 7 secciones de §13.2
- [ ] Recopilar de Gonzalo 4-8 imágenes de obras reales
- [ ] Implementar formulario `/api/contact` + tabla `web_leads`
- [ ] Aviso legal + política de privacidad + cookies (plantillas RGPD-ready)
- [ ] Configurar `demingroupmadrid.com` → web; `app.demingroupmadrid.com` → dashboard
- [ ] Test de envío del formulario end-to-end

**Contenido:**
- [ ] Sesión con Gonzalo (60-90 min) para producir el contenido inicial del KB (§7.1)
- [ ] Exportar correos reales de Gonzalo (5-10) para `kb_documents.correos_gonzalo`
- [ ] Subir Excel de Sabi y los PDFs originales a `docs/`

**Criterio de salida Fase 0:** dominio activo con web pública desplegada y formulario funcional, buzones en warmup, repo inicializado con docs, KB con contenido de Gonzalo en bruto (Markdown plano, antes de embedding).

### Fase 1 — Pipeline + KB + dashboard mínimo (semanas 2-3)

- [ ] Schema de BD aplicado (migrations §6)
- [ ] Worker `ingest_sabi.py` carga el Excel a `companies` con tier asignado
- [ ] Worker `classify_descr.py` corre sobre los 1.737 (~2€)
- [ ] Worker `embed_documents.py` indexa el KB
- [ ] Pantalla "KB editor" funcional (CRUD)
- [ ] Pantalla "Pipeline" funcional (read-only)
- [ ] Auth con magic link
- [ ] Worker `research_prospect.py` ejecutado sobre los `ia_fit='fit'` con web (~5€)
- [ ] Worker `scrape_emails.py` ejecutado sobre los mismos
- [ ] Worker `apollo_enrich.py` integrado y ejecutado sobre Tier 4
- [ ] Worker `verify_emails.py` validado
- [ ] Logs y observabilidad básica

**Criterio de salida Fase 1:** lista de ~400-500 leads cualificados, con email verificado, dossier de research, listos para campaña. Dashboard muestra el pipeline. KB indexado y editable.

### Fase 2 — Generación IA + envío + cola HITL (semana 4)

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

- Reuniones cerradas: **≥3-5/mes** en régimen autónomo
- Reply rate global: ≥5% (benchmark sector cold B2B sin personalización: 1-2%; con personalización profunda: 5-15%)
- Bounce rate: <2% sostenido
- Spam complaints: <0.1% sostenido
- Coste total mensual operativo: <130€
- Tiempo humano de Gonzalo: <30 min/día

---

## 16. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Dominio nuevo quemado por error en warmup | Media | Alto | Warmup externalizado (Lemwarm), 2+ semanas, rampa conservadora |
| KB pobre → correos genéricos | Alta | Alto | Sesión inicial con Gonzalo dedicada. Iteración semanal en v1. |
| Apollo sin cobertura para Tier 4 español | Media | Medio | Aceptar pérdida del Tier 4 si <30% hit rate. Foco en T1+T2+T3. |
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
| Apollo Basic API | ~45€ |
| Anthropic API (uso normal) | ~20-30€ |
| Embeddings (Voyage AI) | ~2-5€ |
| Hetzner VPS CX22 | ~5€ |
| Vercel | 0€ (free tier) |
| Supabase | 0€ (free tier) |
| **Total**                              | **~113-148€/mes** (rango según día 1 vs día 14+) |

Margen ajustado al techo de 150€. Configuración inicial (1 buzón + 1 Lemwarm seat) deja ~37€ de holgura. Configuración estable post-día-14 (2 buzones + 2 seats) consume casi todo el margen. Palancas si se supera: aplazar buzón warm standby más allá del día 14 (-35€/mes), o pasar Apollo de Basic a uso puntual (-30€/mes). Cualquiera de las dos garantiza margen cómodo.

---

## 18. Lo que aporta Gonzalo (dependencias humanas)

Esto NO lo construye Claude Code. Necesita coordinarse con el humano para obtenerlo:

- [x] Decisión final sobre dominio (`demingroupmadrid.com` — comprado en Bloque A)
- [ ] Acceso administrativo a Workspace
- [ ] Sesión de 60-90 min para producir KB inicial (§7.1)
- [ ] 5-10 correos reales suyos (con permiso) para entrenar tono
- [ ] **4-8 imágenes de obras reales** (idealmente antes/después) para la web (§13.3)
- [ ] **Aprobación del color de acento** y estilo general de la web
- [ ] Aprobación de drafts en Fase 2 (presencia diaria 15-30 min)
- [ ] Validación de tono y mensajes tras primer batch
- [ ] Gestión de reuniones que cierre el sistema

---

## 19. Revisión y log de ejecución

> Esta sección se llena conforme se ejecutan las fases. Cada cambio de estado, decisión nueva, desviación o lección se documenta aquí. Si un punto del plan cambia, se actualiza arriba Y se loggea aquí.

### 2026-04-29 — Plan inicial creado

Plan v1 escrito tras conversación de scoping. Pendiente de validación humana antes de iniciar Fase 0.

### 2026-04-29 — v1.1: añadido sitio web público

Se identificó que DEMIN no tiene web. Sin web, los prospectos que googleen al remitente del correo en frío no encuentran nada → conversion penalizada y deliverability empeorada. Solución: landing one-pager construida en Fase 0 en `apps/web/`, mismo stack que el dashboard, despliegue separado en `demingroup.es`. Coste adicional 0€. Ver §13.

### 2026-04-29 — Cierre Bloque A

- **Dominio:** `demingroupmadrid.com` (Namecheap, expira 29/04/2027, auto-renew ON).
- **Workspace:** Business Starter + 1 buzón activo `gonzalo.perez@demingroupmadrid.com` con display "Gonzalo Pérez". 2FA por SMS activado.
- **DNS:** SPF + DKIM + DMARC + MX en verde. CTD (Custom Tracking Domain) explícitamente NO se configura — justificación en `tasks/lessons.md` Lección 5.
- **Postmaster Tools** verificado para el dominio.
- **Cuentas creadas:** Anthropic ($25 créditos), Voyage AI (free tier), Supabase (2 proyectos: `demin-prod` y `demin-dev`), Vercel Hobby, GitHub `demin-group/demin-system` privado. Credenciales en Bitwarden, no en repo.
- **Lemwarm Essential** 29€/mes activado, warmup arrancado el 2026-04-29.
- **Decisiones operativas Bloque A** ya capturadas en `tasks/lessons.md` Lección 4: 1 buzón + warm standby día 14, cadencia D+0/D+12/D+30, caps 10 → +5/sem → 40, Postmaster Tools como monitor oficial.
- **TODO conocido pre-Fase 2:** `docs/dossier_demin.pdf` referencia el dominio antiguo (`demolicionesdemingroup.com`) y el gmail antiguo (`demin.groupmadrid@gmail.com`). Bloqueante de inicio de cadencia: regenerar el dossier con la identidad nueva antes de Fase 2.

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
