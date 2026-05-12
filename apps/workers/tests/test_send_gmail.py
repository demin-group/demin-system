"""Tests de outreach.send_gmail.

Funciones puras (sin BD ni red) en la suite default. El flow E2E completo
(BD dev real + GmailAdapter MockTransport) queda como smoke manual del
PM con `--dry-run` antes del bloqueador B5.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from outreach.send_gmail import (
    _FOOTER,
    build_full_body,
    classify_error_as_bounce,
    is_business_hours,
)

MADRID = ZoneInfo("Europe/Madrid")


def _madrid_dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=MADRID).astimezone(timezone.utc)


# --- 1. is_business_hours --------------------------------------------------


@pytest.mark.parametrize(
    "weekday_label,h,m,expected",
    [
        # 2026-05-11 es lunes (laborable)
        ("lun", 9, 0, True),
        ("lun", 9, 30, True),
        ("lun", 12, 59, True),
        ("lun", 13, 0, False),    # 13:00 ya fuera (estricto < end)
        ("lun", 14, 30, False),   # pausa comida
        ("lun", 15, 0, True),
        ("lun", 17, 59, True),
        ("lun", 18, 0, False),
        ("lun", 8, 59, False),
        ("lun", 0, 1, False),
        ("lun", 23, 59, False),
    ],
)
def test_is_business_hours_weekday_window(
    weekday_label: str, h: int, m: int, expected: bool
) -> None:
    dt = _madrid_dt(2026, 5, 11, h, m)
    assert is_business_hours(dt) is expected


@pytest.mark.parametrize(
    "year,month,day,label",
    [
        (2026, 5, 9, "sab"),   # sabado
        (2026, 5, 10, "dom"),  # domingo
    ],
)
def test_is_business_hours_blocks_weekends(
    year: int, month: int, day: int, label: str
) -> None:
    """Cualquier hora en sabado o domingo -> False."""
    for h in (10, 12, 16, 18):
        dt = _madrid_dt(year, month, day, h)
        assert is_business_hours(dt) is False, f"{label} {h}:00 deberia ser False"


def test_is_business_hours_uses_madrid_tz_not_utc() -> None:
    """A las 7:00 UTC en verano (DST), Madrid esta a 9:00 -- dentro de
    ventana. El test verifica que la conversion de TZ funciona."""
    # 2026-07-13 lunes, 7:00 UTC = 9:00 Madrid (CEST UTC+2)
    dt_utc = datetime(2026, 7, 13, 7, 0, tzinfo=timezone.utc)
    assert is_business_hours(dt_utc) is True


# --- 2. build_full_body ----------------------------------------------------


def test_build_full_body_appends_footer() -> None:
    out = build_full_body("Hola, soy Gonzalo.")
    assert out.startswith("Hola, soy Gonzalo.")
    assert _FOOTER in out


def test_build_full_body_strips_trailing_whitespace_before_footer() -> None:
    out = build_full_body("Hola.\n\n\n   ")
    # rstrip aplicado al body
    assert out.startswith("Hola.")
    assert "Hola.\n\n\n   " not in out
    assert _FOOTER in out


def test_footer_contains_optout_text_from_plan() -> None:
    """§9.3 fija el texto del opt-out. Verifica que esta literal en el footer."""
    assert "responde STOP" in _FOOTER
    assert "dejaremos de escribirte" in _FOOTER


def test_footer_contains_sender_identity() -> None:
    assert "Gonzalo Perez" in _FOOTER
    assert "DEMIN Group" in _FOOTER
    assert "demingroupmadrid.com" in _FOOTER


def test_footer_separator_is_rfc_3676() -> None:
    """Separador estandar de firma '-- \\n' (RFC 3676). Clientes de email
    lo usan para detectar y plegar/colapsar firma."""
    assert "\n-- \n" in _FOOTER


# --- 3. classify_error_as_bounce -------------------------------------------


@pytest.mark.parametrize(
    "err,expected",
    [
        ("Invalid To header: notreal@example", True),
        ("Recipient address rejected: No such user", True),
        ("Domain not found: xn--invalid.es", True),
        ("address does not exist", True),
        ("USER UNKNOWN in virtual mailbox table", True),
        ("Daily user sending quota exceeded.", False),
        ("Mail service unavailable, please retry", False),
        ("Authentication credentials are invalid", False),
        ("", False),
        (None, False),
    ],
)
def test_classify_error_as_bounce(err: str | None, expected: bool) -> None:
    assert classify_error_as_bounce(err) is expected
