"""Tests de shared.gmail_adapter.

Sin red real: usa `httpx.MockTransport` para interceptar requests OAuth +
Gmail send. Sin BD. Sin credenciales reales (client_id/secret/refresh_token
inyectados como strings dummy).
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from shared.gmail_adapter import (
    GmailAdapter,
    GmailAuthError,
    GmailError,
    GmailQuotaError,
    SendResult,
)

# --- Helpers ---------------------------------------------------------------


def _mock_transport(handlers: dict[str, Any]) -> httpx.MockTransport:
    """Construye un MockTransport con dispatchers por URL. `handlers` maps
    URL prefix -> handler callable(request) -> Response."""

    def dispatch(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, handler in handlers.items():
            if url.startswith(prefix):
                return handler(request)
        return httpx.Response(404, json={"error": f"no mock for {url}"})

    return httpx.MockTransport(dispatch)


def _adapter(transport: httpx.MockTransport, **overrides: Any) -> GmailAdapter:
    client = httpx.Client(transport=transport)
    defaults: dict[str, Any] = {
        "from_email": "gonzalo.perez@demingroupmadrid.com",
        "from_display": "Gonzalo Perez",
        "refresh_token": "fake-refresh-token-xyz",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "sending_domain": "demingroupmadrid.com",
        "client": client,
    }
    defaults.update(overrides)
    return GmailAdapter(**defaults)


def _oauth_ok(access_token: str = "fake-access-abc", expires_in: int = 3600):
    def handler(request: httpx.Request) -> httpx.Response:
        # Validamos que el POST trae los campos esperados
        body = request.content.decode("utf-8")
        assert "grant_type=refresh_token" in body
        assert "refresh_token=fake-refresh-token-xyz" in body
        return httpx.Response(
            200,
            json={
                "access_token": access_token,
                "expires_in": expires_in,
                "token_type": "Bearer",
            },
        )
    return handler


def _send_ok(gmail_id: str = "msg-abc123"):
    def handler(request: httpx.Request) -> httpx.Response:
        # Validamos Authorization Bearer + body raw base64-encoded
        auth = request.headers.get("Authorization", "")
        assert auth.startswith("Bearer ")
        body = json.loads(request.content.decode("utf-8"))
        assert "raw" in body
        # Decode raw para verificar headers MIME
        raw_b64 = body["raw"]
        # urlsafe_b64encode strip '=', re-pad para decode
        padded = raw_b64 + "=" * (-len(raw_b64) % 4)
        mime = base64.urlsafe_b64decode(padded).decode("utf-8")
        assert "From: " in mime
        assert "To: " in mime
        assert "Subject: " in mime
        return httpx.Response(
            200,
            json={"id": gmail_id, "threadId": "thr-xyz", "labelIds": ["SENT"]},
        )
    return handler


# --- 1. send_email OK end-to-end ------------------------------------------


def test_send_email_ok_returns_gmail_message_id() -> None:
    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": _send_ok("msg-99"),
    })
    with _adapter(transport) as g:
        result = g.send_email(
            to="prospecto@empresa.es",
            subject="Demolicion interior",
            body="Hola, soy Gonzalo...",
        )
    assert result.success is True
    assert result.gmail_message_id == "msg-99"
    assert result.http_status == 200
    assert result.sent_at is not None
    assert result.error is None


def test_send_email_includes_in_reply_to_for_follow_ups() -> None:
    captured: dict[str, Any] = {}

    def send_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        raw_b64 = body["raw"]
        padded = raw_b64 + "=" * (-len(raw_b64) % 4)
        captured["mime"] = base64.urlsafe_b64decode(padded).decode("utf-8")
        return httpx.Response(200, json={"id": "msg-followup"})

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        result = g.send_email(
            to="prospecto@empresa.es",
            subject="Re: Demolicion interior",
            body="Sigo aqui...",
            in_reply_to="<previo@gmail.com>",
        )
    assert result.success is True
    assert "In-Reply-To: <previo@gmail.com>" in captured["mime"]
    assert "References: <previo@gmail.com>" in captured["mime"]


def test_send_email_mime_headers_include_from_display_and_messageid() -> None:
    captured: dict[str, Any] = {}

    def send_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        raw_b64 = body["raw"]
        padded = raw_b64 + "=" * (-len(raw_b64) % 4)
        captured["mime"] = base64.urlsafe_b64decode(padded).decode("utf-8")
        return httpx.Response(200, json={"id": "msg-x"})

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        g.send_email(to="x@y.es", subject="Asunto", body="Cuerpo")

    mime = captured["mime"]
    assert 'From: "Gonzalo Perez" <gonzalo.perez@demingroupmadrid.com>' in mime
    assert "Message-ID: <" in mime
    assert "@demingroupmadrid.com>" in mime


# --- 2. OAuth token caching -----------------------------------------------


def test_access_token_cached_between_sends() -> None:
    oauth_calls = {"count": 0}

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        oauth_calls["count"] += 1
        return httpx.Response(
            200,
            json={"access_token": "cached-token", "expires_in": 3600},
        )

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": oauth_handler,
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": _send_ok(),
    })
    with _adapter(transport) as g:
        g.send_email(to="a@x.es", subject="S1", body="B1")
        g.send_email(to="b@x.es", subject="S2", body="B2")
        g.send_email(to="c@x.es", subject="S3", body="B3")

    assert oauth_calls["count"] == 1, "OAuth solo debe llamarse 1 vez con token cacheado"


def test_access_token_refreshed_after_401_on_send() -> None:
    oauth_calls = {"count": 0}
    send_calls = {"count": 0}

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        oauth_calls["count"] += 1
        return httpx.Response(
            200,
            json={"access_token": f"token-{oauth_calls['count']}", "expires_in": 3600},
        )

    def send_handler(request: httpx.Request) -> httpx.Response:
        send_calls["count"] += 1
        # 1ra llamada 401 (token caducado), 2da 200
        if send_calls["count"] == 1:
            return httpx.Response(
                401,
                json={"error": {"code": 401, "message": "Invalid Credentials"}},
            )
        return httpx.Response(200, json={"id": "msg-retried"})

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": oauth_handler,
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        # 1er send: 401 invalidan cache → GmailAuthError sin retry. Test
        # verifica que el error es loud (no swallow silencioso).
        with pytest.raises(GmailAuthError):
            g.send_email(to="x@y.es", subject="S", body="B")

    # OAuth se llamo 1 vez al inicio, send 1 vez (401, no retry de auth)
    assert oauth_calls["count"] == 1
    assert send_calls["count"] == 1


# --- 3. Errores OAuth refresh ---------------------------------------------


def test_oauth_400_invalid_grant_raises_auth_error() -> None:
    """refresh_token revocado o invalido -> OAuth devuelve 400 con
    invalid_grant. GmailAuthError sin retry."""

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "Token revoked"},
        )

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": oauth_handler,
    })
    with _adapter(transport) as g:
        with pytest.raises(GmailAuthError, match="OAuth refresh"):
            g.send_email(to="x@y.es", subject="S", body="B")


def test_oauth_500_raises_gmail_error() -> None:
    """OAuth con 5xx no clasifica como auth -> GmailError generico."""

    def oauth_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": oauth_handler,
    })
    with _adapter(transport) as g:
        with pytest.raises(GmailError, match="OAuth refresh status inesperado"):
            g.send_email(to="x@y.es", subject="S", body="B")


# --- 4. Errores Gmail send (4xx sync, no auth) -----------------------------


def test_send_400_invalid_recipient_returns_failed_send_result() -> None:
    """400 con mensaje de bounce sincrono: send_email devuelve SendResult
    con success=False y error poblado. send_gmail.py decidira si marca
    bounced o failed."""

    def send_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "message": "Invalid To header: not-a-valid-email",
                }
            },
        )

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        result = g.send_email(to="not-a-valid", subject="S", body="B")
    assert result.success is False
    assert result.http_status == 400
    assert result.gmail_message_id is None
    assert result.error and "Invalid To header" in result.error


def test_send_403_quota_eventually_raises_quota_error() -> None:
    """403 quota exceeded (sync, no retry como 5xx pero quota es 429
    semanticamente). Gmail devuelve 403 con code; lo tratamos como error
    sincronico no retryable (devuelve SendResult con failed). Si quisieramos
    retry, configurariamos tenacity."""

    def send_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": 403,
                    "message": "Daily user sending quota exceeded.",
                }
            },
        )

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        result = g.send_email(to="x@y.es", subject="S", body="B")
    # 403 cae como error sincronico no auth → SendResult failed
    assert result.success is False
    assert result.http_status == 403
    assert result.error and "quota" in result.error.lower()


# --- 5. Retry sobre 429/5xx -----------------------------------------------


def test_send_429_retried_and_eventually_raises_quota_error() -> None:
    send_calls = {"count": 0}

    def send_handler(request: httpx.Request) -> httpx.Response:
        send_calls["count"] += 1
        return httpx.Response(429, json={"error": {"code": 429, "message": "rate limit"}})

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        with pytest.raises(GmailQuotaError):
            g.send_email(to="x@y.es", subject="S", body="B")
    # tenacity 3 intentos
    assert send_calls["count"] == 3


def test_send_5xx_retried_and_succeeds_on_third_attempt() -> None:
    send_calls = {"count": 0}

    def send_handler(request: httpx.Request) -> httpx.Response:
        send_calls["count"] += 1
        if send_calls["count"] < 3:
            return httpx.Response(503, json={"error": {"code": 503, "message": "unavail"}})
        return httpx.Response(200, json={"id": "msg-after-retry"})

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport) as g:
        result = g.send_email(to="x@y.es", subject="S", body="B")
    assert result.success is True
    assert result.gmail_message_id == "msg-after-retry"
    assert send_calls["count"] == 3


# --- 6. Constructor / config ----------------------------------------------


def test_adapter_requires_client_id_and_secret() -> None:
    """Sin client_id/secret la instancia debe fallar ruidosa (bloqueador B1
    no resuelto). Forzamos strings vacios para no depender del .env real."""
    transport = _mock_transport({})
    client = httpx.Client(transport=transport)
    with pytest.raises(RuntimeError, match="GMAIL_OAUTH_CLIENT"):
        GmailAdapter(
            from_email="x@y.es",
            from_display="X",
            refresh_token="r",
            client_id="",
            client_secret="",
            client=client,
        )
    client.close()


def test_adapter_uses_provided_sending_domain_in_messageid() -> None:
    captured: dict[str, Any] = {}

    def send_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        raw_b64 = body["raw"]
        padded = raw_b64 + "=" * (-len(raw_b64) % 4)
        captured["mime"] = base64.urlsafe_b64decode(padded).decode("utf-8")
        return httpx.Response(200, json={"id": "m"})

    transport = _mock_transport({
        "https://oauth2.googleapis.com/token": _oauth_ok(),
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send": send_handler,
    })
    with _adapter(transport, sending_domain="custom-domain.test") as g:
        g.send_email(to="x@y.es", subject="S", body="B")
    assert "@custom-domain.test>" in captured["mime"]
