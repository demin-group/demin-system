"""Poll IMAP de los 3 buzones cada 5 minutos.

Por cada respuesta nueva: match con el `message` original por `In-Reply-To` o
`References`, persiste en `replies` y encola job `classify_reply`.

Pendiente de implementar en Fase 3. Ver `tasks/todo.md` §11.1.
"""
