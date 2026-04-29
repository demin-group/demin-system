# DEMIN — Lecciones capturadas

> Aquí se registran patrones que hemos aprendido tras correcciones humanas o errores. La idea es no repetirlos. Claude Code lee este archivo al inicio de cada sesión.

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

<!-- Plantilla para futuras lecciones:

## YYYY-MM-DD — Lección N: <título corto>

**Contexto:**
**Corrección humana:**
**Regla resultante:**
**Aplicado en:**

-->
