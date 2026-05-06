"""HunterAdapter — implementación concreta de `EmailFinder` para Hunter.io.

Sprint 4 paso 3 (D21). Único adapter operativo en el roadmap actual.
Encapsula:

- Hunter Domain Search por dominio  → `find_contacts_by_domain`.
- Hunter Domain Search por company  → `find_contacts_by_company` (fuzzy,
  fallback gratis si la empresa no tiene web).
- Hunter Email Finder por nombre    → `find_email_by_name` (extensión §8.6
  para T2 enriquecido cuando `find_contacts.py` no encuentra match en
  `personas_extraidas`).

Resiliencia:
- Retries con tenacity sobre errores transitorios (429, 5xx, timeout,
  conexión). 3 intentos, exp backoff 1-4s. Idéntico patrón a `llm.py`.
- 4xx (400, 401, 404) NO se reintentan: 401 levanta `HunterAuthError`,
  400/404 devuelven `[]` (Hunter no resolvió la empresa, comportamiento
  esperado en T1/T4).

NO clasifica los emails. La clasificación según D20 (decisor / nominal /
corporativo_pequeno / descartado) la hace `email_policy.classify_email`
después en el worker `find_contacts.py`.

Plan Free Hunter: 25 búsquedas/mes (limit=10 emails por response). Para
volumen mayor habrá que subir a Starter (~30-45€/mes), evaluación tras
Sprint 4 productivo.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .email_finder import Contact

logger = logging.getLogger("demin.hunter")
if not logger.handlers:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

_HUNTER_TIMEOUT_S = 30.0
_HUNTER_DEFAULT_LIMIT = 10  # plan Free


# ─── Excepciones del módulo ────────────────────────────────────────────────


class HunterError(Exception):
    """Error general de Hunter (5xx tras agotar reintentos, parsing, etc.)."""


class HunterAuthError(HunterError):
    """401 Unauthorized — api key inválida o suspendida. NO se reintenta."""


class HunterRateLimitError(HunterError):
    """429 Too Many Requests tras agotar reintentos."""


# Wrapper interno usado solo para que tenacity dispare retry sobre 429/5xx
# devueltos en el body, no como excepciones HTTP de httpx.
class _HunterTransientError(Exception):
    pass


# ─── Adapter ───────────────────────────────────────────────────────────────


class HunterAdapter:
    """Adapter Hunter.io. Cumple `EmailFinder` (§8.6).

    Inyectable en tests: `client` permite pasar un `httpx.Client` con
    `MockTransport` para tests sin red. Si no se pasa, el adapter crea
    su propio cliente y lo cierra al salir del context manager.

    Uso típico:
        with HunterAdapter() as h:
            contacts = h.find_contacts_by_domain("acme.es", "ACME SL")
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        limit: int = _HUNTER_DEFAULT_LIMIT,
    ) -> None:
        key = api_key if api_key is not None else settings.HUNTER_API_KEY
        if not key:
            raise RuntimeError(
                "HUNTER_API_KEY no está configurada. Reasentar en .env.dev "
                "(Bitwarden item `Hunter API`) antes de instanciar HunterAdapter."
            )
        self._api_key: str = key
        self._base_url: str = (base_url or settings.HUNTER_BASE_URL).rstrip("/")
        self._limit: int = limit
        if client is None:
            self._client = httpx.Client(timeout=_HUNTER_TIMEOUT_S)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    def __enter__(self) -> HunterAdapter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Cierra el cliente httpx si fue creado por el adapter. Si fue
        inyectado, no se toca (ownership semantics)."""
        if self._owns_client:
            self._client.close()

    # ─── métodos públicos del Protocol ─────────────────────────────────────

    def find_contacts_by_domain(self, domain: str, company_name: str) -> list[Contact]:
        return self._domain_search(domain=domain, company=None, label=domain)

    def find_contacts_by_company(self, company_name: str, location: str) -> list[Contact]:
        return self._domain_search(domain=None, company=company_name, label=company_name)

    def find_email_by_name(self, full_name: str, domain: str) -> str | None:
        return self._email_finder(full_name=full_name, domain=domain)

    # ─── HTTP wrappers con retry ───────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.ConnectError,
            _HunterTransientError,
        )),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _get(self, endpoint: str, params: dict[str, Any]) -> tuple[int, dict[str, Any], int]:
        """GET a `<base_url>/<endpoint>` con `params`. Devuelve (status, body, elapsed_ms).

        429 y 5xx levantan `_HunterTransientError` para que tenacity los
        reintente. 401 levanta `HunterAuthError` (no retry). 4xx restantes
        (400/404) devuelven al caller para que decida.
        """
        full_params = {"api_key": self._api_key, **params}
        url = f"{self._base_url}/{endpoint}"
        started = time.monotonic()
        r = self._client.get(url, params=full_params)
        elapsed = int((time.monotonic() - started) * 1000)

        if r.status_code == 401:
            raise HunterAuthError(
                f"401 Unauthorized en {endpoint} — api key inválida o suspendida"
            )
        if r.status_code == 429:
            raise _HunterTransientError(f"429 rate limit en {endpoint}")
        if 500 <= r.status_code < 600:
            raise _HunterTransientError(f"{r.status_code} server error en {endpoint}")

        try:
            body: dict[str, Any] = r.json()
        except ValueError:
            # JSON inválido en respuesta no-200: devolvemos error de parsing
            # como "transient" para que tenacity reintente; en 200 con JSON
            # malformado lo trata el caller (caller ve dict vacío).
            if r.status_code != 200:
                raise _HunterTransientError(
                    f"{r.status_code} con body no-JSON en {endpoint}"
                ) from None
            body = {}

        return r.status_code, body, elapsed

    # ─── parsing ───────────────────────────────────────────────────────────

    def _domain_search(
        self,
        *,
        domain: str | None,
        company: str | None,
        label: str,
    ) -> list[Contact]:
        """Llama Domain Search. `domain` o `company`, no ambos."""
        if not domain and not company:
            raise ValueError("domain o company es obligatorio")
        params: dict[str, Any] = {"limit": self._limit}
        if domain:
            params["domain"] = domain
        else:
            params["company"] = company

        try:
            status, body, elapsed = self._get("domain-search", params)
        except HunterAuthError:
            raise
        except _HunterTransientError as e:
            raise HunterRateLimitError(str(e)) from e

        if status in (400, 404):
            logger.info(
                "hunter_domain_search no_resuelto status=%d label=%s elapsed_ms=%d",
                status, label, elapsed,
            )
            return []
        if status != 200:
            # 200/4xx-conocidos ya manejados; otros 4xx caen aquí.
            raise HunterError(f"http {status} inesperado en domain-search: {body}")

        data = body.get("data") or {}
        emails_raw = data.get("emails") or []
        contacts = [_to_contact(item) for item in emails_raw]
        logger.info(
            "hunter_domain_search ok label=%s n_emails=%d resolved=%s elapsed_ms=%d",
            label, len(contacts), data.get("domain"), elapsed,
        )
        return contacts

    def _email_finder(self, *, full_name: str, domain: str) -> str | None:
        """Llama Email Finder por nombre+dominio.

        Hunter splittea automáticamente `full_name` si se pasa así, o
        acepta `first_name`/`last_name` separados. Usamos `full_name` para
        no asumir convención de nombres.
        """
        if not full_name.strip() or not domain.strip():
            raise ValueError("full_name y domain son obligatorios y no vacíos")
        params: dict[str, Any] = {"full_name": full_name, "domain": domain}

        try:
            status, body, elapsed = self._get("email-finder", params)
        except HunterAuthError:
            raise
        except _HunterTransientError as e:
            raise HunterRateLimitError(str(e)) from e

        if status in (400, 404):
            logger.info(
                "hunter_email_finder no_resuelto status=%d name=%s domain=%s elapsed_ms=%d",
                status, full_name, domain, elapsed,
            )
            return None
        if status != 200:
            raise HunterError(f"http {status} inesperado en email-finder: {body}")

        data = body.get("data") or {}
        email = data.get("email")
        logger.info(
            "hunter_email_finder ok name=%s domain=%s found=%s score=%s elapsed_ms=%d",
            full_name, domain, bool(email), data.get("score"), elapsed,
        )
        return email if isinstance(email, str) and email else None


def _to_contact(item: dict[str, Any]) -> Contact:
    """Convierte un email de la respuesta Domain Search en `Contact`."""
    first = (item.get("first_name") or "").strip()
    last = (item.get("last_name") or "").strip()
    name = (first + " " + last).strip() or None
    confidence = item.get("confidence")
    if confidence is not None and not isinstance(confidence, int):
        try:
            confidence = int(confidence)
        except (TypeError, ValueError):
            confidence = None
    return Contact(
        email=item.get("value", ""),
        position=item.get("position"),
        person_name=name,
        confidence=confidence,
        source="hunter",
    )
