# Gaps conocidos del KB v1

> Documento de honestidad, **NO de to-dos activos**.
>
> El KB v1 de DEMIN se construyó a partir de una única sesión de captura
> con Gonzalo Pérez (29 abr 2026, ~32 min de entrevista efectiva). Esa
> sesión cerró 6 documentos del KB con material suficiente, pero dejó
> bloques flojos en algunos puntos.
>
> **Decisión operativa del humano (2026-04-29): NO habrá 2ª ronda de
> captura con Gonzalo.** El KB v1 se cierra con el material disponible.
> Este documento existe solo por dos razones:
>
> 1. **Trazabilidad.** Para que cualquier persona o agente que trabaje
>    en el proyecto sepa qué se sabe y qué no se sabe del negocio de
>    DEMIN, y no rellene los huecos con invención.
> 2. **Disponibilidad pasiva.** Si en algún momento Gonzalo aporta
>    material por iniciativa propia (correos reales, datos de un caso
>    nuevo, una nueva objeción que oye con frecuencia), este documento
>    es la guía de qué falta exactamente y dónde inyectarlo en el KB.
>
> Lo que NO es este documento: una lista de tareas pendientes con
> Gonzalo. NO se programan sesiones futuras de captura. Si llega
> material espontáneo, se incorpora; si no llega, el sistema vive con
> los gaps.

---

## Bloque 1 — Objeciones (gap principal)

7 de 9 objeciones clásicas no tienen respuesta validada por Gonzalo. La
táctica primaria de Gonzalo (match price + 15% descuento) cubre las
objeciones de precio, pero NO se trasladó a frases tipo para las
siguientes:

- "Ya tenemos a alguien de confianza."
- "Mándame info y te llamo."
- "No sé si encajáis con vuestro tamaño de obra."
- "Tenemos que pensarlo en el equipo."
- "Las demoliciones pequeñas las hacen los propios albañiles."
- "No conocemos vuestro trabajo, ¿podéis darnos referencias?"
- "Perfecto, nos apuntamos vuestro contacto" (la más frecuente según
  Gonzalo, también sin táctica concreta verbalizada).

**Consecuencia operativa:** la cola de respuestas de Fase 3 será
mayoritariamente HITL (~80% de respuestas escalan a Gonzalo). Ver
`tasks/kb_objeciones_v1.json` y la lección 10 en `tasks/lessons.md`.

**Si llegara material:** las 7 objeciones se actualizan en el JSON con
`tiene_respuesta_validada: true` y `respuesta_base` redactada.

---

## Bloque 2 — Caso Padre Damián / Santo Domingo de Silos

Gonzalo lo identifica espontáneamente como SU mejor obra de referencia.
NO la detalla en la entrevista. Sin metros, presupuesto, plazo, equipo,
problema resuelto y permiso de uso, el caso queda inutilizable en v1.

**Consecuencia operativa:** el caso queda archivado como referencia
interna sin datos en el documento `casos_exito` del KB. NO se usa para
nada en correos, web ni anclaje del LLM redactor.

**Si llegara material:** se enriquece el caso D del documento
`casos_exito` con los datos completos (metros, presupuesto, plazo,
equipo, problema resuelto, qué lo hace memorable, permiso de uso por
nivel). Probablemente pase a ser el caso de referencia central.

---

## Bloque 3 — Diferenciación frente a empresa grande (Q14)

En la entrevista, ante la pregunta "¿por qué vosotros vs. una empresa
más grande?", Gonzalo se atascó y aceptó la sugerencia del entrevistador
("trato directo, disponible 24/7, agilidad en comunicaciones") en lugar
de generar la respuesta en sus propias palabras. Solo verbalizó una
frase propia: "va a contar conmigo en toda la fase del proyecto, no va
a tener problema de comunicación ni limpieza con nadie".

**Consecuencia operativa:** el ángulo `reframe` del step D+12 se
construye con material parcial. Ver documento `diferenciador` del KB,
sección "Cómo lo describe Gonzalo en sus propias palabras".

