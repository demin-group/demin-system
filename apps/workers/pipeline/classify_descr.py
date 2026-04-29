"""Filtro IA por descripción de actividad.

Itera empresas con `tier in (T1,T2,T3,T4)` e `ia_fit='pendiente'`. Llama a Claude
con el prompt en `shared/prompts/classify_fit.md`. Marca `ia_fit` y `ia_fit_reason`.

Pendiente de implementar en Fase 1. Ver `tasks/todo.md` §8.3.
"""
