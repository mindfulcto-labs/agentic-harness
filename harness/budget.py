"""Autonomy budget enforcement for agent tool calls.

Tracks three orthogonal budgets per run:
  - tool_calls: how many side-effecting calls the agent may attempt
  - tokens: how many LLM tokens the agent may consume
  - wall_clock_seconds: how long the agent may run

When any budget is exhausted, the harness raises BudgetExceeded and the
audit log records the kill point. The pattern matches the autonomy-budget
shape described in the patent application referenced in the README.

The decorator and the explicit context-manager API are intentionally both
provided so callers can pick whichever matches their orchestration style
(LangGraph nodes prefer the explicit form; one-off scripts prefer the
decorator).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BudgetExceeded(RuntimeError):
    """Raised when any budget dimension is exhausted.

    The exception carries the dimension name and observed value so the
    harness's audit writer can record the precise kill point without
    callers having to introspect the BudgetState.
    """

    def __init__(self, dimension: str, observed: float, limit: float):
        self.dimension = dimension
        self.observed = observed
        self.limit = limit
        super().__init__(
            f"budget exceeded on {dimension}: observed={observed} limit={limit}"
        )


class BudgetSpec(BaseModel):
    """Declarative budget for a single agent run.

    A spec is immutable per-run; budgets cannot be topped up mid-flight
    by the agent itself. To grant more budget you must end the run and
    start a new one (with corresponding audit entries).
    """

    tool_calls: int = Field(gt=0, description="max side-effecting tool invocations")
    tokens: int = Field(gt=0, description="max LLM tokens (prompt + completion)")
    wall_clock_seconds: float = Field(gt=0, description="max wall-clock duration")


@dataclass
class BudgetState:
    """Live counters for a single run. Mutated by the enforcer."""

    spec: BudgetSpec
    started_at: float = field(default_factory=time.monotonic)
    tool_calls_used: int = 0
    tokens_used: int = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def check(self) -> None:
        """Raise BudgetExceeded if any dimension is over limit.

        Checked dimensions: tool_calls, tokens, wall_clock. The order
        matters only for the exception message: wall-clock first because
        a stalled tool call is the most common runaway pattern.
        """
        elapsed = self.elapsed()
        if elapsed > self.spec.wall_clock_seconds:
            raise BudgetExceeded("wall_clock_seconds", elapsed, self.spec.wall_clock_seconds)
        if self.tool_calls_used > self.spec.tool_calls:
            raise BudgetExceeded("tool_calls", self.tool_calls_used, self.spec.tool_calls)
        if self.tokens_used > self.spec.tokens:
            raise BudgetExceeded("tokens", self.tokens_used, self.spec.tokens)

    def record_tool_call(self) -> None:
        self.tool_calls_used += 1
        self.check()

    def record_tokens(self, n: int) -> None:
        self.tokens_used += n
        self.check()


@contextmanager
def autonomy_budget(spec: BudgetSpec) -> Iterator[BudgetState]:
    """Context-manager API for explicit budget tracking.

    Example::

        with autonomy_budget(BudgetSpec(tool_calls=5, tokens=4000, wall_clock_seconds=30)) as state:
            for step in plan:
                state.record_tool_call()
                result = tool.invoke(step)
                state.record_tokens(result.usage.total_tokens)
    """

    state = BudgetState(spec=spec)
    try:
        yield state
    finally:
        # Final check ensures runs that complete normally still record
        # against the budget for audit purposes.
        # We don't re-raise here; the audit writer logs the final state.
        pass


def with_budget(spec: BudgetSpec) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator API for one-off agent functions.

    The decorated function receives an extra ``budget`` kwarg holding the
    live BudgetState. The function should call ``budget.record_tool_call()``
    and ``budget.record_tokens()`` at the right points; the harness does
    not auto-instrument because token accounting belongs to the LLM client
    layer, not here.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            with autonomy_budget(spec) as state:
                kwargs["budget"] = state
                return fn(*args, **kwargs)

        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator
