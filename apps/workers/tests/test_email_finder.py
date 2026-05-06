"""Tests de shared.email_finder — interfaz `EmailFinder`, `Contact`, stubs."""
from __future__ import annotations

import dataclasses

import pytest

from shared.email_finder import (
    ApolloAdapter,
    Contact,
    EmailFinder,
    RocketReachAdapter,
    SkrappAdapter,
)

# ─── Contact ───────────────────────────────────────────────────────────────


def test_contact_minimal_construction() -> None:
    c = Contact(email="a@b.es")
    assert c.email == "a@b.es"
    assert c.position is None
    assert c.person_name is None
    assert c.confidence is None
    assert c.source == "manual"


def test_contact_full_construction() -> None:
    c = Contact(
        email="juan.perez@empresa.es",
        position="Director General",
        person_name="Juan Pérez",
        confidence=92,
        source="hunter",
    )
    assert c.position == "Director General"
    assert c.person_name == "Juan Pérez"
    assert c.confidence == 92
    assert c.source == "hunter"


def test_contact_is_frozen() -> None:
    c = Contact(email="a@b.es")
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.email = "otro@b.es"  # type: ignore[misc]


def test_contact_equality() -> None:
    """Dataclasses eq=True por default; útil para asserts en otros tests."""
    a = Contact(email="x@y.es", position="CEO", source="hunter")
    b = Contact(email="x@y.es", position="CEO", source="hunter")
    assert a == b


# ─── Stubs cumplen el Protocol ─────────────────────────────────────────────


@pytest.mark.parametrize("adapter_cls", [SkrappAdapter, ApolloAdapter, RocketReachAdapter])
def test_stub_implements_email_finder_protocol(adapter_cls: type) -> None:
    """Cada stub satisface `isinstance(_, EmailFinder)` (runtime_checkable)."""
    instance = adapter_cls()
    assert isinstance(instance, EmailFinder)


@pytest.mark.parametrize("adapter_cls", [SkrappAdapter, ApolloAdapter, RocketReachAdapter])
def test_stub_find_contacts_by_domain_returns_empty(adapter_cls: type) -> None:
    a = adapter_cls()
    assert a.find_contacts_by_domain("acme.es", "ACME SL") == []


@pytest.mark.parametrize("adapter_cls", [SkrappAdapter, ApolloAdapter, RocketReachAdapter])
def test_stub_find_contacts_by_company_returns_empty(adapter_cls: type) -> None:
    a = adapter_cls()
    assert a.find_contacts_by_company("ACME SL", "Madrid") == []


@pytest.mark.parametrize("adapter_cls", [SkrappAdapter, ApolloAdapter, RocketReachAdapter])
def test_stub_find_email_by_name_returns_none(adapter_cls: type) -> None:
    a = adapter_cls()
    assert a.find_email_by_name("Juan Pérez", "acme.es") is None


def test_stubs_have_distinct_classes() -> None:
    """Defensa contra refactor accidental que colapse los 3 stubs."""
    assert SkrappAdapter is not ApolloAdapter
    assert ApolloAdapter is not RocketReachAdapter
    assert SkrappAdapter is not RocketReachAdapter
