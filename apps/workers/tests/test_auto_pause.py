"""Tests de outreach.auto_pause.

Funciones puras (decide_pause_reason) + propiedades de MailboxStats.
Tests de SQL fetch + pause_mailbox requieren BD real -- smoke manual.
"""
from __future__ import annotations

import pytest

from outreach.auto_pause import (
    BOUNCE_RATE_THRESHOLD,
    MIN_SAMPLE_FOR_PAUSE,
    SPAM_RATE_THRESHOLD,
    MailboxStats,
    decide_pause_reason,
)


def _stats(*, sent: int, bounces: int = 0, spam: int = 0) -> MailboxStats:
    return MailboxStats(
        mailbox_id="00000000-0000-0000-0000-000000000000",
        mailbox_email="test@x.es",
        sent_7d=sent,
        bounces_7d=bounces,
        spam_7d=spam,
    )


# --- MailboxStats properties ---------------------------------------------


def test_bounce_rate_zero_when_no_sends() -> None:
    s = _stats(sent=0, bounces=0)
    assert s.bounce_rate == 0.0


def test_bounce_rate_division() -> None:
    s = _stats(sent=100, bounces=3)
    assert s.bounce_rate == 0.03


def test_spam_rate_division() -> None:
    s = _stats(sent=1000, bounces=0, spam=2)
    assert s.spam_rate == 0.002


# --- decide_pause_reason --------------------------------------------------


def test_no_pause_when_below_min_sample_even_if_high_bounce() -> None:
    """1 bounce sobre 10 envios = 10% pero sample <50 -> NO pausar."""
    s = _stats(sent=10, bounces=1)
    assert decide_pause_reason(s) is None


def test_no_pause_with_zero_sends() -> None:
    s = _stats(sent=0)
    assert decide_pause_reason(s) is None


def test_pause_when_bounce_exceeds_threshold_with_enough_sample() -> None:
    # 50 sends + 2 bounces = 4% > 2%
    s = _stats(sent=50, bounces=2)
    assert decide_pause_reason(s) == "auto_bounce_2pct"


def test_no_pause_when_bounce_exactly_at_threshold() -> None:
    # threshold es ESTRICTO >. 2% exacto NO debe pausar.
    # 50 sends * 0.02 = 1.0 bounces (justo en threshold)
    s = _stats(sent=50, bounces=1)
    assert decide_pause_reason(s) is None


def test_pause_when_spam_exceeds_threshold_with_enough_sample() -> None:
    # 1000 sends + 2 spam = 0.2% > 0.1%
    s = _stats(sent=1000, bounces=0, spam=2)
    assert decide_pause_reason(s) == "auto_spam_0.1pct"


def test_bounce_takes_precedence_over_spam_when_both_trigger() -> None:
    """Ambos disparan -> bounce_reason es lo que reportamos primero."""
    s = _stats(sent=100, bounces=5, spam=5)
    assert decide_pause_reason(s) == "auto_bounce_2pct"


@pytest.mark.parametrize(
    "sent,bounces,expected",
    [
        # Frontera MIN_SAMPLE
        (MIN_SAMPLE_FOR_PAUSE - 1, 100, None),  # bajo sample, no pausa
        (MIN_SAMPLE_FOR_PAUSE, 2, "auto_bounce_2pct"),  # justo en sample
    ],
)
def test_min_sample_frontera(
    sent: int, bounces: int, expected: str | None
) -> None:
    s = _stats(sent=sent, bounces=bounces)
    assert decide_pause_reason(s) == expected


# --- Constants ------------------------------------------------------------


def test_thresholds_match_plan_9_4() -> None:
    """§9.4: bounce >2%, spam >0.1%, ventana 7d. Cualquier cambio aqui
    obliga a revisar §9.4 del plan."""
    assert BOUNCE_RATE_THRESHOLD == 0.02
    assert SPAM_RATE_THRESHOLD == 0.001
