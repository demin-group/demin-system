"""Ejecuta la acción correspondiente a cada categoría de respuesta.

interesado     → detener secuencia + escalado a Gonzalo + draft de respuesta
pide_info      → detener secuencia + draft de respuesta (HITL)
no_ahora       → detener secuencia + re-engage D+60 (`re_engage_60`)
no_interesado  → detener secuencia + re-engage D+90 (`re_engage_90`)
rebote         → marcar email_verified=false + buscar alternativo
fuera_oficina  → reprogramar siguiente toque a fecha+5d (o +7d si no hay fecha)
opt-out        → contacts.is_optout=true + acuse "Te quitamos de la lista"

Pendiente de implementar en Fase 3. Ver `tasks/todo.md` §11.2.
"""
