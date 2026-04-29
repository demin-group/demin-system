"""Clasifica respuestas en 6 categorías + flag de opt-out explícito.

Categorías: interesado | pide_info | no_ahora | no_interesado | rebote |
fuera_oficina | desconocido. El flag `is_explicit_optout` es transversal y
fuerza exclusión permanente (regla nº 2 del Apéndice A). Devuelve también
una respuesta sugerida si aplica.

Pendiente de implementar en Fase 3. Ver `tasks/todo.md` §11.1, §11.3 y
`tasks/lessons.md` (lección 1 del 2026-04-29).
"""
