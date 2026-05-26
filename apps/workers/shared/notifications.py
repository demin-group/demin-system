"""notifications.py -- helper para enviar emails operativos via Resend.

Lo usan workers que necesitan notificar a PM/operador (auto_switch_to_autonomous,
potencialmente auto_pause, etc.) cuando ocurren eventos relevantes.

Lee `RESEND_API_KEY` directamente de os.environ -- NO esta en
shared.config.Settings porque es opcional (sin clave, el worker sigue
funcionando pero salta el envio con warning).

Patron Leccion 8 (notifications best-effort): nunca lanza, devuelve
False y loguea si falla. Operacion critica sigue.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

import httpx

logger = logging.getLogger("demin.notifications")

RESEND_API_BASE = "https://api.resend.com"
DEFAULT_FROM = "DEMIN System <noreply@send.demingroupmadrid.com>"
TIMEOUT_S = 10.0


def send_operational_email(
    *,
    to: Iterable[str],
    subject: str,
    html: str,
    text: str | None = None,
    from_address: str | None = None,
) -> bool:
    """Envia email via Resend. Best-effort: True si OK, False si falla
    o si RESEND_API_KEY ausente. NUNCA lanza.

    `to`: lista de emails destinatarios.
    `subject`: asunto.
    `html`: cuerpo HTML.
    `text`: cuerpo plain text (opcional; Resend genera fallback si null).
    `from_address`: remitente. Default 'DEMIN System <noreply@send.demingroupmadrid.com>'.
    """
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "RESEND_API_KEY ausente -- email no enviado (subject=%r, to=%s)",
            subject, list(to),
        )
        return False

    to_list = [t.strip() for t in to if t and t.strip()]
    if not to_list:
        logger.warning("send_operational_email sin destinatarios validos")
        return False

    payload: dict[str, object] = {
        "from": from_address or DEFAULT_FROM,
        "to": to_list,
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        resp = httpx.post(
            f"{RESEND_API_BASE}/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TIMEOUT_S,
        )
        if resp.status_code in (200, 201):
            logger.info(
                "email_sent subject=%r to=%s resend_id=%s",
                subject, to_list, resp.json().get("id"),
            )
            return True
        logger.warning(
            "email_failed subject=%r status=%d body=%s",
            subject, resp.status_code, resp.text[:200],
        )
        return False
    except Exception as e:
        logger.warning("email_exception subject=%r: %s", subject, e)
        return False
