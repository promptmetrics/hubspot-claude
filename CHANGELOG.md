# Changelog

All notable changes to the HubSpot Agent plugin are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); the three version fields
(`pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`)
are kept in sync. Full release notes for each tag live at
[GitHub Releases](https://github.com/promptmetrics/hubspot-claude/releases).

## [Unreleased]

### Changed
- **Docs:** README status table corrected (CI evaluation gate is shipped and
  branch-protection-enforced) and the risk-tiered-approval boundary described
  precisely; added this changelog.
- **CI:** bumped `actions/checkout`, `setup-python`, and `setup-node` to their
  current majors to clear the Node 20 deprecation warning.

## [0.2.11] — 2026-07-22

### Added
- **Loop back-pressure (R13).** The durable loop retries transient read/preview
  errors (rate-limit, HubSpot 5xx, network/transport, retryable handler errors)
  up to 3 attempts with exponential backoff, honoring `Retry-After` (cap 60s),
  and paces before a step off `X-HubSpot-RateLimit-*` headers when remaining is
  low. Writes are never auto-retried — retry wraps read/preview only; a write
  still pauses at `awaiting_approval`. (PR #23)

## [0.2.10] — 2026-07-22

### Added
- **Loop cost governance via proxy budget (R12).** Plan-configurable
  `max_steps` / `max_api_calls` (plus surfaced `error_budget` /
  `verification_plateau`), enforced **per-step** in the durable loop so a
  runaway loop is stopped mid-run, not only at verify checkpoints. (PR #22)

### Removed
- The inert `HUBSPOT_LOOP_COST` / `$0.50` cost ceiling (a dead env-var knob
  nothing ever set).

## [0.2.9] — 2026-07-22

### Fixed
- **Partial-capture auto-apply.** An update that captured fewer original values
  than the records it targets is only partially undoable; it now downgrades from
  AUTO to CONFIRM, keeping a human checkpoint. (PR #21)

## [0.2.8] — 2026-07-22

### Added
- **Risk-tiered approval — Bounded Autonomy (R11).** Interactive writes are
  classified AUTO / CONFIRM / FULL_GATE: provably-safe, reversible, in-ceiling,
  non-sensitive writes auto-apply with an undo command; destructive,
  over-ceiling, non-reversible, sensitive-field, and side-effectful workflow
  writes keep the human gate. Config in `approval_policy.json` (shipped default +
  global + per-portal, union-merged safety lists). (PR #20)

### Note
- The **CI evaluation gate** (`pytest` + `claude plugin validate` + artifact
  allowlist, required on every PR via branch protection — R10) landed just
  before this release without its own version bump.

## [0.2.7] — 2026-07-17

### Added
- Quiet/terse output mode with a hardened HITL carve-out — step narration is
  suppressed, but previews, approvals, and count gates are never suppressed. (R9)

## [0.2.6] — 2026-07-16

### Changed
- Full-coverage deterministic keyword routing across all specialist agents, plus
  a bounded 429 read-retry in the HTTP client. (R1)

## [0.2.5] — 2026-07-15

### Fixed
- Truthful, fail-closed undo — non-undoable operations (delete/merge, or an
  update that captured no originals) surface at preview time instead of
  promising a rollback that can't happen.

## [0.2.4] — 2026-07-15

### Fixed
- Bulk-write silent no-op and undo-replay fixes (filter to writable properties;
  fail-closed on swallowed envelopes).

## [0.2.3] — 2026-07-14

### Fixed
- Demo-rehearsal hardening: duplicate-finder pagination, bulk count gate, bulk
  undo, and loop verbatim-tool-path fixes.

## [0.2.1] — 2026-07-14 · [0.2.0] — 2026-07-11

### Added
- Workflow blueprint learning loop (extract → parameterize → promote → create),
  with HITL-bypass and per-portal fixes in 0.2.1. (R6)

---

Earlier 0.1.x history (initial plugin, OAuth/region support, daemon tool
registry) is in the git tags and GitHub Releases.
