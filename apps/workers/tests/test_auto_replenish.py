"""Tests de pipeline.auto_replenish.

El worker es un orquestador de research_prospect + find_contacts + generate_draft.
Los workers de bajo nivel ya tienen tests; aquí cubrimos:
- CLI parsing + dispatching.
- Logica de gap calculation (cuando cola >= target -> exit 0).
- Logica de huerfanos primero, luego pipeline completo.
- Manejo de exit codes downstream.

Sin red real: cada submodulo se mockea via monkeypatch.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from pipeline import auto_replenish


def test_count_drafts_in_queue_returns_int(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pruebo el contract: get_engine + execute devuelve int >= 0."""
    class FakeRow:
        def __init__(self, n: int) -> None: self._n = n
        def __getitem__(self, i: int) -> int: return self._n

    class FakeResult:
        def fetchone(self) -> FakeRow: return FakeRow(7)

    class FakeConn:
        def __enter__(self) -> "FakeConn": return self
        def __exit__(self, *a: Any) -> None: pass
        def execute(self, *a: Any, **k: Any) -> FakeResult: return FakeResult()

    class FakeEngine:
        def connect(self) -> FakeConn: return FakeConn()

    monkeypatch.setattr(auto_replenish, "get_engine", lambda env: FakeEngine())
    assert auto_replenish.count_drafts_in_queue("dev") == 7


def test_run_replenish_no_op_when_queue_already_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si drafts >= target, no llama a ningun worker downstream."""
    monkeypatch.setattr(auto_replenish, "count_drafts_in_queue", lambda env: 20)
    spy_count_huerfanos = []
    spy_research_pending = []
    spy_research = []
    spy_find = []
    spy_gen = []
    monkeypatch.setattr(
        auto_replenish, "count_contacts_without_draft",
        lambda env, tier: (spy_count_huerfanos.append((env, tier)) or 5),
    )
    monkeypatch.setattr(
        auto_replenish, "count_research_pending",
        lambda env, tier: (spy_research_pending.append((env, tier)) or 100),
    )
    monkeypatch.setattr(
        auto_replenish.research_prospect, "main",
        lambda argv: (spy_research.append(argv) or 0),
    )
    monkeypatch.setattr(
        auto_replenish.find_contacts, "main",
        lambda argv: (spy_find.append(argv) or 0),
    )
    monkeypatch.setattr(
        auto_replenish.generate_draft, "main",
        lambda argv: (spy_gen.append(argv) or 0),
    )

    rc = auto_replenish.run_replenish(
        env="dev", target=15, batch_size=10,
        max_cost_usd=0.5, max_hunter_calls=10, tier="T3",
    )

    assert rc == 0
    assert spy_count_huerfanos == [], "no debe consultar huerfanos si cola llena"
    assert spy_research == []
    assert spy_find == []
    assert spy_gen == []


def test_run_replenish_huerfanos_first_then_skip_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si hay huerfanos suficientes para llenar la cola, no toca pipeline."""
    state = {"drafts": 10}

    def fake_count_drafts(env: str) -> int:
        return state["drafts"]

    monkeypatch.setattr(auto_replenish, "count_drafts_in_queue", fake_count_drafts)
    monkeypatch.setattr(
        auto_replenish, "count_contacts_without_draft",
        lambda env, tier: 5,
    )

    research_called = []
    find_called = []
    gen_called = []

    def fake_gen(argv: list[str]) -> int:
        state["drafts"] = 15
        gen_called.append(argv)
        return 0

    monkeypatch.setattr(
        auto_replenish.research_prospect, "main",
        lambda argv: (research_called.append(argv) or 0),
    )
    monkeypatch.setattr(
        auto_replenish.find_contacts, "main",
        lambda argv: (find_called.append(argv) or 0),
    )
    monkeypatch.setattr(auto_replenish.generate_draft, "main", fake_gen)

    rc = auto_replenish.run_replenish(
        env="prod", target=15, batch_size=10,
        max_cost_usd=0.5, max_hunter_calls=10, tier="T3",
    )

    assert rc == 0
    assert len(gen_called) == 1
    assert research_called == [], "huerfanos no deberian tirar research"
    assert find_called == []
    args = gen_called[0]
    assert args[:2] == ["--env", "prod"]
    assert "--tier" in args and args[args.index("--tier") + 1] == "T3"
    assert "--angle" in args and args[args.index("--angle") + 1] == "opening"


