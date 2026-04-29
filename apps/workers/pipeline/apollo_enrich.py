"""Enriquecimiento de decisores vía Apollo.io API (Tier 4 sin web).

Llama a Apollo con NIF + nombre. Toma hasta 2 contactos con cargo relevante
(gerente, director técnico, jefe de obra, comprador, responsable de operaciones).
Si no hay match: marca `tier='descartado'` con razón explícita; no insiste.

Pendiente de implementar en Fase 1. Ver `tasks/todo.md` §8.5.
"""
