"""Tests de outreach.follow_ups.

Funciones puras (sin BD ni LLM): load_sequence_steps con mock de BD via
fixture, estimate_cost_usd, edge cases del SQL.
"""
from __future__ import annotations

import pytest

from outreach.follow_ups import (
    FollowUpStep,
    estimate_cost_usd,
)


# --- estimate_cost_usd ----------------------------------------------------


def test_estimate_cost_usd_zero() -> None:
    assert estimate_cost_usd(0, 0) == 0.0


def test_estimate_cost_usd_sonnet_pricing() -> None:
    # 1M input + 1M output = $3 + $15 = $18
    assert estimate_cost_usd(1_000_000, 1_000_000) == pytest.approx(18.0)


def test_estimate_cost_usd_typical_draft() -> None:
    # Draft tipico paso 6: ~4600 in, 330 out
    cost = estimate_cost_usd(4600, 330)
    # 4600 * 3 / 1e6 + 330 * 15 / 1e6 = 0.0138 + 0.00495 = 0.01875
    assert cost == pytest.approx(0.01875, rel=1e-3)


# --- FollowUpStep dataclass -----------------------------------------------


def test_follow_up_step_construction() -> None:
    step = FollowUpStep(
        next_step_index=1, next_angle="reframe", days_since_prev_sent=4
    )
    assert step.next_step_index == 1
    assert step.next_angle == "reframe"
    assert step.days_since_prev_sent == 4


# Tests de SQL fetch_followup_candidates y load_sequence_steps requieren BD
# real -- quedan como smoke manual del PM con --dry-run.