**Si llegara material:** 2-3 frases auténticas suyas se inyectan en el
documento `diferenciador` y en los prompts de generación de correos
(`generate_email_reframe.md` cuando se construya en Fase 2).

---

## Bloque 4 — Permisos de uso de los casos

Para los 4 casos válidos (Av. Toreros, La Gasca, Calle Farmacia, Padre
Damián cuando se cierre), no hay permiso explícito de Gonzalo para citar
identificación pública (cliente, dirección, distrito), publicar imágenes
antes/después, o citar cifras concretas en web.

**Consecuencia operativa:** los casos quedan en nivel restrictivo por
defecto en el documento `casos_exito`. La web pública (Bloque C) se
construye sin casos identificables.

**Si llegara material:** Gonzalo aporta autorización por caso y por
nivel (web pública / correo en frío / anclaje interno). Se actualiza
la tabla de permisos del documento `casos_exito` y se desbloquea
material para Bloque C.

---

## Bloque 5 — Aclaraciones operativas residuales

Tres puntos sin cerrar que NO bloquean nada pero que serían útiles:

1. **Techo de 100k€ vs. caso Montalbán (230k€).** Aclarar si el techo
   aplica solo a ejecución con personal propio, si en obras grandes se
   subcontrata, o si el techo en realidad es flexible y Montalbán no es
   excepción.
2. **ICP — perfiles más allá de constructoras.** Gonzalo solo respaldó
   constructoras como cliente cerrado. ¿Ha cerrado alguna vez con
   estudio de arquitectura, promotora, reformista medio o administrador
   de fincas? El sistema sigue prospectando a los 5 perfiles del plan
   §1.3 mientras la respuesta no llegue.
3. **Señales preventivas del caso Fray Luis de León.** ¿Qué del cliente
   o del proyecto haría descartar hoy un prospecto similar en frío?
   Útil para afinar el filtro IA por descripción
   (`apps/workers/shared/prompts/classify_fit.md`).

---

## Bloque 6 — Tono validado contra correos reales

Bloqueado por aporte espontáneo de Gonzalo: en la entrevista prometió
mandar 5-10 correos reales suyos. No los entregó.

**Consecuencia operativa:** el doc 7 del KB (`correos_gonzalo`) está en
standby permanente. El KB vive con 6 documentos. Toda la guía del
documento `tono` está construida sobre lo que Gonzalo VERBALIZÓ en
entrevista oral, sin verificación contra correos reales.

**Si llegara material:**

1. Se crea el doc 7 (`correos_gonzalo`) con los 5-10 correos como
   contenido de KB.
2. Se compara el registro real con las reglas del documento `tono`
   para detectar fórmulas de cortesía o construcciones que en la
   entrevista negó usar pero en la práctica usa.
3. Se valida la estructura de cuerpo en 5 movimientos.
4. Si hay correos de respuesta a un "interesado", se documenta el
   registro de respuesta (distinto del registro de correo en frío).

---

## Bloque 7 — Verificación de grafías y nombres

- ¿Es **Afama Demoliciones** o tiene otra grafía? El transcript de Otter
  dice "a fama demoliciones" y se ha asumido la primera lectura, pero
  sin verificar.
- ¿**INER21** está bien escrito? Es el primer cliente recurrente de
  DEMIN. Si está bien escrito y aparece en el Excel de Sabi, debe
  marcarse con `cliente_existente=true` para excluirlo de prospección
  en frío.

---

## Resumen de impacto

Si todos los gaps se cubrieran (escenario hipotético):

- **Bloque 1 + 2 + 3** = mejora cualitativa fuerte en correos generados
  y baja la carga de HITL del ~80% al ~30%.
- **Bloque 4** = desbloquea Bloque C (web pública) y permite responder
  referencias en automático.
- **Bloque 5 + 7** = limpieza, no bloquea nada.
- **Bloque 6** = afina el documento `tono` con material real.

Si ninguno se cubre (escenario base, asumido por defecto):

- El sistema funciona, con HITL amplio y correos sin caso emblemático.
  La web pública se construye sin material identificable. El sistema
  arranca y rinde dentro de las restricciones documentadas.
