"""Tests de replies.handle_actions.

Cobertura:
- parse_ooo_return_date: parser puro de fechas OOO en espanol/dd-mm-yyyy.
- Constantes L46: re_engage_40 angle (no re_engage_60).

handle_one + BD interactions requieren mocks de SQLAlchemy session; quedan
como smoke manual del PM con --dry-run cuando haya replies reales.
"""
from __future__ import annotations

from datetime import date

import pytest

from replies.handle_actions import (
    OOO_DAYS_AFTER_RETURN,
    OOO_DEFAULT_DAYS,
    RE_ENGAGE_40_DAYS,
    RE_ENGAGE_90_DAYS,
    parse_ooo_return_date,
)


# --- L46 guards (constantes) -----------------------------------------------


def test_re_engage_40_constant_is_40() -> None:
    """L46: no_ahora pasa de +60d a +40d."""
    assert RE_ENGAGE_40_DAYS == 40


def test_re_engage_90_constant_unchanged() -> None:
    """L46: no_interesado se mantiene en +90d."""
    assert RE_ENGAGE_90_DAYS == 90


def test_re_engage_60_constant_removed() -> None:
    """L46: la constante antigua RE_ENGAGE_60_DAYS NO debe existir."""
    from replies import handle_actions

    assert not hasattr(handle_actions, "RE_ENGAGE_60_DAYS"), (
        "Constante RE_ENGAGE_60_DAYS removida en L46. Usa RE_ENGAGE_40_DAYS."
    )


def test_ooo_defaults_sensible() -> None:
    """OOO defaults: +5d desde fecha de retorno, default +7d sin parse."""
    assert OOO_DAYS_AFTER_RETURN == 5
    assert OOO_DEFAULT_DAYS == 7


# --- parse_ooo_return_date -------------------------------------------------

TODAY = date(2026, 5, 26)


def test_parse_ooo_returns_none_for_empty_body() -> None:
    assert parse_ooo_return_date(None, today=TODAY) is None
    assert parse_ooo_return_date("", today=TODAY) is None


def test_parse_ooo_returns_none_when_no_date_in_text() -> None:
    body = "Hola, estoy fuera de la oficina. Saludos."
    assert parse_ooo_return_date(body, today=TODAY) is None


def test_parse_ooo_ddmmyyyy_slash() -> None:
    body = "Estoy de vacaciones. Vuelvo el 15/06/2026. Saludos."
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 6, 15)


def test_parse_ooo_ddmmyyyy_dash() -> None:
    body = "Regreso 30-05-2026, gracias."
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 5, 30)


def test_parse_ooo_ddmm_without_year_assumes_this_year() -> None:
    """Si fecha no lleva ano y todavia no ha pasado este ano, asume hoy.year."""
    body = "Hasta el 15/06"
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 6, 15)


def test_parse_ooo_ddmm_without_year_past_drops_due_to_horizon() -> None:
    """Si fecha sin ano cae en pasado de hoy.year, asume next year -> queda
    a >120d del horizon -> descartado (no es OOO realista)."""
    body = "Vuelvo el 15/01"  # asumiria 2027-01-15, a ~234d -> None
    assert parse_ooo_return_date(body, today=TODAY) is None


def test_parse_ooo_dragging_into_horizon() -> None:
    """Fecha de hoy.year pero a >120d se descarta (out of horizon)."""
    body = "Vuelvo el 30/12/2026"
    assert parse_ooo_return_date(body, today=TODAY) is None


def test_parse_ooo_includes_at_120d() -> None:
    """Fecha cerca del limite 120d sigue dentro."""
    # TODAY = 2026-05-26. +120d = 2026-09-23. "23 de septiembre" debe estar IN.
    body = "Vuelvo el 23 de septiembre"
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 9, 23)


def test_parse_ooo_es_dia_de_mes() -> None:
    body = "Estare de vuelta el 5 de junio de 2026. Un saludo."
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 6, 5)


def test_parse_ooo_es_setiembre_variant() -> None:
    """'setiembre' (variante reconocida) ademas de 'septiembre'."""
    body = "Vuelvo el 1 de setiembre."
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 9, 1)


def test_parse_ooo_picks_latest_in_range() -> None:
    """'del 1 al 15 de junio' -> usa el 15 (cuando vuelve)."""
    body = "Estare fuera del 1 al 15 de junio de 2026"
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 6, 15)


def test_parse_ooo_ignores_dates_too_far_future() -> None:
    """Fechas a >90d se descartan (probablemente no son OOO real)."""
    body = "Vuelvo el 31 de diciembre de 2026."
    assert parse_ooo_return_date(body, today=TODAY) is None


def test_parse_ooo_ignores_invalid_calendar_dates() -> None:
    body = "Vuelvo el 31/02/2026"
    assert parse_ooo_return_date(body, today=TODAY) is None


def test_parse_ooo_case_insensitive() -> None:
    body = "Estare de vuelta el 15 DE JUNIO de 2026"
    assert parse_ooo_return_date(body, today=TODAY) == date(2026, 6, 15)


# --- Bonus: angle/dryrun string contiene re_engage_40 ----------------------


def test_dryrun_label_no_ahora_says_re_engage_40() -> None:
    """L46 guard: el label dry-run para no_ahora menciona re_engage_40."""
    from replies.handle_actions import handle_one

    reply = {
        "reply_id": "00000000-0000-0000-0000-000000000001",
        "message_id": "00000000-0000-0000-0000-000000000002",
        "contact_id": "00000000-0000-0000-0000-000000000003",
        "category": "no_ahora",
        "is_explicit_optout": False,
        "raw_body": "no es momento, gracias",
        "campaign_id": None,
        "mailbox_id": None,
    }
    label = handle_one("dev", reply, dry_run=True)  # type: ignore[arg-type]
    assert "re_engage_40" in label
    assert "re_engage_60" not in label


def test_dryrun_label_interesado_no_genera_draft() -> None:
    """L45 guard: interesado dry-run NO menciona generacion de draft."""
    from replies.handle_actions import handle_one

    reply = {
        "reply_id": "00000000-0000-0000-0000-000000000001",
        "message_id": "00000000-0000-0000-0000-000000000002",
        "contact_id": "00000000-0000-0000-0000-000000000003",
        "category": "interesado",
        "is_explicit_optout": False,
        "raw_body": "Me interesa",
        "campaign_id": None,
        "mailbox_id": None,
    }
    label = handle_one("dev", reply, dry_run=True)  # type: ignore[arg-type]
    # NO debe contener "draft" ni "respuesta" ni "suggested" -- L45.
    assert "draft" not in label.lower()
    assert "respuesta" not in label.lower()
    # SI debe mencionar leave pending / flag / event.
    assert any(k in label.lower() for k in ("pending", "flag", "event"))
