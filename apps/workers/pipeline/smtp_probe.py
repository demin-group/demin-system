"""smtp_probe.py -- verificador SMTP via MX RCPT TO (sin DATA).

Opcion C T4 (sesion 2026-05-26). Probe individual de un email candidato
contra el servidor MX de su dominio. NO envia mensaje real -- cierra
conexion tras leer respuesta del RCPT TO.

Tres respuestas posibles:
- EmailStatus.VALID: 250/251 OK al RCPT TO -> email existe.
- EmailStatus.INVALID: 550/551/553 -> no existe.
- EmailStatus.INCONCLUSIVE: 4xx greylist o error de conexion -> retry futuro.

IMPORTANTE: detect catch-all PRIMERO. Sin esto, dominios catch-all
(que aceptan TODO al RCPT) dan 5 falsos positivos por dominio.

Ver doc: docs/option_c_t4_pipeline.md (4) smtp_probe.
"""
from __future__ import annotations

import logging
import smtplib
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

logger = logging.getLogger("demin.smtp_probe")

# El email FROM que usamos para identificar nuestros probes. NO debe
# coincidir con remitente productivo para no contaminar reputacion.
PROBE_FROM = "probe@demingroupmadrid.com"

SMTP_TIMEOUT = 10.0  # segundos


class EmailStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    INCONCLUSIVE = "inconclusive"
    CATCH_ALL = "catch_all"


@dataclass(slots=True)
class ProbeResult:
    email: str
    status: EmailStatus
    smtp_code: int | None = None
    smtp_message: str = ""


def _probe_single(
    mx_host: str, email: str, probe_from: str = PROBE_FROM, timeout: float = SMTP_TIMEOUT
) -> ProbeResult:
    """Probe contra un MX especifico. Cierra conexion tras RCPT TO."""
    server = None
    try:
        server = smtplib.SMTP(mx_host, 25, timeout=timeout)
        server.ehlo("demingroupmadrid.com")
        # MAIL FROM
        code, msg = server.mail(probe_from)
        if code >= 400:
            return ProbeResult(
                email=email,
                status=EmailStatus.INCONCLUSIVE,
                smtp_code=code,
                smtp_message=(msg.decode("utf-8", errors="replace") if isinstance(msg, bytes) else str(msg))[:200],
            )
        # RCPT TO -- la respuesta real que nos importa.
        code, msg = server.rcpt(email)
        msg_str = (
            msg.decode("utf-8", errors="replace") if isinstance(msg, bytes) else str(msg)
        )[:200]
        if code in (250, 251):
            return ProbeResult(
                email=email, status=EmailStatus.VALID,
                smtp_code=code, smtp_message=msg_str,
            )
        if code in (550, 551, 553, 554):
            return ProbeResult(
                email=email, status=EmailStatus.INVALID,
                smtp_code=code, smtp_message=msg_str,
            )
        # 4xx greylist / rate-limit / temporary failure.
        return ProbeResult(
            email=email, status=EmailStatus.INCONCLUSIVE,
            smtp_code=code, smtp_message=msg_str,
        )
    except (smtplib.SMTPConnectError, socket.timeout, ConnectionRefusedError, OSError) as e:
        return ProbeResult(
            email=email, status=EmailStatus.INCONCLUSIVE,
            smtp_code=None, smtp_message=f"connection_error: {e!s}"[:200],
        )
    except smtplib.SMTPServerDisconnected as e:
        return ProbeResult(
            email=email, status=EmailStatus.INCONCLUSIVE,
            smtp_code=None, smtp_message=f"server_disconnected: {e!s}"[:200],
        )
    except Exception as e:
        logger.warning("smtp_probe error %s for %s: %s", type(e).__name__, email, e)
        return ProbeResult(
            email=email, status=EmailStatus.INCONCLUSIVE,
            smtp_code=None, smtp_message=f"{type(e).__name__}: {e!s}"[:200],
        )
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def probe_email(
    email: str, mx_records: Sequence[str], timeout: float = SMTP_TIMEOUT
) -> ProbeResult:
    """Probe un email contra los MX records del dominio. Devuelve la
    primera respuesta NO inconclusive, o la ultima inconclusive si
    todos los MX fallaron."""
    if not mx_records:
        return ProbeResult(
            email=email, status=EmailStatus.INCONCLUSIVE,
            smtp_code=None, smtp_message="no_mx_records",
        )
    last_inconclusive: ProbeResult | None = None
    for mx in mx_records:
        result = _probe_single(mx, email, timeout=timeout)
        if result.status in (EmailStatus.VALID, EmailStatus.INVALID):
            return result
        last_inconclusive = result
    return last_inconclusive or ProbeResult(
        email=email, status=EmailStatus.INCONCLUSIVE,
        smtp_code=None, smtp_message="all_mx_inconclusive",
    )


def is_catch_all(
    catch_all_probe_email: str,
    mx_records: Sequence[str],
    timeout: float = SMTP_TIMEOUT,
) -> bool:
    """Probe un email aleatorio que NADIE deberia tener. Si responde 250,
    el dominio es catch-all (acepta todo) -> los probes reales son
    falsos positivos. Si responde 550, el dominio rechaza correctamente.

    Returns:
        True = catch-all detectado, skip dominio.
        False = catch-all NO detectado, los probes posteriores son fiables.
    """
    result = probe_email(catch_all_probe_email, mx_records, timeout=timeout)
    return result.status == EmailStatus.VALID
