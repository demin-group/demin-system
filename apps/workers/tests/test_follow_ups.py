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


# --- SQL strings: guard contra regresion 2026-05-25 -----------------------


def test_followup_sql_excludes_cancelled_from_next_step_check() -> None:
    """Sesion 2026-05-25: el filtro NOT EXISTS de m_next debe excluir
    status='cancelled' para permitir que drafts cancelados (porque la
    cadencia o el prompt cambiaron) se regeneren en la siguiente corrida del
    follow_ups cron. Sin este filtro, cancelar bloquea regeneracion futura
    igual que un envio exitoso, lo cual rompe el flujo "cancelar viejo +
    esperar regen con nueva cadencia D+14".
    """
    import inspect

    from outreach import follow_ups

    src = inspect.getsource(follow_ups.fetch_followup_candidates)
    # El SQL debe incluir el guard de cancelled.
    assert "m_next.status <> 'cancelled'" in src, (
        "fetch_followup_candidates debe excluir status='cancelled' del NOT "
        "EXISTS check de m_next; ver sesion 2026-05-25 / Bloque 5.2."
    )
