# CLAUDE.md

> Este archivo se carga automáticamente al inicio de cada sesión de Claude Code en este proyecto. Contiene las reglas operativas del proyecto. No es un aprendizaje, es la constitución.

---

## Orientación al proyecto

Estás trabajando en **demin-system**: un sistema de captación comercial automatizada para DEMIN Group, una empresa de demoliciones interiores en Madrid.

Antes de tocar nada, lee siempre estos tres archivos en orden:

1. **`tasks/todo.md`** — el plan completo, decisiones cerradas, esquema de BD, fases con checklist verificable. Es la fuente de verdad arquitectónica.
2. **`tasks/lessons.md`** — lecciones capturadas tras correcciones humanas. Patrones a no repetir.
3. **`docs/dossier_demin.pdf`** y **`docs/onboarding_demin.pdf`** — contexto del negocio.

Las decisiones marcadas como `[DECIDIDO]` en `todo.md` no se cuestionan sin pregunta explícita previa al humano.

---

## Orquestación del flujo de trabajo

### 1. Modo planificación por defecto

- Entra en modo planificación por **defecto** para **CUALQUIER** tarea no trivial (más de 3 pasos o decisiones arquitectónicas).
- Si algo sale mal, **PARA** y vuelve a planificar de inmediato; no sigas forzando.
- Usa el modo planificación también para los pasos de verificación, no solo para la construcción.
- Escribe especificaciones detalladas por adelantado para reducir la ambigüedad.

### 2. Estrategia de subagentes

- Usa subagentes con frecuencia para mantener limpia la ventana de contexto principal.
- Delega la investigación, exploración y análisis en paralelo a subagentes.
- Para problemas complejos, dedica más capacidad de cómputo mediante subagentes.
- Una tarea por subagente para una ejecución focalizada.

### 3. Bucle de auto-mejora

- Tras **CUALQUIER** corrección del usuario: actualiza `tasks/lessons.md` con el patrón.
- Escribe reglas para ti mismo que eviten el mismo error.
- Itera implacablemente sobre estas lecciones hasta que la tasa de errores disminuya.
- Revisa `tasks/lessons.md` al inicio de cada sesión.

### 4. Verificación antes de finalizar

- Nunca marques una tarea como completada sin demostrar que funciona.
- Compara la diferencia (diff) de comportamiento entre la rama principal y tus cambios cuando sea relevante.
- Pregúntate: "¿Aprobaría esto un Staff Engineer?".
- Ejecuta tests, comprueba los logs y demuestra la corrección del código.

### 5. Exigir elegancia (equilibrada)

- Para cambios no triviales: haz una pausa y pregúntate "¿hay una forma más elegante?".
- Si un arreglo parece un parche (hacky): "Sabiendo todo lo que sé ahora, implementa la solución elegante".
- Omite esto para arreglos simples y obvios — no sobreingenieríes.
- Cuestiona tu propio trabajo antes de presentarlo.

### 6. Corrección autónoma de errores

- Cuando recibas un informe de error: simplemente arréglalo. No pidas que te lleven de la mano.
- Identifica logs, errores o tests que fallen y luego resuélvelos.
- Cero necesidad de cambio de contexto por parte del usuario.
- Arregla los tests de CI que fallen sin que te digan cómo.

---

## Gestión de tareas

1. **Planificar primero**: el plan está en `tasks/todo.md` con elementos verificables (checkboxes).
2. **Verificar plan**: confirma con el humano antes de comenzar la implementación de una fase.
3. **Seguimiento del progreso**: marca los elementos como completados (`[x]`) a medida que avances.
4. **Explicar cambios**: resumen de alto nivel en cada paso, no narres cada línea.
5. **Documentar resultados**: añade entradas a la sección §19 ("Revisión y log de ejecución") de `tasks/todo.md` cuando termines fases o tomes decisiones nuevas.
6. **Capturar lecciones**: actualiza `tasks/lessons.md` después de las correcciones del humano.

---

## Principios fundamentales

- **Simplicidad primero**: haz que cada cambio sea lo más simple posible. Afecta al mínimo código necesario.
- **Sin pereza**: encuentra las causas raíz. Nada de arreglos temporales. Estándares de desarrollador senior.
- **Impacto mínimo**: los cambios solo deben tocar lo necesario. Evita introducir errores.

---

## Reglas no negociables del proyecto

(Espejo del Apéndice A de `tasks/todo.md`.)

1. **Nunca** envíes un correo sin pasar por la cola de aprobación (en HITL). En autónomo, nunca sin pasar las validaciones de §10.3 del todo.md.
2. **Nunca** ignores un opt-out explícito. Es exclusión permanente.
3. **Nunca** inventes datos del prospecto. Si el research no lo dice, no lo digas.
4. **Nunca** prometas plazos, precios o disponibilidad en nombre de DEMIN.
5. **Nunca** uses `localhost` ni credenciales hardcoded en commits. Variables de entorno o Supabase Vault.
6. **Nunca** desactives la auto-pausa sin aprobación humana explícita.
7. **Siempre** usa `pgvector` (Supabase) para el KB, no servicios externos de embeddings con almacenamiento.
8. **Siempre** versiona los prompts en el repo (`apps/workers/shared/prompts/*.md`).
9. **Siempre** que detectes desviación del plan, para y pregunta antes de seguir.
10. **Siempre** captura lecciones en `tasks/lessons.md` tras cualquier corrección humana.
11. **Nunca** inventes clientes, testimonios, casos de éxito o cifras en la web pública. Solo material que Gonzalo aporte y autorice.
12. **Siempre** mantén la separación de despliegue: `demingroup.es` (web pública, sin auth) ≠ `app.demingroup.es` (dashboard, auth obligatoria).

<!-- Notas para el humano que mantiene este archivo:
     Mantén CLAUDE.md compacto. El plan detallado vive en tasks/todo.md.
     Aquí solo van: orientación, reglas de proceso, reglas no negociables.
     Si añades cosas, asegúrate de que aplican a TODA sesión, no a una fase concreta. -->
