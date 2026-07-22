# Governance

## Model

The HubSpot Agent plugin is maintained by **PromptMetrics** under a benevolent-maintainer model.
Izzy Aly is the current maintainer and final decision-maker.

## How decisions are made

- **Product scope and requirements** are tracked in `docs/PRD.md` as numbered requirements (R1–R13),
  with a §6 Status table and an append-only §4 Decisions log.
- **Architectural decisions** are recorded as ADRs under `docs/adr/` (e.g. ADR-0003, deterministic
  routing as a security property).
- Every non-trivial decision gets a dated line in the PRD Decisions log with a one-line rationale.

## Proposing changes

Open an issue to discuss scope, or a pull request for concrete changes. Substantial changes — new
subsystems, changes to the write-safety contract, or new OAuth scopes — should reference or add a
PRD requirement, and, where architectural, an ADR.

## Releases

Versions are bumped in lockstep across `pyproject.toml`, `.claude-plugin/plugin.json`, and
`.claude-plugin/marketplace.json`, tagged `vX.Y.Z`, and published as GitHub releases. Only the
latest release receives fixes.
