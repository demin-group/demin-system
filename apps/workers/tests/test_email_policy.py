"""Tests de shared.email_policy — política D20.

Cubre clasificación de emails (decisor / nominal / corporativo_pequeno /
descartado) y aceptación por tier. Reglas validadas empíricamente en
Frente E (commit 36d5077).
"""
from __future__ import annotations

import dataclasses

import pytest

from shared.email_policy import (
    NEGATIVE_PREFIXES,
    POSITIVE_PREFIXES,
    Classification,
    classify_email,
    is_acceptable_for_tier,
)


def _classify(email: str, **kwargs) -> Classification:
    return classify_email(
        email=email,
        position=kwargs.get("position"),
        person_name=kwargs.get("person_name"),
        tier=kwargs.get("tier", "T3"),
    )


# ─── 1. Whitelist negativa por prefijo ─────────────────────────────────────


@pytest.mark.parametrize("prefix", sorted(NEGATIVE_PREFIXES))
def test_negative_prefix_always_discarded(prefix: str) -> None:
    """Cada prefijo de la whitelist negativa → descartado en todos los tiers."""
    for tier in ("T1", "T2", "T3", "T4"):
        result = _classify(f"{prefix}@empresa.es", tier=tier)
        assert result.email_type == "descartado", f"{prefix}@ en {tier}: {result}"


def test_negative_prefix_overrides_decisor_role() -> None:
    """Aunque el cargo asociado sea decisor, el prefijo negativo gana
    (defensa contra `marketing@` mapeado por el adapter a un cargo CEO)."""
    result = _classify("marketing@empresa.es", position="CEO")
    assert result.email_type == "descartado"


# ─── 2. Whitelist positiva por prefijo ─────────────────────────────────────


@pytest.mark.parametrize("prefix", sorted(POSITIVE_PREFIXES))
def test_positive_prefix_yields_corporativo_pequeno(prefix: str) -> None:
    """Cada prefijo positivo (sin cargo decisor) → corporativo_pequeno."""
    result = _classify(f"{prefix}@empresa.es", tier="T3")
    assert result.email_type == "corporativo_pequeno"


def test_positive_prefix_loses_to_decisor_role() -> None:
    """Si el adapter mapea `info@` con un cargo decisor, gana decisor
    (regla 3 antes que regla 4)."""
    result = _classify("info@empresa.es", position="Gerente")
    assert result.email_type == "decisor"


# ─── 3. Decisor estricto ───────────────────────────────────────────────────


@pytest.mark.parametrize("position", [
    "Gerente",
    "Director General",
    "Director Ejecutivo",
    "CEO",
    "CFO",
    "CTO",
    "COO",
    "CIO",
    "Jefe de Obra",
    "Jefe de Obras",
    "Responsable de Compras",
    "Responsable de Obras",
    "Responsable Técnico",
    "Director Técnico",
    "Director Tecnico",
    "Jefe de Proyectos",
    "Jefe de Operaciones",
    "Director Comercial",
    "Director de Operaciones",
    "Director de Proyectos",
    "Director of Projects",
    "Founder",
    "Co-Founder",
    "Cofounder",
    "Fundador",
    "Propietario",
    "Owner",
    "Presidente",
    "Operations Manager",
    "Technical Manager",
    "Technical Office Manager",
    "Plant Manager",
    "General Manager",
    "Managing Director",
    "Project Director",
    "Head of Operations",
    "Head of Construction",
    "Head of Procurement",
    "Head of Projects",
    "Socio",
    "Administrador",
])
def test_decisor_strict_positions(position: str) -> None:
    result = _classify("juan.perez@empresa.es", position=position)
    assert result.email_type == "decisor", f"position={position!r}: {result}"


def test_administrador_de_sistemas_not_decisor() -> None:
    """`Administrador de Sistemas` queda excluido por lookahead negativo →
    cae a nominal (cargo identificable no decisor)."""
    result = _classify("juan@empresa.es", position="Administrador de Sistemas")
    assert result.email_type == "nominal"


def test_bare_director_falls_to_nominal() -> None:
    """`Director` solo (sin contexto operativo ni jerárquico) → nominal."""
    result = _classify("juan@empresa.es", position="Director")
    assert result.email_type == "nominal"


def test_bare_manager_falls_to_nominal() -> None:
    """`Manager` solo → nominal (no es decisor estricto)."""
    result = _classify("juan@empresa.es", position="Manager")
    assert result.email_type == "nominal"


