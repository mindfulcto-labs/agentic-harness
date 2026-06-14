"""Hash-chain audit log tests."""

from harness import AuditLogger, InMemoryAuditWriter, verify_chain
from harness.audit import GENESIS_HASH


def test_chain_starts_at_genesis():
    writer = InMemoryAuditWriter()
    log = AuditLogger(run_id="r1", writer=writer)
    ev = log.emit("run.start", {"agent": "procurement_triage"})
    assert ev.previous_hash == GENESIS_HASH


def test_chain_links_events():
    writer = InMemoryAuditWriter()
    log = AuditLogger(run_id="r1", writer=writer)
    e1 = log.emit("a", {"i": 1})
    e2 = log.emit("b", {"i": 2})
    e3 = log.emit("c", {"i": 3})
    assert e2.previous_hash == e1.hash
    assert e3.previous_hash == e2.hash
    assert verify_chain([e1, e2, e3]) is True


def test_tampered_payload_detected():
    writer = InMemoryAuditWriter()
    log = AuditLogger(run_id="r1", writer=writer)
    e1 = log.emit("a", {"i": 1})
    e2 = log.emit("b", {"i": 2})
    # An attacker rewrites e1's payload after the fact.
    e1_tampered = e1.model_copy(update={"payload": {"i": 999}})
    assert verify_chain([e1_tampered, e2]) is False


def test_reordered_events_detected():
    writer = InMemoryAuditWriter()
    log = AuditLogger(run_id="r1", writer=writer)
    e1 = log.emit("a", {"i": 1})
    e2 = log.emit("b", {"i": 2})
    e3 = log.emit("c", {"i": 3})
    # Reordering breaks the chain.
    assert verify_chain([e1, e3, e2]) is False


def test_sequences_are_per_run():
    writer = InMemoryAuditWriter()
    log_a = AuditLogger(run_id="A", writer=writer)
    log_b = AuditLogger(run_id="B", writer=writer)
    a1 = log_a.emit("x", {})
    b1 = log_b.emit("x", {})
    a2 = log_a.emit("y", {})
    assert a1.sequence == 0
    assert b1.sequence == 0
    assert a2.sequence == 1
    assert a1.run_id == "A"
    assert b1.run_id == "B"
