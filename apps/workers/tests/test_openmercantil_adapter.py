"""Tests de shared.openmercantil_adapter — funciones puras (sin red).

Cubre: parseo de nombre español (orden registral APELLIDOS NOMBRE → first/last
natural), ranking de cargo, exclusión de personas jurídicas y selección del
mejor decisor de una lista `current` de OpenMercantil.
"""
from __future__ import annotations

import pytest

from shared.openmercantil_adapter import (
    Officer,
    is_juridical_person,
    parse_spanish_name,
    pick_best_officer,
    rank_role,
)


# ─── parse_spanish_name ────────────────────────────────────────────────────
@pytest.mark.parametrize("registry,first,last,full", [
    ("FERNANDEZ MENCIA RICARDO", "Ricardo", "Fernandez", "Ricardo Fernandez Mencia"),
    ("CRESPO JIMENEZ JUAN JOSE", "Juan", "Crespo", "Juan Jose Crespo Jimenez"),
    ("BAREA NAVARRO ANTONIO", "Antonio", "Barea", "Antonio Barea Navarro"),
    ("ARBOLEDA MONTOYA LEIDY JHOANNA", "Leidy", "Arboleda", "Leidy Jhoanna Arboleda Montoya"),
    ("GARCIA JUAN", "Juan", "Garcia", "Juan Garcia"),
])
def test_parse_spanish_name_typical(registry, first, last, full):
    f, l, fn = parse_spanish_name(registry)
    assert f == first
    assert l == last
    assert fn == full


def test_parse_spanish_name_particle_surname():
    """Partículas se adhieren al apellido siguiente."""
    f, l, fn = parse_spanish_name("DE LA FUENTE GARCIA ANA")
    assert f == "Ana"
    assert l == "De La Fuente"
    assert fn == "Ana De La Fuente Garcia"


def test_parse_spanish_name_single_token():
    f, l, fn = parse_spanish_name("MADONNA")
    assert f == "Madonna"
    assert l == ""
    assert fn == "Madonna"


def test_parse_spanish_name_empty():
    assert parse_spanish_name("") == ("", "", "")
    assert parse_spanish_name("   ") == ("", "", "")


# ─── rank_role ─────────────────────────────────────────────────────────────
def test_rank_role_orders_decisor_above_apoderado():
    assert rank_role("Administrador Unico") > rank_role("Apoderado")
    assert rank_role("Administrador Solidario") > rank_role("Consejero")
    assert rank_role("Consejero Delegado") > rank_role("Apoderado")


def test_rank_role_excludes_auditor():
    assert rank_role("Auditor") == -1
    assert rank_role("Auditor de Cuentas") == -1


def test_rank_role_unknown_role_is_present_but_low():
    """Cargo presente pero no catalogado → 10 (sigue siendo persona de contacto)."""
    assert rank_role("Vocal") == 10
    assert rank_role("") == 10
    assert rank_role(None) == 10


def test_rank_role_accent_and_case_insensitive():
    assert rank_role("administrador único") == rank_role("ADMINISTRADOR UNICO")


# ─── is_juridical_person ───────────────────────────────────────────────────
@pytest.mark.parametrize("name", [
    "ACP AUDITORES CONSULTORES SL",
    "GESTORIA EJEMPLO S.L.",
    "HOLDING X SA",
    "CONSULTORA Y SLU",
])
def test_is_juridical_person_true(name):
    assert is_juridical_person(name) is True


@pytest.mark.parametrize("name", [
    "FERNANDEZ MENCIA RICARDO",
    "BAREA NAVARRO ANTONIO",
    "ANA MAROTO TELLO",
])
def test_is_juridical_person_false(name):
    assert is_juridical_person(name) is False


# ─── pick_best_officer ─────────────────────────────────────────────────────
def test_pick_best_officer_prefers_administrador_over_apoderado():
    current = [
        {"name": "BAREA NAVARRO ANTONIO", "role": "Apoderado"},
        {"name": "FERNANDEZ MENCIA RICARDO", "role": "Administrador Unico"},
    ]
    best = pick_best_officer(current)
    assert isinstance(best, Officer)
    assert best.name_registry == "FERNANDEZ MENCIA RICARDO"
    assert best.role == "Administrador Unico"
    assert best.first_name == "Ricardo"


def test_pick_best_officer_skips_juridical_and_auditor():
    current = [
        {"name": "ACP AUDITORES CONSULTORES SL", "role": "Auditor"},
        {"name": "CRESPO JIMENEZ JUAN JOSE", "role": "Apoderado"},
    ]
    best = pick_best_officer(current)
    assert best is not None
    assert best.name_registry == "CRESPO JIMENEZ JUAN JOSE"


def test_pick_best_officer_none_when_only_juridical():
    current = [
        {"name": "ACP AUDITORES CONSULTORES SL", "role": "Auditor"},
        {"name": "OTRA SOCIEDAD SL", "role": "Administrador Unico"},
    ]
    assert pick_best_officer(current) is None


def test_pick_best_officer_empty_list():
    assert pick_best_officer([]) is None
    assert pick_best_officer(None) is None
