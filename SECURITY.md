# Security Policy

## Reporting a vulnerability

If you find a security issue in this repository, please email **security@themindfulcto.com** with:

- A description of the issue
- Steps to reproduce
- Affected version (commit SHA is fine)

Please **do not** open a public issue for a vulnerability. We'll acknowledge within 72 hours and aim to triage within five working days.

## Scope

This is a v0.1-alpha library. Threats in scope:

- Audit-chain integrity bypass (constructing valid chains that misrepresent history)
- Budget enforcer bypass (causing the harness to skip a budget check)
- Blast-radius policy bypass (causing the harness to invoke a tool against policy)
- Hash canonicalisation issues that break verification

Out of scope:

- Vulnerabilities in upstream dependencies (report directly to Pydantic / etc.)
- Vulnerabilities in user-supplied tool code or policy functions
- Issues that require an attacker with code-deploy access to the host (see [ADR 0002](docs/adr/0002-sha256-hash-chain.md))

## Disclosure

Once a fix is shipped, the original reporter is credited in the release notes unless they prefer anonymity. We aim for a public disclosure window of 30 days.
