# ADR 0002: Hash chain with SHA-256, not signatures

## Status

Accepted, v0.1.

## Context

The audit log needs to be tamper-evident: a regulator or internal auditor must be able to confirm that events have not been silently rewritten after the fact. The options:

1. **Sign each event with an HSM-backed key.** Cryptographically strong, expensive to operate, and requires every site to have an HSM.
2. **Hash-chain the events.** Each row carries `previous_hash` and `hash`. A reviewer recomputes the chain in O(n) and detects any inserted, deleted, or modified row.
3. **Write to a "blockchain".** Real cost, unclear regulator acceptance, fashion-cycle risk.
4. **Trust the DBA.** Operationally common, regulatorily indefensible.

## Decision

Hash-chain with SHA-256 (option 2). The `hash` column is computed as `sha256(previous_hash ‖ canonical-json(row_body))`. The first row in a run uses 32 bytes of `0x00` as the previous hash.

## Trade-offs

- **No cryptographic non-repudiation against an insider with database write access who can also rewrite the application code.** A determined attacker can rewrite the entire chain from a chosen point. We accept this because the threat model is "honest operator, hostile administrator" or "honest operator, regulator-side audit", not "insider attacker with code-deploy access". Sites that need stronger guarantees should layer signing or external anchoring on top.
- **Canonical JSON is a footgun.** Hash invariance requires byte-identical serialisation. We use `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)`. Sites that customise serialisation will break verification. Documented in `harness/audit.py`.
- **SHA-256 over BLAKE3.** BLAKE3 is faster, but SHA-256 is universally available in regulator tooling, libraries, and command-line utilities. The latency cost is irrelevant at audit-log write rates.

## Consequences

- Audit-log verification is one linear scan; no signing infrastructure required.
- Sites can ship `verify_chain(run_id)` as an operator-facing CLI without HSM-key plumbing.
- We commit to JSON canonicalisation as a stable contract. Any future change to the canonicalisation function is a breaking change.
