# Correos reales de DEMIN — referencia interna v1

> **Documento de referencia interna del proyecto. NO es contenido de KB
> ni se embedea ni alimenta a los workers de redacción.**
>
> Su función es doble:
>
> 1. **Histórico ("el antes").** Archivar los correos en frío que Gonzalo
>    enviaba ANTES del sistema DEMIN (2 plantillas genéricas repetidas
>    sin personalización). Sirve como referencia de qué tipo de outreach
>    el sistema viene a desplazar — NO como modelo a replicar.
> 2. **Banco de patrones reales.** Capturar las respuestas textuales que
>    los prospectos dieron a esos correos en frío. Útil para validar el
>    clasificador `classify_replies.py` cuando se construya en Fase 3:
>    son respuestas reales del mercado español B2B en demoliciones, no
>    inventadas.
>
> **Lo que este archivo NO es:** un modelo de tono. La línea editorial
> del sistema (cómo escribe el LLM redactor) está definida por el documento
> `tono` del KB, capturado en la entrevista con Gonzalo del 29 abr 2026.
> Esa entrevista verbalizó el tono que Gonzalo QUIERE que el sistema use,
> que es radicalmente distinto al de los correos plantilla archivados aquí.
>
> Ver lección 11 en `tasks/lessons.md` para el razonamiento completo de
> por qué la entrevista manda sobre los correos archivados.

---

## Sección 1 — Las 2 plantillas que Gonzalo usaba antes

### Plantilla A — "Demoliciones Interiores - Rapidez y Limpieza Garantizada"

**Asunto:** Demoliciones Interiores - Rapidez y Limpieza Garantizada (DEMIN Group)

**Apertura:** Hola equipo de [EMPRESA]:

**Cuerpo:**

> Mi nombre es Gonzalo Pérez, responsable de **DEMIN Group**, una empresa
> en Madrid especializada en la **fase cero** de sus reformas: las
> demoliciones.
>
> Hemos seguido su trabajo y sabemos que la **rapidez y la limpieza** en
> el vaciado inicial son críticas para no retrasar a los gremios siguientes.
>
> Nos ofrecemos como su **partner técnico** para garantizar que sus obras
> comienzan sin contratiempos, centrándonos en:
>
> - **Precisión y Control**: Desmontaje de falsos techos, tabiquería y
>   vaciados técnicos, minimizando el riesgo de daños estructurales o a
>   instalaciones.
> - **Velocidad**: Gestión eficiente de escombros con retirada y limpieza
>   **en el día**, entregando el espacio listo para empezar a replantear.
> - **Cumplimiento Normativo**: Todos nuestros equipos y procesos están
>   al día con **seguros y gestión de residuos (LOD).**
>
> Nos encantaría que nos considerasen para su próxima reforma integral.
> Si nos permite enviar un presupuesto para un trabajo reciente, podrá
> valorar nuestra forma de trabajar.
>
> Adjunto encontrará un breve dosier de capacidad técnica.
>
> Un cordial saludo,
>
> [logo DEMIN — sin nombre de Gonzalo en firma de texto]

**Destinatarios conocidos** (uso interno, anonimizado):

- Inmobiliaria de inversión céntrica (nov 2025)
- Estudio de arquitectura zona Tetuán (oct 2025)
- Estudio de arquitectura especializado en interiorismo (oct 2025)

### Plantilla B — "Colaboración en trabajos de demolición – DEMIN Group"

**Asunto:** Colaboración en trabajos de demolición – DEMIN Group

**Apertura:** Hola equipo de [EMPRESA]:

**Cuerpo (preview parcial):** Mi nombre es Gonzalo Pérez, responsable de
DEMIN Group, una empresa especializada en demoliciones interiores con sede
en Madrid... [resto del cuerpo no recogido en las capturas]

**Destinatarios conocidos** (uso interno, anonimizado):

- Constructora-reformas zona Madrid centro (jun 2025)
- Constructora con marca propia "D-ma" (jul 2025, vía Gabriel Sánchez)
- Reformas Pergola (oct 2025, gestor con +20 años de experiencia)
- Banasa — departamento de estudios (ago 2025, vía Palma Piedrahita)

---

## Sección 2 — Por qué estas plantillas NO son modelo de tono

Comparativa con lo que Gonzalo verbalizó en la entrevista del 29 abr 2026
sobre cómo quiere que escriba el sistema:

