"""Genera el draft de correo personalizado para un `message`.

Pipeline: carga contacto + empresa + research_data + correos previos al mismo
contacto + retrieval de 5 chunks del KB → construye prompt según `angle`
(opening / reframe / closing / re_engage_60 / re_engage_90) → Claude Sonnet 4.5
→ validación post-generación (§10.3) → `messages.body` con `status='drafted'`.

Pendiente de implementar en Fase 2. Ver `tasks/todo.md` §10.
"""
