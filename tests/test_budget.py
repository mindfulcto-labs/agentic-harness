"""Budget enforcement tests."""

import time

import pytest

from harness import BudgetExceeded, BudgetSpec, autonomy_budget, with_budget


def test_tool_calls_kill():
    spec = BudgetSpec(tool_calls=3, tokens=10_000, wall_clock_seconds=10)
    with autonomy_budget(spec) as state:
        state.record_tool_call()
        state.record_tool_call()
        state.record_tool_call()
        with pytest.raises(BudgetExceeded) as exc:
            state.record_tool_call()
        assert exc.value.dimension == "tool_calls"


def test_tokens_kill():
    spec = BudgetSpec(tool_calls=10, tokens=100, wall_clock_seconds=10)
    with autonomy_budget(spec) as state:
        state.record_tokens(50)
        state.record_tokens(50)
        with pytest.raises(BudgetExceeded) as exc:
            state.record_tokens(1)
        assert exc.value.dimension == "tokens"


def test_wall_clock_kill():
    spec = BudgetSpec(tool_calls=10, tokens=10_000, wall_clock_seconds=0.05)
    with autonomy_budget(spec) as state:
        time.sleep(0.10)
        with pytest.raises(BudgetExceeded) as exc:
            state.record_tool_call()
        assert exc.value.dimension == "wall_clock_seconds"


def test_decorator_carries_budget():
    spec = BudgetSpec(tool_calls=2, tokens=100, wall_clock_seconds=5)

    @with_budget(spec)
    def agent(budget=None):
        budget.record_tool_call()
        budget.record_tool_call()
        return "ok"

    assert agent() == "ok"


def test_decorator_propagates_exceeded():
    spec = BudgetSpec(tool_calls=1, tokens=100, wall_clock_seconds=5)

    @with_budget(spec)
    def runaway(budget=None):
        budget.record_tool_call()
        budget.record_tool_call()

    with pytest.raises(BudgetExceeded):
        runaway()