| Elemento | Lo que dijo Gonzalo en entrevista | Lo que hacen las plantillas |
|---|---|---|
| Asunto | "3-6 palabras, sin clickbait" | 9 palabras, paréntesis, "Garantizada" |
| Tono | "ir al grano, sin floruras" | Lleno de adjetivos vacíos y léxico de copy de venta |
| Vocabulario tabú | "nada de increíble, sinergias..." | Usa "partner técnico", "Garantizada", "Cumplimiento Normativo" mayúscula |
| Bullets en negrita | (no preguntado, pero coherente con "ir al grano") | Bullets con palabras clave en negrita — formato plantilla |
| Personalización | "referencia concreta a lo que hace la empresa" | "Hemos seguido su trabajo" — afirmación genérica que vale para cualquier prospecto |
| Promesas operativas | "nunca prometas plazos, precios o disponibilidad" | "retirada y limpieza en el día" — promesa operativa explícita |
| Tratamiento | "tuteo por defecto, nada forzado" | Mezcla incoherente — "Hola equipo" informal + "su próxima reforma" formal |
| Firma | "Gonzalo Pérez, sin cargos grandilocuentes" | Sin firma de texto, solo logo de imagen |

**Lectura operativa:** estas plantillas son justamente lo que el sistema
DEMIN viene a desplazar. Tienen marcas claras de copy genérico de SaaS
de outreach (probablemente generadas con IA genérica o copiadas de plantilla
de mailchimp/lemlist) y NO reflejan la voz auténtica de Gonzalo. La
entrevista verbalizada el 29 abr 2026 es la fuente autoritativa de tono.

**Decisión arquitectónica que esto confirma**: D8 del plan §3 — el sistema
NO usa plantillas con variables, ni siquiera "buenas" plantillas. Cada
correo es **redacción IA completa por correo**, personalizada al prospecto,
alimentada por retrieval del KB + dossier de research previo. Estas
plantillas archivadas existen aquí como referencia histórica, NO como
modelo a clonar.

---

## Sección 3 — Patrones de respuesta reales recogidos

Banco de respuestas textuales que prospectos reales dieron a las plantillas
de Gonzalo. Anonimizadas (se conserva el contenido textual, se omite o
generaliza el remitente). Útiles para validar `classify_replies.py` en
Fase 3 con datos de campo, no inventados.

### 3.1 — Categoría `no_ahora_amable` (objeción más frecuente)

6 ejemplos textuales reales:

> 1. "Muchas gracias por contactar con nosotros, tendremos en cuenta
>    para futuros proyectos."
>
> 2. "Muchas gracias por la información, os tendremos en cuenta para
>    futuras obras."
>
> 3. "Hemos recibido correctamente su información comercial. Los
>    tendremos en cuenta para futuras ocasiones de colaboración."
>
> 4. "Nos guardamos sus datos. Gracias."
>
> 5. "Muchas gracias por la información. Nos quedamos con sus datos
>    por si en un futuro podemos contar con sus servicios."
>
> 6. "Muchas gracias por la información, la tendremos en cuenta."

**Patrón común:** apertura con gratitud genérica + frase de archivo
("guardamos sus datos / tendremos en cuenta") + cierre seco. Ninguna
de las 6 abre puerta a próximo paso. Tratamiento confirmado:
`no_ahora` → re-engage +60d.

**Aplicado en:** `tasks/kb_objeciones_v1.json`, objeción
`obj_no_ahora_amable`, frases_gatillo ampliadas con variantes textuales
extraídas de estos ejemplos.

### 3.2 — Categoría `interesado_condicional` (zona gris detectada)

1 ejemplo textual real:

> "Buenos días, Gonzalo. Muchas gracias por tu correo. Mi nombre es
> [Nombre]. Te contacto desde el departamento de estudios de la empresa.
> ¿Quería preguntarse si en Demin también hacen presupuestos para
> estudios? En caso de hacerlo, me pondría en contacto contigo más
> adelante para estudiar obras que estén en proceso de licitación."

**Patrón:** interés condicional. NO es interesado puro ni objeción —
es "¿hacéis X concreto? si sí, os llamo más adelante". Requiere respuesta
con criterio sobre capacidades operativas (¿puede DEMIN trabajar con
departamentos de estudios sobre licitaciones en curso?). El sistema NO
puede comprometer esto en automático — la respuesta exige juicio que
solo Gonzalo tiene.

**Aplicado en:** `tasks/kb_objeciones_v1.json`, nueva categoría
`obj_interesado_condicional` con acción `escalar_a_gonzalo_con_contexto`.

### 3.3 — Peticiones espontáneas de oferta (oportunidad caliente)

2 ejemplos textuales reales (anonimizados):

