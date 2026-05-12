"""GmailAdapter -- envio Gmail API via OAuth refresh_token.

Sprint 4 paso 7. Envia emails RFC 2822 desde un buzon configurado en Google
Workspace usando OAuth offline_access (refresh_token de larga duracion).

Setup OAuth previo (bloqueador humano B1, fuera de este modulo):
1. Google Cloud Console: proyecto + Gmail API habilitado + OAuth client
   (Desktop o Web) con scope `https://www.googleapis.com/auth/gmail.send`.
2. Flow OAuth standalone una vez por buzon para obtener `refresh_token`.
3. Persistir `refresh_token` cifrado en `mailboxes.oauth_refresh_token_encrypted`
   (Supabase Vault). Para dev local de pruebas, GMAIL_OAUTH_REFRESH_TOKEN en
   `.env.dev` permite trabajar sin BD.

Access token cache:
- Refresh access_token via POST a https://oauth2.googleapis.com/token.
- Cache in-memory con expiry; refresh cuando quedan <60s o tras 401.

Resiliencia:
- Retry con tenacity sobre 429/5xx/timeout (3 intentos, exp backoff 1-4s).
- 401 levanta GmailAuthError sin retry (refresh_token revocado o credenciales).
- Errores 4xx no-auth (400 invalid recipient, 403 quota) devuelven SendResult
  con error poblado para que send_gmail.py decida (bounce vs failed).

NOTA importante sobre bounce detection:
- Gmail API 200 = "encolado por Google", NO "entregado al destinatario".
- Hard bounces reales llegan como DSN email al buzon -> requieren poll_imap
  (Fase 3). Para paso 7 nos quedamos con bounces sincronos (400/403/422
  con codigos de Gmail que indican direccion invalida o cuota). auto_pause
  vigila esos como senal temprana; hard bounces invisibles del paso 7
  quedan como deuda tecnica conocida hasta Fase 3 (inbox + poll_imap).
"""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings

logger = logging.getLogger("demin.gmail")
if not logger.handlers:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

_GMAIL_TIMEOUT_S = 30.0
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_ACCESS_TOKEN_SAFETY_SECS = 60
"""Refresh el access_token cuando le queden <60s para evitar carrera."""


# --- Excepciones del modulo ------------------------------------------------


class GmailError(Exception):
    """Error general Gmail (5xx tras agotar reintentos, parsing, etc.)."""


class GmailAuthError(GmailError):
    """401 Unauthorized -- refresh_token revocado o client_id/secret invalidos.
    NO se reintenta. send_gmail.py debe parar y reportar."""


class GmailQuotaError(GmailError):
    """429 Too Many Requests / 403 quota exceeded tras agotar reintentos."""


# Internal sentinel for tenacity retry sobre 429/5xx en el body
class _GmailTransientError(Exception):
    pass


# --- Resultado de envio ----------------------------------------------------


@dataclass(slots=True)
class SendResult:
    """Resultado de `send_email`. `gmail_message_id` y `sent_at` poblados
    en exito (200). `error` poblado en fallo no-auth (4xx no-401, o 5xx
    tras retries) para que el caller persista `status='failed'` o
    `status='bounced'` segun corresponda."""

    success: bool
    gmail_message_id: str | None
    sent_at: datetime | None
    error: str | None
    http_status: int | None
    raw_response: dict[str, Any] | None


# --- Adapter ---------------------------------------------------------------


