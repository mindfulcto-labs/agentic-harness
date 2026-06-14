# agentic-harness

[![CI](https://github.com/mindfulcto-labs/agentic-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/mindfulcto-labs/agentic-harness/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

> Production-shape agent harness. Autonomy budgets. Blast-radius controls. Regulator-legible audit trails.

A small Python library that wraps any agent (LangGraph, CrewAI, AutoGen, plain function calls) with three primitives:

1. **Autonomy budget** — the agent gets a fixed budget of tool calls, tokens, and wall-clock seconds. When the budget runs out, the harness kills the run and records the kill point.
2. **Blast radius** — every tool the agent can call is classified `READ_ONLY`, `WRITE_REVERSIBLE`, or `WRITE_IRREVERSIBLE`. The harness gates each call through a policy. The default policy refuses `WRITE_IRREVERSIBLE` unless the tool descriptor explicitly opts into two-person approval.
3. **Hash-chained audit trail** — every event the harness emits is appended to a SHA-256 chain. A regulator (or your own auditor) can verify the chain end-to-end without trusting the database administrator.

The shape is the one I described in a patent application I filed during my time at A.P. Moller-Maersk on agentic AI for regulated workflows. This repo is a clean-room, public-domain reference implementation in a non-customs domain (the worked example is procurement triage). No employer IP, no client data, no proprietary architecture.

## Why this exists

In April 2026 Anthropic took down 8,100 GitHub repositories citing IP infringement. In March 2026 Microsoft shipped the AI Agent Governance Toolkit. The category — "production-grade agent governance primitives, open-source, opinionated, focused-domain" — has shifted from optional to expected. This is my answer.

The opinions:

- **Budgets are orthogonal, not unified.** A single "max steps" counter conflates three failure modes. Three budgets catch three different runaway shapes.
- **Blast radius has exactly three tiers.** Practitioners can hold three tiers in their head; five tiers turn the policy into an exercise. The patent application uses the same three.
- **The audit log is append-only and hash-chained.** Not because every site needs cryptographic non-repudiation, but because the alternative — trusting your DBA, your backups, and your own code to never silently rewrite history — is the one a regulator will not accept.

## Quickstart

```bash
pip install agentic-harness
```

```python
from harness import BudgetSpec, autonomy_budget, BlastRadiusEnforcer, BlastTier, ToolDescriptor, AuditLogger, InMemoryAuditWriter

# Declare tools and their blast-radius tier.
enforcer = BlastRadiusEnforcer()
enforcer.register(ToolDescriptor(name="erp.read_supplier", tier=BlastTier.READ_ONLY, description="lookup supplier"))
enforcer.register(ToolDescriptor(name="erp.create_po", tier=BlastTier.WRITE_IRREVERSIBLE, description="create purchase order", requires_two_person_approval=True))

# Each run gets its own audit logger and budget.
writer = InMemoryAuditWriter()  # swap for PostgresAuditWriter in production
log = AuditLogger(run_id="run-001", writer=writer)
budget = BudgetSpec(tool_calls=8, tokens=20_000, wall_clock_seconds=30)

with autonomy_budget(budget) as state:
    log.emit("run.start", {"agent": "procurement_triage", "budget": budget.model_dump()})

    decision = enforcer.evaluate("erp.read_supplier", {"id": 42})
    if decision.allow:
        state.record_tool_call()
        state.record_tokens(120)
        log.emit("tool.invoke", {"tool": "erp.read_supplier", "input": {"id": 42}})

    log.emit("run.end", {"status": "ok"})

# Verify the chain end-to-end.
from harness import verify_chain
assert verify_chain(writer.events("run-001"))
```

Worked example: [`examples/procurement_triage/`](examples/procurement_triage/) wires the three primitives into a small LangGraph agent that triages purchase requests under budget and policy.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                  agent                                   │
│  (LangGraph node, CrewAI task, plain function — anything that calls a    │
│   tool and consumes tokens)                                              │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                ┌───────────────────┴───────────────────┐
                │           harness boundary            │
                └───────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌──────────────────┐         ┌─────────────────┐
│ BudgetState   │         │ BlastRadius      │         │ AuditLogger     │
│ tool_calls    │         │ Enforcer         │         │ run_id          │
│ tokens        │         │ tool → tier      │         │ sequence        │
│ wall_clock    │         │ tier → decision  │         │ hash chain      │
└───────────────┘         └──────────────────┘         └─────────────────┘
        │                           │                           │
        ▼                           ▼                           ▼
   BudgetExceeded            PolicyDecision               AuditEvent (JSONB)
   (kill the run)            (allow / deny / approve)     (Postgres or memory)
```

## Audit log format

Each row is one event. The `hash` column references the previous row's hash, so verifying integrity is one linear scan.

| Column          | Type       | Notes                                                         |
|-----------------|------------|---------------------------------------------------------------|
| `run_id`        | text       | Groups events for one agent invocation                        |
| `sequence`      | int        | 0, 1, 2 … within `run_id`                                     |
| `timestamp`     | timestamptz| UTC, set by the harness                                       |
| `event_type`    | text       | `run.start`, `tool.invoke`, `policy.deny`, `budget.exceeded`, `run.end`  |
| `payload`       | jsonb      | Free-form, canonicalised before hashing                       |
| `previous_hash` | text       | Hex SHA-256 of the previous row's hash                        |
| `hash`          | text       | Hex SHA-256 of (previous_hash ‖ canonical-json(this row body)) |

The first row in a run sets `previous_hash = "0" * 64` (genesis). Verification walks the chain forward and recomputes each hash.

This format aligns with EU AI Act Article 12 (automatic event logging for high-risk systems). The cross-walk to ISO/IEC 42001 Annex A.7 lives in the companion [`compliance-as-code`](https://github.com/mindfulcto-labs/compliance-as-code) repo.

## Limitations

- **No model training, no orchestration of >5 concurrent agents, no built-in human-in-the-loop UI.** The harness is a wrapper, not a platform. If you want a platform, look at [Microsoft AI Agent Governance Toolkit](https://github.com/microsoft/aigovernance-toolkit) or LangChain Vaara — both ship more surface area, less opinion.
- **Postgres adapter ships in v0.2.** v0.1 has the in-memory writer (for quickstart and tests) and the abstract `AuditWriter` interface so sites can plug their own.
- **OPA integration ships in v0.2.** v0.1 has the policy function abstraction and the reference default policy.

## Roadmap

- **v0.2** — Postgres audit writer, OPA policy gate, two-person approval workflow for `WRITE_IRREVERSIBLE`, audit-chain verification CLI.
- **v0.3** — CrewAI and AutoGen adapters. Streamlit replay UI for past runs.
- **v0.4** — Drift detection on budget configurations. Per-tool eval harness for harness overhead (latency, token cost).

## IP statement

This is a public reference implementation of patterns inspired by production AI systems. It does not reference, replicate, or derive from any employer's internal architecture, source code, or proprietary designs. All data is synthetic or drawn from public sources.

## Companion reading

The design choices are explained in three essays at [themindfulcto.com](https://themindfulcto.com):

- _Autonomy budgets: three orthogonal kill switches that catch three different runaway shapes._
- _Blast radius: why three tiers, not five, and what to do when the agent calls a write-irreversible tool._
- _Hash-chained audit logs for EU AI Act Article 12: the cheapest tamper-evident pattern._

## License

[Apache License 2.0](LICENSE).
