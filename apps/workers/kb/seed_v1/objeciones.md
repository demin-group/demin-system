# Objeciones — qué responde DEMIN cuando un prospecto pone freno

## Aviso operativo

En la entrevista de KB se le pasó a Gonzalo el listado completo de objeciones
clásicas en cold B2B. Su respuesta fue una **única táctica comercial general**,
no una respuesta articulada por objeción [42:21–44:36]. Este documento
recoge esa táctica como respuesta primaria a objeciones de precio y de
encaje, y deja explícitamente marcadas las objeciones para las que NO
tenemos respuesta validada por Gonzalo. Esas objeciones se tratan en
producción como "escalado a Gonzalo", no se responden con improvisación
del sistema.

## Táctica primaria — respuesta a objeciones de precio y de encaje

Texto literal reconstruido a partir de la respuesta de Gonzalo
[43:14–44:36]:

> "Pasarme un presupuesto anterior que tenga el cliente de una demolición y
> yo le mando enseguida los precios que tenemos nosotros para ver si le
> encaja un precio. Si no, la otra opción es que en la próxima demolición
> pequeña que tenga, un piso normalito, le hago el trabajo con un 15% de
> descuento sobre el total, para fidelizar al cliente y para que pueda
> comprobar cómo trabajamos."

La táctica tiene dos movimientos:

1. **Match price.** Si el prospecto ya tiene un presupuesto de otra empresa,
   Gonzalo lo iguala o lo baja. "El objetivo al final es engancharle"
   [44:36]. Si los precios resultan muy parecidos, no se baja a ciegas:
   se da explicación de por qué (matizar accesos, plazo, alcance).
2. **Descuento de fidelización.** Si la primera vía no aplica, oferta del
   **15% de descuento** sobre la próxima obra del cliente, como
   demostración del nivel de trabajo. **El descuento del 15% no tiene
   tope de presupuesto: aplica tanto a obras pequeñas como a las grandes,
   siempre como gancho de fidelización en la primera colaboración.**

Esta es la respuesta de Gonzalo a "me parece caro" y, según su propia
formulación, también su forma de entrar cuando la respuesta es ambigua.

## Tipo de objeción que más le frustra

Cita [45:36]:

> "Me suelen responder mucho con: 'perfecto, nos apuntamos tu contacto para
> futuras demoliciones'. Pues ahí me gustaría terminar de engancharles
> cuando me responden a ese tipo cuando me responden a los correos."

Es decir, el "no ahora amable" — la respuesta cortés que aparca el contacto
sin cerrar puerta. Para Gonzalo es la objeción más frustrante porque NO es
un no, pero deja la conversación en limbo.

Su filosofía frente a esto, cita [45:58]:

> "El cómo no aceptar un no. Efectivamente, intentar lucharlo para
> rascarle algo."

Operativamente, el sistema trata "perfecto, nos apuntamos vuestro contacto"
como categoría `no_ahora` (no como `no_interesado`) → re-engage automático
a +60 días con ángulo `re_engage_60`. Gonzalo confirma con su filosofía
que esto es lo correcto: no es un no definitivo, hay que volver.

## Presupuesto sin visita previa

Cita reconstruida [46:17]:

> "No siempre voy. En muchos casos están licitando, por lo tanto ni la
> empresa constructora tiene las llaves del local o del piso, y lo único
> que tienen son fotos. Es presupuestar un poco a ciegas porque tampoco
> conozco los accesos ni nada."

Procedimiento de Gonzalo:

- Si el cliente manda **mediciones detalladas**: presupuesta a ciegas con
  esa información.
- Si las mediciones no están al 100%: va al sitio para hacerlas él.
- Si no se puede ir al sitio: pide **fotos documentadas con explicación
  por zona** de lo que hay que hacer. Con eso presupuesta.

Esta es la respuesta cuando un prospecto pide presupuesto en frío sin
visita.

## Objeciones SIN respuesta validada — escalar a Gonzalo

Las siguientes objeciones se le pasaron a Gonzalo en la entrevista y NO
respondió a ellas de forma diferenciada. **No se debe improvisar respuesta
en automático.** El sistema las clasifica y las escala:

- "Ya tenemos a alguien de confianza."
- "Mándame info y te llamo."
- "No sé si encajáis con vuestro tamaño de obra."
- "Tenemos que pensarlo en el equipo."
- "Las demoliciones pequeñas las hacen los propios albañiles."
- "No conocemos vuestro trabajo, ¿podéis darnos referencias?"

Para todas estas, la acción del sistema es:

- Categoría: `pide_info` o `no_ahora` según el caso.
- Acción: detener secuencia, generar borrador de respuesta sugerida basada
  en la táctica primaria (match price + descuento del 15%) **únicamente como
  base de partida**, marcar como **escalado a Gonzalo** con HITL obligatorio.

## Línea roja de Gonzalo frente a las objeciones

Cita [54:32]:

> "Nunca puede mandar un presupuesto a un cliente, nunca puede agendar una
> cita con un cliente, nunca puede aceptar o sea hacer el filtro de sí o no
> de una obra. Me lo tiene que pasar todo a mí, tengo que confirmar todo yo.
> Está claro eso ya."

Implicación operativa para la cola de respuestas: ninguna respuesta a una
objeción puede contener cifras concretas de presupuesto, plazos comprometidos,
ni aceptación o rechazo de la obra. La función de la respuesta automática
(o sugerida en HITL) es **mantener viva la conversación** hasta que Gonzalo
entre en persona — nada más.

## GAPS CONOCIDOS DEL KB v1

(NO son to-dos activos. Decisión humana: NO hay 2ª ronda con Gonzalo.
Quedan documentados aquí solo por trazabilidad.)

Este documento es el más flojo de los 6 que conforman el KB inicial. Tres
bloques que quedaron sin cerrar:

1. **Respuesta diferenciada a las 6 objeciones sin trabajar** (lista
   arriba). Para cada una: Gonzalo no verbalizó frase tipo. La táctica
   primaria sirve de base, pero no está validada como respuesta para
   estas objeciones específicas.
2. **Cómo trabaja el "perfecto, nos apuntamos vuestro contacto"** más
   allá de "rascarle algo". Cómo concretamente — si manda dossier, llama,
   propone visita gratuita — no quedó verbalizado.
