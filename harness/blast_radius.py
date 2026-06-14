"""Blast-radius classification for tool calls.

Every tool the agent has access to is classified into one of three tiers:

  READ_ONLY              read state without modifying the outside world.
  WRITE_REVERSIBLE       modify state, but the change can be undone without
                         coordination beyond a single system boundary.
  WRITE_IRREVERSIBLE     modify state in a way that cannot be undone by the
                         agent alone (sends external email, dispatches funds,
                         deletes data, calls third-party APIs that bill,
                         changes records other systems already replicated).

The harness enforces a policy decision before any WRITE_IRREVERSIBLE call
runs. Default policy: require two-person approval via the human-in-the-loop
interface. Sites can override with explicit allowlists in the policy bundle.

Why three tiers and not five: research and incident-report patterns show
practitioners reliably distinguish "nothing happens", "I can undo this",
and "I cannot undo this". Finer granularity makes the policy harder to
reason about without changing the outcome.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel


class BlastTier(str, Enum):
    READ_ONLY = "read_only"
    WRITE_REVERSIBLE = "write_reversible"
    WRITE_IRREVERSIBLE = "write_irreversible"


class ToolDescriptor(BaseModel):
    """Static metadata about a single tool the agent may call.

    The descriptor is the source of truth for blast-radius classification.
    Tools register their descriptor at startup; the harness refuses to
    invoke a tool that lacks one.
    """

    name: str
    tier: BlastTier
    description: str
    requires_two_person_approval: bool = False
    dry_run_supported: bool = False


class PolicyDecision(BaseModel):
    """Result of a policy gate evaluation."""

    allow: bool
    reason: str
    requires_approval: bool = False


# A policy callable takes the descriptor and the call's input and returns
# a decision. Sites plug their own callables here; the default below is
# the conservative reference implementation.
PolicyFn = Callable[[ToolDescriptor, dict], PolicyDecision]


def default_policy(descriptor: ToolDescriptor, call_input: dict) -> PolicyDecision:
    """Reference policy. Sites should replace, not extend.

    Rules:
      - READ_ONLY: always allow.
      - WRITE_REVERSIBLE: allow, log to audit.
      - WRITE_IRREVERSIBLE: require approval unless the descriptor opts out
        explicitly (e.g. for batch jobs running under a service identity
        with their own out-of-band controls).
    """

    if descriptor.tier == BlastTier.READ_ONLY:
        return PolicyDecision(allow=True, reason="read_only_tier")

    if descriptor.tier == BlastTier.WRITE_REVERSIBLE:
        return PolicyDecision(allow=True, reason="write_reversible_tier")

    # WRITE_IRREVERSIBLE
    if descriptor.requires_two_person_approval:
        return PolicyDecision(
            allow=True,
            reason="write_irreversible_with_two_person_approval",
            requires_approval=True,
        )
    return PolicyDecision(
        allow=False,
        reason="write_irreversible_without_approval_disallowed_by_default",
    )


class BlastRadiusEnforcer:
    """Gate that wraps tool invocations and applies the policy."""

    def __init__(self, policy: Optional[PolicyFn] = None):
        self._policy = policy or default_policy
        self._registry: dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor) -> None:
        """Register a tool. Duplicate names raise; renaming is intentional friction."""
        if descriptor.name in self._registry:
            raise ValueError(f"tool already registered: {descriptor.name}")
        self._registry[descriptor.name] = descriptor

    def descriptor(self, name: str) -> ToolDescriptor:
        if name not in self._registry:
            raise KeyError(f"tool not registered: {name}")
        return self._registry[name]

    def evaluate(self, name: str, call_input: dict) -> PolicyDecision:
        descriptor = self.descriptor(name)
        return self._policy(descriptor, call_input)
