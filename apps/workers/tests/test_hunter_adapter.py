"""Tests de shared.hunter_adapter.

Sin red real: usa `httpx.MockTransport` con un handler que el test controla.
Los tests de retry monkey-patchean el `wait` de tenacity a `wait_none()`
para que la suite no tarde minutos.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from tenacity import wait_none

from shared.email_finder import Contact
from shared.hunter_adapter import (
    HunterAdapter,
    HunterAuthError,
    HunterError,
    HunterRateLimitError,
)

# ─── Helpers ───────────────────────────────────────────────────────────────


def _make_adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    api_key: str = "test-key",
) -> HunterAdapter:
    """Construye un adapter con cliente httpx que usa MockTransport."""
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return HunterAdapter(api_key=api_key, base_url="https://api.hunter.io/v2/", client=client)


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anula el wait de tenacity en `_get` para que los tests de retry
    no esperen segundos reales. La política de retry (3 intentos, qué
    se reintenta) se preserva."""
    from shared import hunter_adapter

    # tenacity decorator está envuelto en _get.retry. Sobrescribimos `wait`.
    hunter_adapter.HunterAdapter._get.retry.wait = wait_none()  # type: ignore[attr-defined]


# Response real-shaped, una empresa T3 (basado en formato de probe_hunter):
_DOMAIN_SEARCH_OK = {
    "data": {
        "domain": "acme.es",
        "organization": "ACME SL",
        "emails": [
            {
                "value": "juan.perez@acme.es",
                "first_name": "Juan",
                "last_name": "Pérez",
                "position": "Director General",
                "confidence": 92,
                "seniority": "executive",
                "department": "executive",
            },
            {
                "value": "info@acme.es",
                "first_name": None,
                "last_name": None,
                "position": None,
                "confidence": 75,
            },
        ],
    },
    "meta": {"results": 2, "limit": 10, "offset": 0},
}


# ─── 1. Domain Search éxito ────────────────────────────────────────────────


def test_find_contacts_by_domain_parses_real_shaped_response() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json=_DOMAIN_SEARCH_OK)

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("acme.es", "ACME SL")

    assert "domain-search" in captured["url"]
    assert captured["params"]["domain"] == "acme.es"
    assert captured["params"]["api_key"] == "test-key"
    assert captured["params"]["limit"] == "10"
    assert "company" not in captured["params"]

    assert contacts == [
        Contact(
            email="juan.perez@acme.es",
            position="Director General",
            person_name="Juan Pérez",
            confidence=92,
            source="hunter",
        ),
        Contact(
            email="info@acme.es",
            position=None,
            person_name=None,
            confidence=75,
            source="hunter",
        ),
    ]


def test_find_contacts_by_company_uses_company_param() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json=_DOMAIN_SEARCH_OK)

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_company("ACME SL", "Madrid")

    assert captured["params"]["company"] == "ACME SL"
    assert "domain" not in captured["params"]
    assert len(contacts) == 2


def test_empty_emails_list_returns_empty() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"domain": "x.es", "emails": []}})

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("x.es", "X SL")

    assert contacts == []


def test_missing_data_key_returns_empty() -> None:
    """Defensivo: response 200 sin clave `data` no rompe."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"meta": {}})

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("x.es", "X SL")

    assert contacts == []


# ─── 2. Domain Search códigos no-200 esperados ─────────────────────────────


def test_status_400_returns_empty() -> None:
    """Hunter devuelve 400 cuando no resuelve `company` a un dominio.
    Comportamiento esperado en T1/T4 fuzzy. NO es error."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"id": "company_not_found"}]})

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_company("Empresa Inventada SL", "Madrid")

    assert contacts == []


def test_status_404_returns_empty() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": [{"id": "not_found"}]})

    with _make_adapter(handler) as h:
        assert h.find_contacts_by_domain("noexiste.invalid", "X") == []


def test_status_401_raises_auth_error_no_retry() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"errors": [{"id": "unauthorized"}]})

    with _make_adapter(handler) as h, pytest.raises(HunterAuthError):
        h.find_contacts_by_domain("acme.es", "ACME")

    assert calls["n"] == 1, "401 NO debe reintentarse"


# ─── 3. Domain Search códigos transitorios (con retry) ─────────────────────


def test_status_429_retries_and_eventually_raises_rate_limit() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"errors": [{"id": "rate_limit"}]})

    with _make_adapter(handler) as h, pytest.raises(HunterRateLimitError):
        h.find_contacts_by_domain("acme.es", "ACME")

    assert calls["n"] == 3, "429 debe reintentarse hasta 3 veces"


def test_status_500_retries_and_eventually_raises_hunter_error() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="Internal Server Error")

    with _make_adapter(handler) as h, pytest.raises(HunterError):
        h.find_contacts_by_domain("acme.es", "ACME")

    assert calls["n"] == 3


def test_status_503_retries_and_eventually_succeeds() -> None:
    """Si tras 1-2 fallos transitorios el servidor responde, debe devolver datos."""
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json=_DOMAIN_SEARCH_OK)

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("acme.es", "ACME")

    assert calls["n"] == 3
    assert len(contacts) == 2


def test_timeout_retries() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("simulated timeout")

    with _make_adapter(handler) as h, pytest.raises(httpx.TimeoutException):
        h.find_contacts_by_domain("acme.es", "ACME")

    assert calls["n"] == 3


# ─── 4. Email Finder ───────────────────────────────────────────────────────


def test_find_email_by_name_success() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["params"] = dict(req.url.params)
        return httpx.Response(
            200,
            json={"data": {"email": "juan.perez@acme.es", "score": 87}},
        )

    with _make_adapter(handler) as h:
        email = h.find_email_by_name("Juan Pérez", "acme.es")

    assert "email-finder" in captured["url"]
    assert captured["params"]["full_name"] == "Juan Pérez"
    assert captured["params"]["domain"] == "acme.es"
    assert email == "juan.perez@acme.es"


def test_find_email_by_name_returns_none_when_email_null() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"email": None, "score": 0}})

    with _make_adapter(handler) as h:
        email = h.find_email_by_name("Persona Inexistente", "acme.es")

    assert email is None


def test_find_email_by_name_404_returns_none() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": []})

    with _make_adapter(handler) as h:
        assert h.find_email_by_name("X", "x.es") is None


def test_find_email_by_name_401_raises_auth_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": []})

    with _make_adapter(handler) as h, pytest.raises(HunterAuthError):
        h.find_email_by_name("X", "x.es")


def test_find_email_by_name_validates_inputs() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"email": "x@y.es", "score": 50}})

    with _make_adapter(handler) as h:
        with pytest.raises(ValueError):
            h.find_email_by_name("", "acme.es")
        with pytest.raises(ValueError):
            h.find_email_by_name("Juan", "")
        with pytest.raises(ValueError):
            h.find_email_by_name("   ", "acme.es")


# ─── 5. Construcción del adapter ───────────────────────────────────────────


def test_constructor_raises_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin api_key explícito y sin HUNTER_API_KEY en settings, debe fallar."""
    from shared import hunter_adapter as ha

    monkeypatch.setattr(ha.settings, "HUNTER_API_KEY", None)
    with pytest.raises(RuntimeError, match="HUNTER_API_KEY"):
        HunterAdapter()


def test_explicit_api_key_overrides_settings() -> None:
    """api_key explícito gana sobre settings (útil en tests)."""
    h = HunterAdapter(api_key="explicit-key")
    assert h._api_key == "explicit-key"
    h.close()


# ─── 6. Ownership del cliente httpx ────────────────────────────────────────


def test_owned_client_closed_on_exit() -> None:
    """Si el adapter creó el cliente, se cierra al salir del `with`."""
    h = HunterAdapter(api_key="x")
    client = h._client
    assert h._owns_client is True
    h.close()
    assert client.is_closed


def test_injected_client_not_closed_on_exit() -> None:
    """Si el cliente se inyecta, NO se cierra (el caller mantiene ownership)."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": {}}))
    client = httpx.Client(transport=transport)
    h = HunterAdapter(api_key="x", client=client)
    assert h._owns_client is False
    with h:
        pass  # exit triggers __exit__
    assert not client.is_closed
    client.close()


# ─── 7. Source attribution ─────────────────────────────────────────────────


def test_all_returned_contacts_have_source_hunter() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_DOMAIN_SEARCH_OK)

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("acme.es", "ACME")

    assert all(c.source == "hunter" for c in contacts)


# ─── 8. Robustez de parsing ────────────────────────────────────────────────


def test_string_confidence_is_coerced_to_int() -> None:
    """Si Hunter devolviera confidence como string (raro), se convierte a int."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "domain": "x.es",
                    "emails": [{"value": "a@x.es", "confidence": "75"}],
                }
            },
        )

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("x.es", "X")

    assert contacts[0].confidence == 75


def test_invalid_confidence_becomes_none() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "domain": "x.es",
                    "emails": [{"value": "a@x.es", "confidence": "garbage"}],
                }
            },
        )

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("x.es", "X")

    assert contacts[0].confidence is None


def test_partial_name_handles_missing_last_name() -> None:
    """Hunter puede devolver solo first_name."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "domain": "x.es",
                    "emails": [
                        {"value": "a@x.es", "first_name": "Juan", "last_name": None}
                    ],
                }
            },
        )

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("x.es", "X")

    assert contacts[0].person_name == "Juan"


def test_no_name_at_all_yields_none_person_name() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "domain": "x.es",
                    "emails": [{"value": "info@x.es"}],
                }
            },
        )

    with _make_adapter(handler) as h:
        contacts = h.find_contacts_by_domain("x.es", "X")

    assert contacts[0].person_name is None
    assert contacts[0].position is None
    assert contacts[0].source == "hunter"
