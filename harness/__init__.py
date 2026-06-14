"""agentic-harness — autonomy budgets, blast-radius controls, audit trails.

Public API surface. Sites import from ``harness``, not from the submodules
directly, so submodule reshuffles don't break callers.
"""

from harness.audit import (
    AuditEvent,
    AuditLogger,
    AuditWriter,
    GENESIS_HASH,
    InMemoryAuditWriter,
    verify_chain,
)
from harness.blast_radius import (
    BlastRadiusEnforcer,
    BlastTier,
    PolicyDecision,
    ToolDescriptor,
    default_policy,
)
from harness.budget import (
    BudgetExceeded,
    BudgetSpec,
    BudgetState,
    autonomy_budget,
    with_budget,
)

__all__ = [
    # audit
    "AuditEvent",
    "AuditLogger",
    "AuditWriter",
    "GENESIS_HASH",
    "InMemoryAuditWriter",
    "verify_chain",
    # blast radius
    "BlastRadiusEnforcer",
    "BlastTier",
    "PolicyDecision",
    "ToolDescriptor",
    "default_policy",
    # budget
    "BudgetExceeded",
    "BudgetSpec",
    "BudgetState",
    "autonomy_budget",
    "with_budget",
]
