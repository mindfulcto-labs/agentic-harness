# ADR 0001: Three blast-radius tiers, not five

## Status

Accepted, v0.1.

## Context

The harness needs a way to classify tools so the policy gate can decide whether a given call requires approval. The question is how granular the classification should be.

Existing patterns considered:

- **Microsoft AI Agent Governance Toolkit** uses a five-tier model (read / write-safe / write-with-rollback / write-irreversible / external-side-effect). Designed for the platform team operating the agents.
- **Most academic papers** on agent safety classify tools as "safe" vs "unsafe" — two tiers. Designed for research, not deployment.
- **The patent application** I filed at Maersk uses three tiers (read, reversible, irreversible). Designed for an operating team that needs to hold the tier in their head during a 2am incident.

## Decision

We use three tiers: `READ_ONLY`, `WRITE_REVERSIBLE`, `WRITE_IRREVERSIBLE`.

## Trade-offs

- **Coarser than Microsoft's model.** We lose the distinction between "write-with-rollback" and "write-irreversible-external-side-effect". The pragmatic answer is: rollback that requires coordination with another team is operationally indistinguishable from irreversible during the actual incident, so we collapse them.
- **Finer than two-tier.** Two-tier collapses cache-invalidation and dispatching-funds into the same bucket, which forces every meaningful policy to be a side-channel allowlist. We lose readability.
- **Three matches operator memory.** Practitioner interviews (informal, n≈12) consistently produced the same three categories without prompting. People who tried to add a fourth could not remember it the next day.

## Consequences

- Sites who want the fourth tier can subclass `ToolDescriptor` and write a custom policy function. The harness does not block this; it just does not encourage it.
- We do not attempt to map our tiers onto Microsoft's. Sites that need both can keep two registries side by side.
