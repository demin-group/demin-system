# Opción C — pipeline T4 (empresas sin web declarada)

> Doc de diseño. Sesión 2026-05-26. Code implementa tras confirmación PM.
> Decisión PM: pool threshold ≥50 (no 100). Opción C es la palanca principal
> para subir el pool ya que Hunter retry sobre T1+T2 (102 empresas) dio 0
> contactos nuevos — cobertura Hunter estructuralmente saturada en sector
> construcción PYME España (confirmado Lección 22 + sesión 2026-05-26).

## Universo objetivo

288 empresas `tier='T4'`, `ia_fit='fit'`, `research_done_at IS NULL`,
`web IS NULL` (100% sin web declarada). Es el último gran bloque de pool
sin tocar. No hay más T1/T2/T3/T4 después de esto en el ingest actual de
Sabi — para más material habría que pasar a Palancas A (LinkedIn), B
(clasificar pendientes) o C (nuevo dump Sabi) — ver `tasks/todo.md` §20.

## Inputs disponibles por empresa

Lo que sabemos sin web:

- `nif` (identificador).
- `nombre` (razón social, ej. "DEMOLICIONES PEREZ SL").
- `localidad` (ciudad principal, ej. "MADRID").
- `descripcion` (descripción Sabi del sector / actividad CNAE expresada en texto).
- `rev_y0_keur`, `rev_y1_keur`, `rev_growth_pct` (cifras facturación si están).
- `tier='T4'` (rango bajo, 0.5k-20k €).

NO tenemos: web, teléfono, dirección postal completa, nombre del CEO/administrador, redes sociales, fotos.

## Estrategia general (4 sub-pasos)

```
T4 fit sin web (288)
   │
   ├──► (1) infer_domain     ─► dominio candidato o None
   │       │
   │       └─► si None: descarta company (tier='descartado', razon='no_domain_inferred')
   │
   ├──► (2) research_t4_nowebsite ─► research_data minimo + hooks por sector/localidad
   │
   ├──► (3) permute_emails    ─► lista de candidatos (info@, contacto@, etc.)
   │
   └──► (4) smtp_probe        ─► email verificado o None
           │
           ├─► email verificado: INSERT contact con email_source='option_c_t4'
           └─► None: skip silencioso (no descarta company; reintento futuro posible)
```

## (1) infer_domain — heurística simple `<slug>.<tld>` + MX check

**Por qué simple y no Google search:**
- Google search API ($5/1000 queries con Custom Search) cabe pero ata a un proveedor con quotas estrictas.
- Scraping Google es frágil y rate-limited agresivamente.
- Empresite.com / Einforma.com requieren mini-experimento estructurado (Lección 26) — fuera de scope esta sesión.
- La heurística `<slug>.es` funciona en sector PYME ES donde la mayoría usan dominio igual al nombre comercial.

**Algoritmo:**

1. **Slugify nombre** quitando sufijos legales (`SL`, `SA`, `SLU`, `CB`, etc.) y normalizando: lowercase + ASCII + sin espacios. Ej. "DEMOLICIONES PEREZ SL" → `"demolicionesperez"`.
2. **Generar variantes**:
   - `<slug>.es`
   - `<slug>.com`
   - Si nombre tiene 2+ palabras: también `<palabra1>-<palabra2>.es` y `<palabra1><palabra2>.es`.
3. **Para cada variante, lookup DNS MX**:
   - Si MX devuelve registros: candidato válido.
   - Si NXDOMAIN o sin MX: descarta variante.
4. **Devuelve la primera variante con MX válido** (orden de preferencia: `.es` primero).
5. Si ninguna variante tiene MX: `infer_domain → None`.

**Hit rate esperado**: 15-30% basado en intuición sector. Los que tienen dominio comercial real lo tienen igual o muy parecido al nombre. Los que no tienen web tampoco tienen email business → caen al 70-85%.

**Coste**: 0 USD. DNS MX lookups son gratis y rápidos (~50ms). Total 288 × 3 variantes = 864 lookups en ~1 min.

## (2) research_t4_nowebsite — research IA sin scraping

**Limitación clara**: sin web no podemos extraer proyectos concretos, hooks personalizados con detalle, valores específicos. Lo que podemos hacer:

- Inferir tipo de actividad concreta desde la `descripcion` Sabi.
- Identificar sub-sector (constructora vs promotora vs reformas vs estudios arquitectura).
- Generar hooks genéricos basados en localidad + sub-sector + facturación.

**Prompt** (corto, Haiku o Sonnet — uso Sonnet por calidad):

```
Eres analista de prospección. Dado el siguiente registro de empresa
(sin web disponible), extrae JSON con:
- tipo_actividad_concreta (1 frase)
- sub_sector (constructora_obra_nueva | reformas | demolicion | arquitectura | promotora | otro)
- hooks_de_personalizacion (lista 1-2 hooks que un correo en frío
  podría usar basándose SOLO en nombre+localidad+sector,
  evitando inventar proyectos concretos)
- nota: si la empresa parece NO encajar con ICP de demoliciones
  interiores (ej. es una constructora de obra civil pura, una
  inmobiliaria sin obra propia, etc.), añadir flag _maybe_not_fit=true
```

