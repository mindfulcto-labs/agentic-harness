"""Blast-radius classifier tests."""

import pytest

from harness import BlastRadiusEnforcer, BlastTier, ToolDescriptor


def _enforcer_with(*descriptors):
    e = BlastRadiusEnforcer()
    for d in descriptors:
        e.register(d)
    return e


def test_read_only_always_allowed():
    e = _enforcer_with(
        ToolDescriptor(name="ledger.read", tier=BlastTier.READ_ONLY, description="read")
    )
    d = e.evaluate("ledger.read", {})
    assert d.allow is True
    assert d.requires_approval is False


def test_write_reversible_allowed_with_audit():
    e = _enforcer_with(
        ToolDescriptor(
            name="cache.set", tier=BlastTier.WRITE_REVERSIBLE, description="reversible"
        )
    )
    d = e.evaluate("cache.set", {})
    assert d.allow is True
    assert d.requires_approval is False


def test_write_irreversible_default_denied():
    e = _enforcer_with(
        ToolDescriptor(
            name="payments.send",
            tier=BlastTier.WRITE_IRREVERSIBLE,
            description="dispatches funds",
        )
    )
    d = e.evaluate("payments.send", {"amount": 100})
    assert d.allow is False


def test_write_irreversible_allowed_with_two_person_approval():
    e = _enforcer_with(
        ToolDescriptor(
            name="payments.send",
            tier=BlastTier.WRITE_IRREVERSIBLE,
            description="dispatches funds",
            requires_two_person_approval=True,
        )
    )
    d = e.evaluate("payments.send", {"amount": 100})
    assert d.allow is True
    assert d.requires_approval is True


def test_unregistered_tool_raises():
    e = BlastRadiusEnforcer()
    with pytest.raises(KeyError):
        e.evaluate("ghost.tool", {})


def test_duplicate_registration_raises():
    e = BlastRadiusEnforcer()
    d = ToolDescriptor(name="x", tier=BlastTier.READ_ONLY, description="x")
    e.register(d)
    with pytest.raises(ValueError):
        e.register(d)