def test_engineer_is_nominal() -> None:
    result = _classify("juan@empresa.es", position="Engineer")
    assert result.email_type == "nominal"


def test_architect_is_nominal() -> None:
    result = _classify("juan@empresa.es", position="Architect")
    assert result.email_type == "nominal"


# ─── 4. Roles descartados ──────────────────────────────────────────────────


@pytest.mark.parametrize("position", [
    "Marketing Director",
    "Marketing Manager",
    "Communications Director",
    "Director of Communications",
    "Comunicación Corporativa",
    "Comms Lead",
    "RRHH",
    "HR Manager",
    "Recursos Humanos",
    "Human Resources Director",
    "Press Officer",
    "Prensa",
    "Prevention Specialist",
    "PRL",
    "Prevención de Riesgos",
    "Internal Audit",
    "Auditor",
    "Auditora",
    "Customer Support",
    "Customer Service",
    "Atención al Cliente",
    "Recepción",
    "Receptionist",
])
def test_negative_role_discarded(position: str) -> None:
    result = _classify("juan@empresa.es", position=position)
    assert result.email_type == "descartado", f"position={position!r}: {result}"


def test_negative_role_overrides_decisor_combo() -> None:
    """`Marketing Director` contiene 'marketing' Y 'Director'. Gana descartado
    (regla 2 antes que regla 3)."""
    result = _classify("juan@empresa.es", position="Marketing Director")
    assert result.email_type == "descartado"


# ─── 5. Caso A3 híbrido por tier ───────────────────────────────────────────


@pytest.mark.parametrize("tier", ["T1", "T3", "T4"])
def test_a3_name_no_position_yields_nominal_in_t1_t3_t4(tier: str) -> None:
    """A3: nombre + sin cargo + prefijo no whitelist → nominal en T1/T3/T4."""
    result = _classify(
        "juan.perez@empresa.es", person_name="Juan Pérez", tier=tier
    )
    assert result.email_type == "nominal"
    assert "A3" in result.reason


def test_a3_name_no_position_yields_descartado_in_t2() -> None:
    """A3: nombre + sin cargo + prefijo no whitelist → descartado en T2."""
    result = _classify(
        "juan.perez@empresa.es", person_name="Juan Pérez", tier="T2"
    )
    assert result.email_type == "descartado"
    assert "A3" in result.reason


def test_a3_name_with_positive_prefix_classified_as_corporativo() -> None:
    """Si el prefijo está en whitelist positiva, regla 4 gana sobre A3."""
    result = _classify(
        "info@empresa.es", person_name="Juan Pérez", tier="T2"
    )
    assert result.email_type == "corporativo_pequeno"


# ─── 6. Política por tier ──────────────────────────────────────────────────


def test_tier_acceptance_corporativo_pequeno() -> None:
    """corporativo_pequeno aceptado en T1/T3/T4, NO en T2."""
    assert is_acceptable_for_tier("corporativo_pequeno", "T1") is True
    assert is_acceptable_for_tier("corporativo_pequeno", "T3") is True
    assert is_acceptable_for_tier("corporativo_pequeno", "T4") is True
    assert is_acceptable_for_tier("corporativo_pequeno", "T2") is False


def test_tier_acceptance_decisor_nominal() -> None:
    """decisor + nominal aceptados en todos los tiers."""
    for tier in ("T1", "T2", "T3", "T4"):
        assert is_acceptable_for_tier("decisor", tier) is True
        assert is_acceptable_for_tier("nominal", tier) is True


def test_tier_acceptance_descartado() -> None:
    """descartado nunca aceptado."""
    for tier in ("T1", "T2", "T3", "T4"):
        assert is_acceptable_for_tier("descartado", tier) is False


def test_tier_acceptance_invalid_tier_raises() -> None:
    with pytest.raises(ValueError, match="tier inválido"):
        is_acceptable_for_tier("decisor", "T5")
    with pytest.raises(ValueError):
        is_acceptable_for_tier("decisor", "")
    with pytest.raises(ValueError):
        is_acceptable_for_tier("decisor", "t1")  # case-sensitive


# ─── 7. Normalización (acentos, mayúsculas) ────────────────────────────────


def test_normalization_handles_accents() -> None:
    """Cargos con tildes se clasifican igual que sin tildes."""
    assert _classify("x@e.es", position="Comunicación").email_type == "descartado"
    assert _classify("x@e.es", position="Atención al Cliente").email_type == "descartado"
    assert _classify("x@e.es", position="Director Técnico").email_type == "decisor"
    assert _classify("x@e.es", position="Recepción").email_type == "descartado"


