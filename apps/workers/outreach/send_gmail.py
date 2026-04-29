"""Envío real vía Gmail API.

Toma `messages` con `status='approved'` o `status='scheduled'` cuyo `scheduled_for`
ha llegado, los envía desde el `mailbox` asignado, persiste `gmail_message_id`,
respeta caps por buzón y aplica jitter ±30 min sobre la hora prevista.

Pendiente de implementar en Fase 2. Ver `tasks/todo.md` §9.
"""
