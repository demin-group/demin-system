"""Interfaz `EmailFinder` y stubs descartados.

Reescrito 2026-05-06 (Sprint 4 paso 3, D21). Fuente arquitectónica: §8.6
del plan. La interfaz desacopla `find_contacts.py` del cliente concreto
del adapter primario.

Estado por adapter (Lección 21 aplicada 4 veces):
- `HunterAdapter`         — único adapter operativo (D21). Vive en
                            `shared/hunter_adapter.py`.
- `SkrappAdapter`         — descartado por API Enterprise $262/mes (D19).
- `ApolloAdapter`         — descartado, people endpoints gated en Free (Frente D).
- `RocketReachAdapter`    — descartado por API Ultimate $2.484/año (D17→D19).

Los tres descartados quedan como stubs que cumplen el `Protocol` y
devuelven listas vacías / None. Coste de mantenerlos es cero y evita
reabrir la abstracción si alguno cambia su pricing/access en el futuro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Contact:
    """Contacto devuelto por un adapter de email finder.

    Campos mínimos comunes a Hunter / Skrapp / Apollo / RocketReach. NO
    incluye `email_type` ni `email_priority` — esos los rellena
    `find_contacts.py` (paso 4) tras pasar por `email_policy.classify_email`.
    NO incluye `is_primary` — esa decisión es del worker, no del adapter.

    `source` traza el adapter que devolvió el dato; va a `contacts.email_source`
    al insertar.
    """

    email: str
    position: str | None = None
    person_name: str | None = None
    confidence: int | None = None  # Hunter: 0..100; Skrapp/Apollo análogo
    source: str = "manual"


@runtime_checkable
class EmailFinder(Protocol):
    """Contrato común de los adapters de email finder (§8.6).

    Métodos renombrados desde `find_decisors_*` a `find_contacts_*`
    para reflejar la jerarquía de aceptación de D20 (decisor + nominal +
    corporativo_pequeno). El adapter NO clasifica; sólo devuelve lo que
    su backend reporte. La clasificación se hace después con
    `email_policy.classify_email`.
    """

    def find_contacts_by_domain(self, domain: str, company_name: str) -> list[Contact]: ...

    def find_contacts_by_company(self, company_name: str, location: str) -> list[Contact]: ...

    def find_email_by_name(self, full_name: str, domain: str) -> str | None: ...


# ─── Stubs descartados ─────────────────────────────────────────────────────
# Los tres devuelven [] / None. El motivo de descarte está en el docstring
# para que un futuro lector del código entienda por qué no se llaman desde
# `find_contacts.py`. Si alguno vuelve viable, la implementación concreta
# sustituye al stub sin cambiar la firma.


class SkrappAdapter:
    """Stub. Skrapp descartado: API Enterprise $262/mes excede el techo D15
    (150€/mes total). Decisión D19 (Lección 21 aplicada). Si en el futuro
    Skrapp libera su Bulk Email Finder en el plan Starter, este stub se
    sustituye por la implementación real.
    """

    def find_contacts_by_domain(self, domain: str, company_name: str) -> list[Contact]:
        return []

    def find_contacts_by_company(self, company_name: str, location: str) -> list[Contact]:
        return []

    def find_email_by_name(self, full_name: str, domain: str) -> str | None:
        return None


class ApolloAdapter:
    """Stub. Apollo descartado: people endpoints gated en plan Free (sólo
    Master Plan los expone). Decisión tras Frente D 2026-05-06 (Lección 21
    aplicada). Si Apollo libera el endpoint en Free, este stub se sustituye.
    """

    def find_contacts_by_domain(self, domain: str, company_name: str) -> list[Contact]:
        return []

    def find_contacts_by_company(self, company_name: str, location: str) -> list[Contact]:
        return []

    def find_email_by_name(self, full_name: str, domain: str) -> str | None:
        return None


class RocketReachAdapter:
    """Stub. RocketReach descartado: API requiere plan Ultimate $2.484/año,
    excede el techo D15. Decisión D17→D19 (Lección 21 originaria). Mantener
    el stub permite reactivarlo sin reabrir la abstracción si en algún
    momento bajan el gating del API.
    """

    def find_contacts_by_domain(self, domain: str, company_name: str) -> list[Contact]:
        return []

    def find_contacts_by_company(self, company_name: str, location: str) -> list[Contact]:
        return []

    def find_email_by_name(self, full_name: str, domain: str) -> str | None:
        return None
