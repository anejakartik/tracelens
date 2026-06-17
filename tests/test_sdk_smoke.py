"""Smoke tests — fail-soft decorator, token extraction, cost calc."""

from __future__ import annotations

from dataclasses import dataclass

import tracelens
from tracelens.pricing import PRICING, compute_cost


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class _Msg:
    content: str


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Response:
    choices: list[_Choice]
    usage: _Usage
    model: str


def test_traced_decorator_returns_result_when_collector_down() -> None:
    """Decorator must be fail-soft: no collector → function still returns."""
    tracelens.configure(endpoint="http://localhost:1")  # bogus port

    @tracelens.traced(model="gpt-4o-mini")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_traced_extracts_openai_token_usage() -> None:
    tracelens.configure(endpoint="http://localhost:1")

    @tracelens.traced(model="gpt-4o-mini")
    def fake_call() -> _Response:
        return _Response(
            choices=[_Choice(message=_Msg(content="hi"))],
            usage=_Usage(prompt_tokens=12, completion_tokens=8, total_tokens=20),
            model="gpt-4o-mini",
        )

    out = fake_call()
    assert out.usage.total_tokens == 20


def test_compute_cost_known_model() -> None:
    # gpt-4o-mini: $0.15/M input, $0.60/M output.
    cost = compute_cost("gpt-4o-mini", 1000, 1000)
    assert cost is not None
    assert cost > 0
    # 1000 input @ 0.15 + 1000 output @ 0.60 = 0.00015 + 0.0006 = 0.00075
    assert abs(cost - 0.00075) < 1e-9


def test_compute_cost_unknown_model_returns_none() -> None:
    assert compute_cost("imaginary-model-2099", 1000, 1000) is None


def test_compute_cost_strips_provider_prefix() -> None:
    assert compute_cost("openai/gpt-4o-mini", 1000, 1000) == compute_cost("gpt-4o-mini", 1000, 1000)


def test_pricing_table_non_empty() -> None:
    assert len(PRICING) > 5
    assert "gpt-4o-mini" in PRICING


def test_traced_records_error_without_raising_observability_side() -> None:
    tracelens.configure(endpoint="http://localhost:1")

    @tracelens.traced(model="gpt-4o-mini")
    def boom() -> int:
        raise ValueError("nope")

    import pytest

    with pytest.raises(ValueError):
        boom()