class GmailAdapter:
    """Adapter Gmail API por buzon. Un adapter = un mailbox.

    Inyectable en tests: `client` permite pasar un `httpx.Client` con
    `MockTransport` para tests sin red.

    Uso tipico:
        with GmailAdapter(
            from_email="gonzalo.perez@demingroupmadrid.com",
            from_display="Gonzalo Perez",
            refresh_token=mailbox.oauth_refresh_token,
        ) as g:
            result = g.send_email(
                to="prospecto@empresa.es",
                subject="...",
                body="...",
            )
    """

    def __init__(
        self,
        from_email: str,
        from_display: str,
        refresh_token: str,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        sending_domain: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._from_email = from_email
        self._from_display = from_display
        self._refresh_token = refresh_token

        cid = client_id if client_id is not None else settings.GMAIL_OAUTH_CLIENT_ID
        csecret = (
            client_secret
            if client_secret is not None
            else settings.GMAIL_OAUTH_CLIENT_SECRET
        )
        if not cid or not csecret:
            raise RuntimeError(
                "GMAIL_OAUTH_CLIENT_ID/SECRET no configurados. Resuelve el "
                "bloqueador humano B1 (Google Cloud Console OAuth) antes de "
                "instanciar GmailAdapter en runtime."
            )
        self._client_id: str = cid
        self._client_secret: str = csecret
        self._sending_domain: str = sending_domain or settings.SENDING_DOMAIN

        if client is None:
            self._client = httpx.Client(timeout=_GMAIL_TIMEOUT_S)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

        # Cache in-memory del access_token + expiry
        self._access_token: str | None = None
        self._access_token_expiry: datetime | None = None

    def __enter__(self) -> GmailAdapter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- API publica -------------------------------------------------------

    def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> SendResult:
        """Envia un email. `in_reply_to` (Message-ID de un email previo) se
        usa para hilos en follow-ups (D+4/D+10) — mantiene el thread agrupado
        en Gmail/Outlook del destinatario."""

        raw = self._build_raw_message(
            to=to, subject=subject, body=body, in_reply_to=in_reply_to
        )

        try:
            status, body_resp, elapsed_ms = self._send_with_retry(raw)
        except GmailAuthError:
            raise
        except _GmailTransientError as e:
            raise GmailQuotaError(str(e)) from e

        if status == 200:
            gmail_id = body_resp.get("id") if isinstance(body_resp, dict) else None
            logger.info(
                "gmail_send ok from=%s to=%s subject=%r gmail_id=%s elapsed_ms=%d",
                self._from_email, to, subject[:40], gmail_id, elapsed_ms,
            )
            return SendResult(
                success=True,
                gmail_message_id=gmail_id,
                sent_at=datetime.now(timezone.utc),
                error=None,
                http_status=200,
                raw_response=body_resp,
            )

        # 4xx no-auth: error sincrono. El caller decide si tratar como
        # bounced (invalid recipient, dominio inexistente) o failed (otros).
        err_msg = _extract_error_message(body_resp)
        logger.warning(
            "gmail_send fail from=%s to=%s status=%d err=%r elapsed_ms=%d",
            self._from_email, to, status, err_msg, elapsed_ms,
        )
        return SendResult(
            success=False,
            gmail_message_id=None,
            sent_at=None,
            error=err_msg,
            http_status=status,
            raw_response=body_resp,
        )

    # --- Construccion del mensaje RFC 2822 --------------------------------

    def _build_raw_message(
        self, *, to: str, subject: str, body: str, in_reply_to: str | None
    ) -> str:
        msg = MIMEText(body, _subtype="plain", _charset="utf-8")
        msg["From"] = f'"{self._from_display}" <{self._from_email}>'
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self._sending_domain)
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")

    # --- OAuth refresh access_token --------------------------------------

    def _get_access_token(self) -> str:
        now = datetime.now(timezone.utc)
        if (
            self._access_token
            and self._access_token_expiry
            and self._access_token_expiry > now + timedelta(seconds=_ACCESS_TOKEN_SAFETY_SECS)
        ):
            return self._access_token

        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }
        started = time.monotonic()
        r = self._client.post(_OAUTH_TOKEN_URL, data=data)
        elapsed = int((time.monotonic() - started) * 1000)

        if r.status_code == 401 or r.status_code == 400:
            try:
                body_err = r.json()
            except ValueError:
                body_err = {"error": r.text[:200]}
            raise GmailAuthError(
                f"OAuth refresh fallo status={r.status_code} body={body_err!r}"
            )
        if r.status_code != 200:
            raise GmailError(
                f"OAuth refresh status inesperado {r.status_code}: {r.text[:200]}"
            )

        body = r.json()
        token = body.get("access_token")
        expires_in = body.get("expires_in", 3600)
        if not isinstance(token, str) or not token:
            raise GmailError(f"OAuth refresh sin access_token en body: {body!r}")

        self._access_token = token
        self._access_token_expiry = now + timedelta(seconds=int(expires_in))
        logger.info(
            "gmail_oauth_refresh ok from=%s expires_in=%ss elapsed_ms=%d",
            self._from_email, expires_in, elapsed,
        )
        return token

    # --- Send HTTP con retry ----------------------------------------------

    @retry(
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.ConnectError,
            _GmailTransientError,
        )),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _send_with_retry(self, raw: str) -> tuple[int, dict[str, Any], int]:
        access_token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {"raw": raw}
        started = time.monotonic()
        r = self._client.post(_GMAIL_SEND_URL, headers=headers, json=payload)
        elapsed = int((time.monotonic() - started) * 1000)

        if r.status_code == 401:
            # access_token caducado o revocado. Invalidamos cache y
            # levantamos auth error si el refresh tambien falla (lo hace
            # _get_access_token en el siguiente intento del send_email).
            self._access_token = None
            self._access_token_expiry = None
            raise GmailAuthError(
                f"401 Gmail send -- access_token invalido o scope insuficiente"
            )
        if r.status_code == 429:
            raise _GmailTransientError(f"429 rate limit en gmail send")
        if 500 <= r.status_code < 600:
            raise _GmailTransientError(f"{r.status_code} server error en gmail send")

        try:
            body: dict[str, Any] = r.json()
        except ValueError:
            body = {}

        return r.status_code, body, elapsed


# --- Helpers ----------------------------------------------------------------


def _extract_error_message(body: dict[str, Any] | None) -> str:
    """Gmail API error body tipico:
        {"error": {"code": 400, "message": "Invalid To header"}}
    """
    if not isinstance(body, dict):
        return "respuesta sin body JSON"
    err = body.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str) and msg:
            return msg
    return str(body)[:200]
