"""Procurement triage agent — worked example for the harness.

A purchase request comes in. The agent:

  1. Reads the requesting employee's record (READ_ONLY).
  2. Looks up the supplier (READ_ONLY).
  3. Picks a tier: under £500 routes to auto-approve, £500-£5000 routes
     to single-manager approval, anything else routes to two-person
     finance approval.
  4. Creates the routing record (WRITE_REVERSIBLE — sites can cancel a
     routing before any PO is cut).

The agent never calls ``erp.create_po`` directly. That tool is registered
as WRITE_IRREVERSIBLE and the default policy refuses it without two-person
approval, so the agent has to escalate.

All of this is fake. The "ERP" is a Python dict. The point of the example
is to show the three primitives in concert, not to ship procurement.
"""

from __future__ import annotations

from typing import Any

from harness import (
    AuditLogger,
    BlastRadiusEnforcer,
    BlastTier,
    BudgetExceeded,
    BudgetSpec,
    BudgetState,
    InMemoryAuditWriter,
    ToolDescriptor,
    autonomy_budget,
)

# --------------------------------------------------------------------------- #
#  Fake ERP backend                                                           #
# --------------------------------------------------------------------------- #

_EMPLOYEES = {
    101: {"name": "A. Khan", "cost_centre": "ENG-PLT"},
    102: {"name": "B. Patel", "cost_centre": "ENG-PLT"},
}
_SUPPLIERS = {
    501: {"name": "Acme Cables Ltd", "preferred": True, "frame_agreement": True},
    502: {"name": "Generic Bolts Inc", "preferred": False, "frame_agreement": False},
}
_ROUTINGS: list[dict[str, Any]] = []


def erp_read_employee(employee_id: int) -> dict[str, Any]:
    return _EMPLOYEES[employee_id]


def erp_read_supplier(supplier_id: int) -> dict[str, Any]:
    return _SUPPLIERS[supplier_id]


def erp_create_routing(request: dict[str, Any], tier: str) -> dict[str, Any]:
    record = {"request": request, "tier": tier, "id": len(_ROUTINGS) + 1}
    _ROUTINGS.append(record)
    return record


# --------------------------------------------------------------------------- #
#  Tool registry                                                              #
# --------------------------------------------------------------------------- #


def build_enforcer() -> BlastRadiusEnforcer:
    e = BlastRadiusEnforcer()
    e.register(
        ToolDescriptor(
            name="erp.read_employee",
            tier=BlastTier.READ_ONLY,
            description="Lookup employee record by id.",
        )
    )
    e.register(
        ToolDescriptor(
            name="erp.read_supplier",
            tier=BlastTier.READ_ONLY,
            description="Lookup supplier record by id.",
        )
    )
    e.register(
        ToolDescriptor(
            name="erp.create_routing",
            tier=BlastTier.WRITE_REVERSIBLE,
            description="Create a routing decision. Routings can be cancelled before a PO is cut.",
        )
    )
    e.register(
        ToolDescriptor(
            name="erp.create_po",
            tier=BlastTier.WRITE_IRREVERSIBLE,
            description="Create a purchase order. Cannot be undone once the supplier is notified.",
            requires_two_person_approval=True,
        )
    )
    return e


# --------------------------------------------------------------------------- #
#  The agent itself                                                           #
# --------------------------------------------------------------------------- #


def _classify_tier(amount_gbp: float) -> str:
    if amount_gbp < 500:
        return "auto_approve"
    if amount_gbp < 5_000:
        return "single_manager"
    return "two_person_finance"


def triage(
    request: dict[str, Any],
    *,
    enforcer: BlastRadiusEnforcer,
    log: AuditLogger,
    budget: BudgetState,
) -> dict[str, Any]:
    """Triage one purchase request.

    Returns the routing record. Raises BudgetExceeded if any budget is
    exhausted; raises PermissionError if the policy refuses a tool call.
    """

    log.emit(
        "agent.input",
        {"request_id": request.get("id"), "amount_gbp": request.get("amount_gbp")},
    )

    # Step 1: read employee
    decision = enforcer.evaluate("erp.read_employee", {"id": request["employee_id"]})
    if not decision.allow:
        log.emit("policy.deny", {"tool": "erp.read_employee", "reason": decision.reason})
        raise PermissionError(decision.reason)
    budget.record_tool_call()
    employee = erp_read_employee(request["employee_id"])
    log.emit("tool.invoke", {"tool": "erp.read_employee", "result": employee})
    budget.record_tokens(80)  # accounted as if it were an LLM-mediated lookup

    # Step 2: read supplier
    decision = enforcer.evaluate("erp.read_supplier", {"id": request["supplier_id"]})
    if not decision.allow:
        log.emit("policy.deny", {"tool": "erp.read_supplier", "reason": decision.reason})
        raise PermissionError(decision.reason)
    budget.record_tool_call()
    supplier = erp_read_supplier(request["supplier_id"])
    log.emit("tool.invoke", {"tool": "erp.read_supplier", "result": supplier})
    budget.record_tokens(80)

    # Step 3: classify tier
    tier = _classify_tier(request["amount_gbp"])
    log.emit("agent.decision", {"tier": tier})
    budget.record_tokens(60)

    # Step 4: create routing
    decision = enforcer.evaluate("erp.create_routing", {"tier": tier})
    if not decision.allow:
        log.emit("policy.deny", {"tool": "erp.create_routing", "reason": decision.reason})
        raise PermissionError(decision.reason)
    budget.record_tool_call()
    routing = erp_create_routing(request, tier)
    log.emit("tool.invoke", {"tool": "erp.create_routing", "result": routing})
    budget.record_tokens(80)

    log.emit("agent.output", {"routing_id": routing["id"], "tier": tier})
    return routing


def run_demo() -> dict[str, Any]:
    """End-to-end demo. Returns the routing and the audit events."""

    enforcer = build_enforcer()
    writer = InMemoryAuditWriter()
    log = AuditLogger(run_id="demo-001", writer=writer)
    budget_spec = BudgetSpec(tool_calls=10, tokens=2_000, wall_clock_seconds=5)

    request = {
        "id": "REQ-2026-001",
        "employee_id": 101,
        "supplier_id": 501,
        "amount_gbp": 1_250.0,
    }

    with autonomy_budget(budget_spec) as state:
        log.emit("run.start", {"agent": "procurement_triage", "budget": budget_spec.model_dump()})
        try:
            routing = triage(request, enforcer=enforcer, log=log, budget=state)
            log.emit("run.end", {"status": "ok", "routing_id": routing["id"]})
        except BudgetExceeded as e:
            log.emit("budget.exceeded", {"dimension": e.dimension, "observed": e.observed, "limit": e.limit})
            log.emit("run.end", {"status": "budget_exceeded"})
            raise

    return {
        "routing": routing,
        "events": [e.model_dump() for e in writer.events("demo-001")],
    }


if __name__ == "__main__":
    import json

    result = run_demo()
    print(json.dumps(result, indent=2, default=str))