> 1. "Buenos días: Para el proyecto indicado en Asunto, solicitamos
>    oferta de las partidas incluidas en archivo adjunto. Agradeceríamos
>    nos facilitar su oferta hasta el [FECHA]. Muchas gracias y un
>    saludo." [Constructora con CIF, sede en Madrid centro]
>
> 2. "Buenas tardes; Nuestra empresa se encuentra valorando el proyecto:
>    [REFERENCIA DE OBRA]. Es una OBRA ADJUDICADA, ya hemos ejecutado
>    previamente las Fases 1 y 2. A continuación, les enviamos la
>    documentación para que nos envíen su mejor oferta para la ejecución
>    de las partidas de DEMOLICIONES que su empresa pueda ejecutar.
>    Adjunto mediciones en pdf y Excel anexas a este mail, así como
>    PLANOS de estado actual y demoliciones. Fecha máxima de entrega:
>    [FECHA]. Rogamos nos confirmen si proceden a su valoración. Gracias
>    de antemano." [Constructora especializada]

**Patrón:** estos NO son respuestas a un cold email convencional. Son
peticiones formales de oferta donde la constructora ya tiene el proyecto
identificado, mediciones, planos y fecha límite. Pueden venir como
respuesta indirecta al cold (el cold sembró interés que cristalizó luego)
o por puro azar de coincidencia temporal.

**Tratamiento operativo:** categoría `interesado` con acción
`detener_secuencia_y_escalar_urgente`. Notificación urgente a Gonzalo.
NO generar borrador automático — Gonzalo responde en persona porque
estas son las que pueden cerrar obra real y exigen evaluación técnica
del alcance.

**Implicación**: el clasificador debe detectar peticiones de oferta
formales (palabras clave: "solicitamos oferta", "envíennos su mejor
oferta", "fecha máxima de entrega", "mediciones adjuntas", "partidas",
"licitando", "obra adjudicada") y separarlas de respuestas vagas tipo
"mándame info" — las primeras son oportunidades calientes que merecen
respuesta inmediata de Gonzalo, las segundas siguen el flujo normal de
`pide_info`.

**Mejora pendiente para Fase 3:** considerar añadir una sub-categoría
`peticion_oferta_formal` al JSON de objeciones cuando se construya
`classify_replies.py`. No se añade ahora porque la categoría `interesado`
ya cubre el caso operativo (escalado urgente a Gonzalo) — pero un
clasificador más fino mejoraría la priorización de la cola.

---

## Sección 4 — Conclusión operativa

Lo que esta revisión confirma:

1. La decisión arquitectónica D8 (redacción IA completa por correo, sin
   plantillas) está bien tomada y se ratifica con material en mano.
2. El doc `tono` del KB v1, capturado en la entrevista del 29 abr 2026,
   es la fuente autoritativa de cómo escribe Gonzalo. NO se actualiza
   con estas plantillas archivadas porque no representan su voz auténtica.
3. El doc 7 (`correos_gonzalo`) sigue en standby permanente. Estos correos
   reales no sirven como modelo positivo de tono.
4. El JSON `kb_objeciones_v1.json` se enriquece con datos de campo reales
   (frases gatillo extraídas de las respuestas) y con una nueva categoría
   intermedia (`obj_interesado_condicional`) detectada gracias al material.

Lo que esta revisión NO cambia:

- Nada del contenido cargado en `kb_documents` en sesión 1.
- Nada de las decisiones del plan o de las lecciones 1-10.
- La política de HITL amplio en Fase 3 (lección 10).
- La línea editorial sobre la juventud de DEMIN como activo (sesión 1).

---

## Apéndice — Lo que NO está en este archivo

Tres tipos de correo que valdría tener pero no se han recogido en esta
sesión (gap conocido, NO to-do activo):

1. **Correos donde Gonzalo respondió a un prospecto que le contestó.**
   Mostrarían cómo escribe Gonzalo en conversación viva, no en frío.
   Material valioso para `suggest_response` en Fase 3 si llegara.
2. **Correos con objeciones distintas del "no_ahora amable"** —
   "ya tenemos proveedor", "es caro", "no encajáis con nuestro tamaño".
   Las 6 objeciones sin respuesta validada en el JSON siguen sin tener
   ejemplos textuales reales para alimentar sus `frases_gatillo`.
3. **Hilos completos donde una respuesta inicial llevó a una segunda
   ronda y eventualmente a cierre o rechazo.** Permitirían entender la
   curva temporal típica de un cold a obra cerrada en este sector.

Si en algún momento aparecen, se incorporan a este archivo y se evalúa
si justifican un nuevo patch al JSON. Si no aparecen, el sistema vive
con el material actual.