def test_normalization_handles_uppercase() -> None:
    """Mayúsculas no rompen clasificación."""
    assert _classify("x@e.es", position="GERENTE").email_type == "decisor"
    assert _classify("x@e.es", position="MARKETING").email_type == "descartado"
    assert _classify("x@e.es", position="Director General").email_type == "decisor"


def test_normalization_strips_whitespace() -> None:
    """Cargos con espacios extra al inicio/fin no rompen."""
    assert _classify("x@e.es", position="  Gerente  ").email_type == "decisor"


# ─── 8. Edge cases ─────────────────────────────────────────────────────────


def test_empty_position_with_name_falls_to_a3() -> None:
    """Position vacío + nombre → A3 (no decisor, no rol negativo, prefijo no whitelist)."""
    result = _classify(
        "juan.perez@e.es", position="", person_name="Juan Pérez", tier="T3"
    )
    assert result.email_type == "nominal"
    assert "A3" in result.reason


def test_none_position_with_name_falls_to_a3() -> None:
    """Position None tiene mismo efecto que vacío."""
    result = _classify(
        "juan.perez@e.es", position=None, person_name="Juan Pérez", tier="T1"
    )
    assert result.email_type == "nominal"


def test_whitespace_only_name_does_not_trigger_a3() -> None:
    """Nombre con solo espacios no cuenta como nombre conocido."""
    result = _classify(
        "xyz@e.es", position=None, person_name="   ", tier="T3"
    )
    assert result.email_type == "descartado"


def test_no_position_no_name_no_whitelist_yields_descartado() -> None:
    """Sin nada útil → descartado (regla 7)."""
    result = _classify("xyz@e.es")
    assert result.email_type == "descartado"


def test_email_without_at_uses_full_string_as_prefix() -> None:
    """Robustez: si el adapter manda algo raro sin `@`, no rompe."""
    result = _classify("infonotemail")
    assert result.email_type == "descartado"


def test_email_with_subdomain_extracts_prefix_correctly() -> None:
    result = _classify("info@sub.empresa.es", tier="T3")
    assert result.email_type == "corporativo_pequeno"


def test_uppercase_email_prefix_still_matches_whitelist() -> None:
    """`INFO@empresa.es` → corporativo_pequeno (prefix lowercased internamente)."""
    result = _classify("INFO@empresa.es", tier="T3")
    assert result.email_type == "corporativo_pequeno"


# ─── 9. Combos realistas ───────────────────────────────────────────────────


def test_realistic_decisor_with_personal_email() -> None:
    """Caso típico Hunter: nombre.apellido@ con cargo Director General."""
    result = _classify(
        "juan.perez@empresa.es",
        position="Director General",
        person_name="Juan Pérez",
        tier="T3",
    )
    assert result.email_type == "decisor"
    assert is_acceptable_for_tier(result.email_type, "T3") is True


def test_realistic_corporativo_t2_classified_but_rejected() -> None:
    """`info@` en T2: clasifica como corporativo pero la política tier lo rechaza."""
    cls = _classify("info@empresa.es", tier="T2")
    assert cls.email_type == "corporativo_pequeno"
    assert is_acceptable_for_tier(cls.email_type, "T2") is False


def test_realistic_marketing_director_combo() -> None:
    """Marketing Director con email personal: descartado por rol."""
    cls = _classify(
        "ana.lopez@empresa.es",
        position="Marketing Director",
        person_name="Ana López",
    )
    assert cls.email_type == "descartado"


def test_realistic_engineer_t2_accepted() -> None:
    """Engineer (cargo identificable no decisor) → nominal, aceptado en T2."""
    cls = _classify(
        "ana@empresa.es", position="Civil Engineer", person_name="Ana López", tier="T2"
    )
    assert cls.email_type == "nominal"
    assert is_acceptable_for_tier(cls.email_type, "T2") is True


# ─── 10. Inmutabilidad ─────────────────────────────────────────────────────


def test_classification_is_frozen() -> None:
    """Classification es inmutable (frozen dataclass)."""
    cls = _classify("info@e.es", tier="T3")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cls.email_type = "decisor"  # type: ignore[misc]


def test_whitelists_are_frozensets() -> None:
    """Las whitelists son inmutables — no pueden ser modificadas en runtime."""
    with pytest.raises(AttributeError):
        POSITIVE_PREFIXES.add("nuevo")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        NEGATIVE_PREFIXES.add("nuevo")  # type: ignore[attr-defined]
