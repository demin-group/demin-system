"""Scrapeo de emails desde la web del prospecto (Tier 1+2+3).

Visita la web y extrae mailtos + patrones `[a-z]+@<dominio>`. Prioriza:
comercial@, obras@, proyectos@, gerencia@, contacto@, info@, hola@.
Guarda hasta 2 emails por empresa, marca `is_primary` el primero por prioridad.

Pendiente de implementar en Fase 1. Ver `tasks/todo.md` §8.5.
"""