**Coste estimado**: ~$0.005-0.010 por empresa (prompt ~800 tokens input + ~250 output, Sonnet 4.6). 288 × $0.008 = **~$2.30 LLM**.

**Salida persistida**: `companies.research_data` con campos mínimos +
`research_data._source='option_c_nowebsite'` para distinguir de research
con scraping.

## (3) permute_emails — generador de candidatos

Whitelist positiva del L23 D20 (válida para T1 y T4 según política
"corporativo_pequeno OK en tier bajo"):

```python
PATRONES = [
    "info",
    "contacto",
    "administracion",
    "gerencia",
    "oficina",
]
```

Genera hasta 5 candidatos por dominio. **NO incluye patrones tipo
`gonzalo@`, `nombre.apellido@`, etc.** porque sin LinkedIn no sabemos
nombres de personas.

## (4) smtp_probe — verificador SMTP

**Mecánica**:

1. **Lookup MX records** para el dominio. Toma el primero por prioridad.
2. **Connect SMTP** al servidor MX (puerto 25, timeout 10s).
3. **HELO + MAIL FROM `<probe@demingroupmadrid.com>` + RCPT TO `<candidato@dominio>`**.
4. **Sin DATA**: cerramos la conexión tras leer la respuesta del RCPT TO.
   - `250 OK` → email aceptado.
   - `550 / 551 / 553` → email rechazado (no existe).
   - `421 / 450 / 451` greylist o rate-limit → no concluyente, marcar para retry futuro.
   - Otros errores → no concluyente.

**Catch-all detection** (obligatorio antes de aceptar):
- Primero probe con email aleatorio `xyzrandom1234@<dom>`.
- Si responde 250: dominio es catch-all (acepta todo) — los probes de
  patrones reales son falsos positivos. **Skip dominio completo**.
- Si responde 550: catch-all detection negativo, podemos confiar en los
  siguientes probes.

**Rate limiting**:
- Máximo 1 conexión simultánea por dominio (DNS providers consideran
  abuse el paralelismo).
- Sleep 3s entre dominios distintos.
- Timeout total por dominio: 60s (incluyendo MX + catch-all + 5 patrones).

**Riesgos**:
- Algunos providers (Google Workspace, Microsoft 365) responden 250 a
  TODO el RCPT TO independientemente del email real (anti-enumeración).
  El catch-all detection los pilla.
- Otros providers (Workspace en modo strict) cierran la conexión sin
  respuesta. Marcar como inconcluso.
- IPs residenciales / dinámicas pueden ser bloqueadas por listas RBL.
  Probar desde el VPS Hetzner (IP estática, sin reputación negativa
  conocida) es la apuesta correcta. En local desde la conexión PM
  podría fallar — si el smoke local falla, mover a VPS antes de full run.

**Confidence score asignado**: 50 sobre 100 (Hunter da 70-99 cuando
encuentra). El operador HITL ve el `email_source='option_c_t4'` y sabe
que la confianza es menor.

## Salida final

Por cada empresa T4 procesada:

| Caso | Acción BD |
|---|---|
| Sin dominio inferido | `companies.tier='descartado'` + `research_data._descartado_reason='no_domain_inferred'` |
| Dominio inferido + research IA | `companies.research_data={...}` + `research_done_at=now()` |
| Catch-all detectado | research_data._smtp_status='catch_all_skipped'`, NO contact insertado |
| Email verificado SMTP | INSERT `contacts (email, email_verified=true, email_source='option_c_t4', email_type='corporativo_pequeno', email_priority=4, is_primary=true)` |
| Sin email verificado | research_data._smtp_status='no_match'`, NO contact insertado |

## Métricas a reportar tras run

- Empresas procesadas / 288.
- Con dominio inferido / sin dominio.
- Catch-all detectados / con dominio inferido.
- Emails verificados / candidatos probados.
- Contactos insertados.
- Coste LLM consumido.
- Tiempo total.

## Decisiones explícitas (PM puede revertir)

1. **Whitelist de patrones**: 5 (`info, contacto, administracion, gerencia, oficina`). No incluir `obras@` ni `proyectos@` porque tienen tasa más alta de ser leídos por gente NO-decisora en T4. Razón: empresas micro T4, todo el flujo va al gerente; los buzones nominales pierden señal.

2. **Hit rate esperado conservador**: 5-15% del universo T4. Sobre 288 = 15-45 contactos nuevos. Llegar a pool ≥50 total con esto + los 9 actuales requiere que la cota alta se cumpla.

3. **Si SMTP probe da problemas desde local**, mover ejecución al VPS Hetzner (IP estática con reputación neutra). El smoke inicial sobre 10 empresas lo decide.

4. **No hago hoy**: empresite.com / einforma.com scraping (Lección 26 deuda). Si Opción C heurística no llega a 50 vírgenes, esa es la siguiente palanca natural pero requiere su propio diseño.
