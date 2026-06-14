"""End-to-end test for the procurement triage example."""

from harness import verify_chain
from harness.audit import AuditEvent

from examples.procurement_triage import agent


def test_demo_run_produces_valid_chain():
    result = agent.run_demo()
    events = [AuditEvent.model_validate(e) for e in result["events"]]
    assert verify_chain(events)


def test_demo_routing_classification():
    result = agent.run_demo()
    assert result["routing"]["tier"] == "single_manager"  # 1250 GBP


def test_classify_tier_boundaries():
    assert agent._classify_tier(499.99) == "auto_approve"
    assert agent._classify_tier(500.0) == "single_manager"
    assert agent._classify_tier(4_999.99) == "single_manager"
    assert agent._classify_tier(5_000.0) == "two_person_finance"
