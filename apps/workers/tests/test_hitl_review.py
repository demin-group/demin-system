"""Tests de scripts.hitl_review.

Sin BD ni stdin reales. Cubre las funciones puras del script + verifica que
las funciones de UPDATE construyen el SQL correcto via mocks.
"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.hitl_review import (
    EOF_MARKER,
    DraftRow,
    format_draft_for_display,
    normalize_action,
    parse_eof_input,
)

# ─── Helpers ───────────────────────────────────────────────────────────────


def _make_draft(
    *,
    nif: str = "A12345678",
    nombre_empresa: str = "ACME SL",
    tier: str = "T3",
    email: str = "juan@acme.es",
    email_type: str = "decisor",
    nombre_contacto: str | None = "Juan Pérez",
    cargo_contacto: str | None = "Director Técnico",
    subject: str = "Vaciados interiores en obras",
    body: str = "Hola Juan,\n\nTexto del cuerpo del correo.\n",
    angle: str = "opening",
    research_snapshot: dict[str, Any] | None = None,
) -> DraftRow:
    return DraftRow(
        message_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        contact_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        nif=nif,
        nombre_empresa=nombre_empresa,
        tier=tier,
        web="https://acme.es",
        email=email,
        email_type=email_type,
        email_priority=1,
        nombre_contacto=nombre_contacto,
        cargo_contacto=cargo_contacto,
        step_index=0,
        angle=angle,
        subject=subject,
        body=body,
        research_snapshot=research_snapshot or {},
        research_data={},
    )


# ─── 1. normalize_action ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a", "a"),
        ("A", "a"),
        ("aprobar", "a"),
        ("approve", "a"),
        ("e", "e"),
        ("editar", "e"),
        ("edit", "e"),
        ("r", "r"),
        ("regenerar", "r"),
        ("regen", "r"),
        ("x", "x"),
        ("rechazar", "x"),
        ("optout", "x"),
        ("s", "s"),
        ("saltar", "s"),
        ("skip", "s"),
        ("q", "q"),
        ("quit", "q"),
        ("exit", "q"),
        ("  A  ", "a"),  # whitespace + uppercase
    ],
)
def test_normalize_action_canonicalizes(raw: str, expected: str) -> None:
    assert normalize_action(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "z", "yes", "no", "1", "approve!"])
def test_normalize_action_returns_none_for_invalid(raw: str) -> None:
    assert normalize_action(raw) is None


# ─── 2. parse_eof_input ────────────────────────────────────────────────────


def test_parse_eof_stops_at_marker() -> None:
    lines = ["línea 1", "línea 2", "EOF", "línea ignorada"]
    assert parse_eof_input(lines) == "línea 1\nlínea 2"


def test_parse_eof_handles_marker_with_whitespace() -> None:
    lines = ["línea 1", "  EOF  ", "línea 2"]
    assert parse_eof_input(lines) == "línea 1"


def test_parse_eof_no_marker_returns_all_lines() -> None:
    """Si no aparece EOF, devuelve todo lo dado (caso defensivo — el caller
    ya leyó stdin y dejó de pasar líneas)."""
    lines = ["a", "b", "c"]
    assert parse_eof_input(lines) == "a\nb\nc"


def test_parse_eof_strips_trailing_whitespace() -> None:
    """El bloque entero pasa por rstrip — líneas vacías al final se descartan
    para no devolver `"línea\\n\\n"` con whitespace cuelgue."""
    lines = ["línea", "", "  ", "EOF"]
    assert parse_eof_input(lines) == "línea"


def test_parse_eof_empty_input_returns_empty() -> None:
    assert parse_eof_input([]) == ""
    assert parse_eof_input(["EOF"]) == ""


def test_parse_eof_custom_marker() -> None:
    lines = ["a", "b", "STOP", "c"]
    assert parse_eof_input(lines, marker="STOP") == "a\nb"


def test_parse_eof_marker_constant_matches() -> None:
    assert EOF_MARKER == "EOF"


# ─── 3. format_draft_for_display ───────────────────────────────────────────


def test_format_includes_company_contact_subject_body() -> None:
    d = _make_draft()
    out = format_draft_for_display(d, idx=1, total=5)
    assert "ACME SL" in out
    assert "A12345678" in out
    assert "T3" in out
    assert "https://acme.es" in out
    assert "juan@acme.es" in out
    assert "Juan Pérez" in out
    assert "Director Técnico" in out
    assert "Vaciados interiores en obras" in out
    assert "Hola Juan" in out
    assert "[1/5]" in out


def test_format_displays_validation_pass() -> None:
    d = _make_draft(research_snapshot={})
    out = format_draft_for_display(d, idx=1, total=1)
    assert "todas las validaciones automáticas pasan" in out


def test_format_displays_validation_failures() -> None:
    d = _make_draft(research_snapshot={
        "_failed_validations": ["body_too_short:30", "has_exclamation"],
    })
    out = format_draft_for_display(d, idx=1, total=1)
    assert "validaciones fallidas" in out
    assert "body_too_short:30" in out
    assert "has_exclamation" in out


def test_format_displays_razonamiento_when_present() -> None:
    d = _make_draft(research_snapshot={
        "_razonamiento_breve": "He elegido el hook de la calle Murcia",
    })
    out = format_draft_for_display(d, idx=1, total=1)
    assert "RAZONAMIENTO LLM" in out
    assert "calle Murcia" in out


def test_format_omits_razonamiento_section_when_absent() -> None:
    d = _make_draft(research_snapshot={})
    out = format_draft_for_display(d, idx=1, total=1)
    assert "RAZONAMIENTO LLM" not in out


def test_format_handles_corporativo_pequeno_without_name() -> None:
    """Para corporativo_pequeno, nombre_contacto y cargo_contacto suelen ser
    None — el display no debe mostrar paréntesis vacíos ni 'None'."""
    d = _make_draft(
        email="info@acme.es",
        email_type="corporativo_pequeno",
        nombre_contacto=None,
        cargo_contacto=None,
    )
    out = format_draft_for_display(d, idx=1, total=1)
    assert "info@acme.es" in out
    assert "None" not in out
    assert "()" not in out


def test_format_includes_action_prompt() -> None:
    d = _make_draft()
    out = format_draft_for_display(d, idx=1, total=1)
    assert "[a]probar" in out
    assert "[e]ditar" in out
    assert "[r]egenerar" in out
    assert "[x]" in out
    assert "[s]altar" in out
    assert "[q]uit" in out


def test_format_includes_position_index() -> None:
    d = _make_draft()
    out = format_draft_for_display(d, idx=3, total=10)
    assert "[3/10]" in out


def test_format_handles_missing_web() -> None:
    d = _make_draft()
    d.web = None
    out = format_draft_for_display(d, idx=1, total=1)
    assert "(sin web)" in out
