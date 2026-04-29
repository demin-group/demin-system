"""Verificación de emails: sintaxis + MX record + SMTP probe opcional.

Marca `email_verified = true/false` en la tabla `contacts`. Si SMTP probe es
bloqueado por el provider, fallback a aceptar si MX existe.

Pendiente de implementar en Fase 1. Ver `tasks/todo.md` §8.6.
"""