def test_run_replenish_warns_when_no_research_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si no hay huerfanos ni research_pending, exit 3 con warning."""
    monkeypatch.setattr(auto_replenish, "count_drafts_in_queue", lambda env: 0)
    monkeypatch.setattr(
        auto_replenish, "count_contacts_without_draft",
        lambda env, tier: 0,
    )
    monkeypatch.setattr(
        auto_replenish, "count_research_pending",
        lambda env, tier: 0,
    )
    research_called = []
    monkeypatch.setattr(
        auto_replenish.research_prospect, "main",
        lambda argv: (research_called.append(argv) or 0),
    )

    rc = auto_replenish.run_replenish(
        env="dev", target=15, batch_size=10,
        max_cost_usd=0.5, max_hunter_calls=10, tier="T3",
    )

    assert rc == 3
    assert research_called == [], "no debe llamar research si pending=0"


def test_run_replenish_full_pipeline_when_huerfanos_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cuando huerfanos=0 y research_pending>0, ejecuta research+find+generate."""
    state = {"drafts": 5}

    def fake_count(env: str) -> int:
        return state["drafts"]

    monkeypatch.setattr(auto_replenish, "count_drafts_in_queue", fake_count)
    monkeypatch.setattr(
        auto_replenish, "count_contacts_without_draft",
        lambda env, tier: 0,
    )
    monkeypatch.setattr(
        auto_replenish, "count_research_pending",
        lambda env, tier: 50,
    )

    calls: dict[str, list[list[str]]] = {"research": [], "find": [], "gen": []}

    def fake_research(argv: list[str]) -> int:
        calls["research"].append(argv)
        return 0

    def fake_find(argv: list[str]) -> int:
        calls["find"].append(argv)
        return 0

    def fake_gen(argv: list[str]) -> int:
        calls["gen"].append(argv)
        state["drafts"] = 15
        return 0

    monkeypatch.setattr(auto_replenish.research_prospect, "main", fake_research)
    monkeypatch.setattr(auto_replenish.find_contacts, "main", fake_find)
    monkeypatch.setattr(auto_replenish.generate_draft, "main", fake_gen)

    rc = auto_replenish.run_replenish(
        env="prod", target=15, batch_size=10,
        max_cost_usd=0.5, max_hunter_calls=10, tier="T3",
    )

    assert rc == 0
    assert len(calls["research"]) == 1
    assert len(calls["find"]) == 1
    assert len(calls["gen"]) == 1
    # limit = min(batch_size, research_pending) = min(10, 50) = 10
    assert "--limit" in calls["research"][0]
    idx = calls["research"][0].index("--limit")
    assert calls["research"][0][idx + 1] == "10"
    # find: --max-hunter-calls debe llevarse
    assert "--max-hunter-calls" in calls["find"][0]
    # generate: limit = target - drafts pre = 15 - 5 = 10
    idx_g = calls["gen"][0].index("--limit")
    assert calls["gen"][0][idx_g + 1] == "10"


def test_main_cli_defaults() -> None:
    """CLI parsing: defaults razonables."""
    with patch.object(auto_replenish, "run_replenish", return_value=0) as mock:
        rc = auto_replenish.main(["--env", "dev"])
    assert rc == 0
    kw = mock.call_args.kwargs
    assert kw["env"] == "dev"
    assert kw["target"] == auto_replenish.DEFAULT_TARGET
    assert kw["batch_size"] == auto_replenish.DEFAULT_BATCH_SIZE
    assert kw["max_cost_usd"] == auto_replenish.DEFAULT_MAX_COST_USD
    assert kw["max_hunter_calls"] == auto_replenish.DEFAULT_MAX_HUNTER_CALLS
    assert kw["tier"] == "T3"


def test_main_cli_overrides() -> None:
    """CLI parsing: override de todos los flags."""
    with patch.object(auto_replenish, "run_replenish", return_value=0) as mock:
        rc = auto_replenish.main([
            "--env", "prod", "--target", "20", "--batch-size", "5",
            "--max-cost-usd", "1.5", "--max-hunter-calls", "30",
            "--tier", "T2",
        ])
    assert rc == 0
    kw = mock.call_args.kwargs
    assert kw["env"] == "prod"
    assert kw["target"] == 20
    assert kw["batch_size"] == 5
    assert kw["max_cost_usd"] == 1.5
    assert kw["max_hunter_calls"] == 30
    assert kw["tier"] == "T2"
