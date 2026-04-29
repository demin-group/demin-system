"""Auto-pausa de campaña si bounce > 2% o spam complaints > 0.1% (rolling 7d).

Corre cada hora. Pausa = todos los `messages` con `status='scheduled'` pasan a
`status='paused'`. Notificación al dashboard. Reanudar es manual (regla nº 6
del Apéndice A: nunca desactivar auto-pausa sin aprobación humana explícita).

Pendiente de implementar en Fase 3. Ver `tasks/todo.md` §9.4.
"""
