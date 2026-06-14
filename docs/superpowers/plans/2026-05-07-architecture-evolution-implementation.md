# HubSpot Agent — Architecture Evolution Implementation Plan

> **Date:** 2026-05-07
> **Source PRD:** `docs/superpowers/research/2026-05-07-architecture-evolution.md`
> **Scope:** 42 tasks across Phase A (Foundation), Phase B (Intelligence/UX), Phase C (Domain Expansion)
> **Execution strategy:** Phase-gated — Phase A first, then B, then C

---

## Overview

This plan implements the architecture evolution described in the research PRD. It is dependency-ordered and designed for sequential execution with quality gates per task.

**Disk schema (final state after all phases):**

```
~/.claude/hubspot/
  <portal_id>.json                  # PortalConfig (auth, tier, scopes)
  <portal_id>/
    schema_cache.json               # Phase 0 — object/property schemas
    audit.log                       # Phase 0 — approved writes
    action_log.jsonl                # Phase A — idempotency ledger
    capabilities.json               # Phase A — feature matrix
    traces.jsonl                    # Phase B — observability
    query_cache.json                # Phase B — short-lived read cache
    sessions/                       # Phase C — conversation summaries
      <session_id>.json
    in_flight/                      # Phase A — bulk checkpoints
      <action_id>.jsonl
    completed/                      # Phase A — archived checkpoints
      <action_id>.jsonl
    undo_snapshots/                 # Phase 0 — rollback data
      <action_id>.json
    roles.json                      # Phase C — RBAC (optional)
    routing_overrides.json          # Phase C — per-portal vocab (optional)
~/.claude/hubspot/plugins/          # Phase C — custom tool extensions
  *.py
```

---

## Phase A — Foundation Hardening

> **Goal:** Eliminate silent partial-state failures, cache staleness surprises, and first-run friction. Transform the agent from "demo" to "robust."
> **Estimated effort:** 2–3 weeks
> **Key principle:** All Phase A modules are additive. They can be disabled by omitting orchestrator hooks.

| # | Task | Effort | Files | Dependencies | Acceptance Criteria |
|---|------|--------|-------|-------------|-------------------|
| 1 | **Error category taxonomy** | tiny | `errors.py`, `client.py` | — | Every `HubSpotError` carries an `ErrorCategory` enum mapped from HTTP status and response body shape. |
| 2 | **Portal capability matrix probe** | small | `capabilities.py`, `orchestrator.py` | — | First portal connection probes tier, custom objects, workflow API, user management, and calculated properties; results cached in `capabilities.json`. |
| 3 | **Snapshot pruning + TTL** | small | `maintenance.py`, `orchestrator.py` | — | Undo snapshots older than 30 days and completed in-flight files older than 7 days are auto-pruned; `traces.jsonl` rotates at 100 MB. |
| 4 | **Background pre-fetch (cache warming)** | small | `cache.py`, `orchestrator.py` | — | Portal switch triggers async warming of standard-object schemas; subsequent requests hit warm cache. |
| 5 | **Guided setup wizard** | medium | `setup.py`, `cli.py` | — | `/hubspot setup` walks through OAuth or Private App token, probes capabilities, warms schema cache, and reports scope gaps. |
| 6 | **Capability detection report** | small | `capabilities.py` | 2 | Post-setup readout lists portal tier, enabled features, cached schema counts, and missing OAuth scopes. |
| 7 | **Action ledger for idempotency** | small | `ledger.py`, `orchestrator.py` | — | Every write appends `started` and `completed` entries to `action_log.jsonl`; re-dispatch checks ledger and surfaces in-flight actions instead of duplicating. |
| 8 | **Mid-execution checkpointing (bulk ops)** | small | `checkpoint.py`, `tools/objects.py`, `orchestrator.py` | 7 | Bulk ops write per-chunk status to `in_flight/<action_id>.jsonl`; resumption offers to continue from last completed chunk with exact per-record error tracking. |
| 9 | **Schema-aware pre-validation** | medium | `validation.py`, `cache.py`, `tools/*.py` | 1, 4 | Property names and values are validated against cached schema before API call; failures return structured errors with fuzzy-match suggestions and trigger one cache-refresh retry. |
| 10 | **Progress streaming for long ops** | small | `orchestrator.py`, `tools/objects.py` | 8 | Bulk operations stream chunk progress, ETA, and last-error to the user every N seconds or chunks. |
| 11 | **PII redaction** | medium | `redaction.py`, `ledger.py`, `trace.py` | 7 | Emails, phones, and names are masked via hashed placeholders in all disk-written logs/traces; redaction levels configurable as `off` / `pii` / `full`. |

### Phase A Dependency Graph

```
setup.py
  -> capabilities.probe_portal()     [task 2]
  -> cache.warm_standard_schemas()  [task 4]

orchestrator.py
  -> ledger.py            [task 7]  (before writes)
  -> checkpoint.py        [task 8]  (during bulk ops)
  -> capabilities.py      [task 2]  (before routing)
  -> maintenance.py       [task 3]  (session start)
  -> trace.py             [task 13] (throughout — B, but A sets hooks)

tools/*.py
  -> validation.py        [task 9]  (before API calls)
  -> checkpoint.py        [task 8]  (after chunks)
  -> cache.py             [task 4]  (schema lookup)

client.py
  -> errors.py            [task 1]  (categorized exceptions)
```

### Phase A Known Gaps (to resolve in Phase B)

- **Task 7 — Ledger completion wiring:** `record_action_completion` is implemented and tested, but the production `execute` path does not yet exist in the CLI/orchestrator. When Phase B builds the execute flow, call `record_action_completion(portal_id, action_id, result)` after every successful write. The 1-hour stale TTL on `find_similar_in_flight` prevents false duplicates until that wiring is in place.
- **Task 8 — Checkpoint resume wiring:** `CheckpointManager` records per-chunk state and offers `get_resume_state()`, but `batch_upsert_objects` does not yet read checkpoint state to skip already-completed chunks on restart. When Phase B builds the retry/resume flow, read the resume state at the start of a bulk operation and skip completed chunks.
- **Task 9 — Validation refresh no-op:** `retry_with_refresh=True` calls `cache.invalidate()` then `cache.get()`, but `SchemaCache.get()` reads from local disk only and never fetches from HubSpot. The retry path is useful when the cache was manually invalidated or re-seeded by cache warming (Task 4), but it cannot auto-recover from a permanently empty cache. Phase B should wire cache warming into the validation retry path or remove the retry flag.
- **Task 11 — Redaction heuristic limits:** The phone regex may still overmatch short numeric identifiers; the name heuristic may misclassify uncommon domain-like strings without common TLDs. Phase B should consider a deny-list approach for known non-PII patterns (invoice prefixes, product SKUs) or make redaction rules portal-configurable.

### Phase A On-Disk Additions

```
~/.claude/hubspot/<portal_id>/
  action_log.jsonl          # [task 7]  append-only
  capabilities.json          # [task 2]  TTL 24h
  in_flight/
    <action_id>.jsonl       # [task 8]
  completed/
    <action_id>.jsonl       # [task 8]
```

---

## Phase B — Intelligence & UX

> **Goal:** Make the agent pleasant to use, observable, and self-correcting. Upgrade routing, previews, approvals, and testing.
> **Estimated effort:** 2–3 months
> **Key principle:** LLM routing (task 12) replaces keyword heuristics; keep the old table commented-out initially for safe rollback.

| # | Task | Effort | Files | Dependencies | Acceptance Criteria |
|---|------|--------|-------|-------------|-------------------|
| 12 | **LLM routing replaces keyword heuristics** | medium | `orchestrator.py`, `agents/_base.py`, `prompts/routing.txt` | — | Parent reasons about routing in its own prompt without the keyword table; unambiguous fast-paths remain for common requests. |
| 13 | **Structured trace events** | small | `trace.py`, `cli.py` | — | Every request emits `traces.jsonl` events covering request received, route decision, tool call, approval, and completion. |
| 14 | **Cost & latency tracking** | small | `trace.py`, `cli.py` | 13 | Final trace event includes input/output tokens, tool call count, duration, and estimated USD cost; `/hubspot status` shows aggregates. |
| 15 | **Self-correction loop in sub-agents** | small | `agents/*.py`, `orchestrator.py` | 1, 9 | Sub-agent prompts handle `VALIDATION` / `CONFLICT` / `NOT_FOUND` by examining fields, searching existing records, or reporting missing prerequisites; any corrected payload re-enters HITL. |
| 16 | **Inline diff viewer for updates** | small | `preview.py`, `orchestrator.py` | — | Update previews render `old -> new` per field for the first 10 records and summarize the remainder by identical change pattern. |
| 17 | **Batch approval modes** | small | `orchestrator.py`, `preview.py` | — | HITL supports `--batch` (approve full plan once) and pattern mode (approve sample, auto-execute rest) with explicit user opt-in. |
| 18 | **Property-based testing (hypothesis)** | small | `tests/property_based/`, `pyproject.toml` | — | Hypothesis tests generate random valid and invalid inputs for every tool and assert no crashes plus well-formed error responses. |
| 19 | **Prompt regression suite** | medium | `tests/test_routing_regression.py`, `tests/routing_corpus.yaml` | 12 | YAML corpus of `(request, expected_route, expected_outcome)` runs at `temperature=0` and fails on prompt changes that silently break routing. |
| 20 | **Workflow blueprint library** | medium | `blueprints/workflows/*.py`, `agents/workflows.py` | — | WorkflowsAgent checks blueprints before raw construction; starter set of 3–5 blueprints passes end-to-end integration tests against a dev portal. |
| 21 | **Query-result cache** | small | `cache.py`, `tools/*.py` | — | Read tool results cached LRU for 5 min by `(tool, args_hash, portal_id)`; writes invalidate affected domains. |
| 22 | **Parallel sub-agent execution (read-only)** | small | `orchestrator.py` | 13 | Independent read-only agents dispatch concurrently via `asyncio.gather`; write-heavy parallel ops remain serial for HITL safety. |
| 23 | **Reflection / post-action review** | small | `orchestrator.py`, `tools/*.py` | — | High-risk writes automatically re-fetch the modified resource and verify field-level match against the proposed payload before reporting success. |
| 24 | **Custom routing rules per portal** | small | `routing.py`, `.claude/hubspot/<portal_id>/routing_overrides.json` | 12 | Per-portal vocabulary aliases and agent overrides inject into parent routing context without code changes. |
| 25 | **Tour mode** | small | `tour.py`, `cli.py` | — | `/hubspot tour` runs 5–7 interactive examples demonstrating read queries, write previews, and approval flows. |

### Phase B On-Disk Additions

```
~/.claude/hubspot/<portal_id>/
  traces.jsonl              # [task 13]
  query_cache.json          # [task 21]
~/.claude/hubspot/plugins/  # [task 35 — C, but B sets the hook]
  *.py
```

---

## Phase C — Domain Expansion

> **Goal:** Grow into adjacent HubSpot domains and advanced patterns. Contingent on observed usage and demand.
> **Estimated effort:** 6+ months
> **Key principle:** DAG planner (task 26) only activates for compound requests (>2 nodes); single-step requests bypass.

| # | Task | Effort | Files | Dependencies | Acceptance Criteria |
|---|------|--------|-------|-------------|-------------------|
| 26 | **Multi-step DAG planner** | medium | `plan.py`, `orchestrator.py`, `preview.py` | 12 | Compound requests generate a JSON DAG with nodes, inputs/outputs, and dependencies; user approves the full DAG before node-by-node execution. |
| 27 | **Interactive plan modification** | medium | `plan.py`, `orchestrator.py` | 26 | Approval prompt accepts `skip n3` and parameter edits; modified plan re-renders and re-validates dependency invariants before execution. |
| 28 | **Batch coalescing** | medium | `plan.py`, `orchestrator.py` | 26 | Serial writes to the same object type within a plan are buffered and flushed as a single batch API call at plan boundary. |
| 29 | **Replay tooling** | medium | `replay.py`, `tests/` | 13 | Any trace file can be replayed against a mock `HubSpotClient` with recorded responses, producing identical agent behavior for regression tests. |
| 30 | **Anomaly detection** | medium | `anomaly.py`, `trace.py`, `orchestrator.py` | 13 | Per-portal baselines track median failure rate and duration per tool; runs deviating >3 sigma trigger a warning pause. |
| 31 | **Custom objects support** | medium | `cache.py`, `orchestrator.py`, `agents/objects.py` | 9 | Agent dynamically discovers custom object schemas, routes custom object vocabulary to ObjectsAgent, and validates on demand. |
| 32 | **Reporting & dashboards** | medium | `tools/reporting.py`, `agents/analytics.py` | — | AnalyticsAgent creates custom reports, assembles dashboards, and schedules email delivery via HubSpot reporting APIs. |
| 33 | **Service hub expansion** | medium | `tools/service.py`, `agents/service.py` | — | New ServiceAgent covers knowledge base articles, ticket pipelines, service automation, and customer feedback surveys. |
| 34 | **Role-based access** | medium | `roles.py`, `orchestrator.py` | — | `roles.json` restricts per-user allowed agents and max risk level; checked before dispatch. |
| 35 | **Plugin architecture** | medium | `plugins.py`, `orchestrator.py` | — | Python files in `~/.claude/hubspot/plugins/` register tools via `@tool` decorator and augment sub-agents at startup. |
| 36 | **Chaos testing harness** | medium | `tests/chaos/`, `testing.py` | 1 | Fault injection (5% rate-limit, 1% network error, 0.1% truncation) over existing tests verifies agent recovery and graceful degradation. |
| 37 | **Marketing campaigns / email** | large | `tools/marketing.py`, `agents/marketing.py` | — | New MarketingAgent with 8–12 tools handles email creation, campaigns, segmentation, A/B tests, and suppression lists. |
| 38 | **Webhooks / event subscriptions** | large | `webhooks.py`, `server.py`, `orchestrator.py` | — | Long-running webhook listener validates and ingests HubSpot events, triggering agent reactions without user prompt. |
| 39 | **Sandbox-first dangerous changes** | large | `sandbox.py`, `orchestrator.py` | 26, 23 | High-risk operations offer sandbox preview first; agent replicates change, runs a test workload, and reports behavior diff before prod apply. |
| 40 | **Conversation memory** | medium | `memory.py`, `orchestrator.py` | — | Session summaries persist to disk on session end; new sessions load the last summary as context to reduce prompt bloat. |
| 41 | **Hook system for pre/post-write events** | medium | `hooks.py`, `orchestrator.py` | — | Async `pre_write`, `post_write`, `pre_approval`, `post_approval` hooks are configurable and can block or mirror events to external systems. |
| 42 | **CMS, files, social** | medium | `tools/cms.py`, `agents/cms.py` | — | CMSAgent manages HubSpot pages, file manager assets, and social media publishing via respective APIs. |

### Phase C On-Disk Additions

```
~/.claude/hubspot/<portal_id>/
  sessions/
    <session_id>.json         # [task 40]
  roles.json                  # [task 34]
  routing_overrides.json      # [task 24 — actually B, but C is when it becomes load-bearing]
```

---

## Cross-Cutting Concerns

### PII Redaction (task 11 — Phase A)

Runs over every string before it is written to `audit.log`, `traces.jsonl`, or `action_log.jsonl`:
- Email-shaped strings → `<email:abc123>` (hashed for correlation)
- Phone numbers → `<phone:def456>`
- Names from a configurable list → `<name:ghi789>`

Configurable levels: `off` (nothing), `pii` (emails/phones/names), `full` (any long string).

### Top Three Integration Risks

1. **Ledger write failure as a gate.** If `action_log.jsonl` is on a full disk or read-only filesystem, the agent refuses writes. This is by design, but creates a hard dependency on local disk health. Mitigation: graceful degradation to a memory-only ledger with a loud warning.
2. **Validation layer vs. cache staleness.** Schema-aware validation (task 9) will falsely reject if the cache hasn't seen a freshly created property. The "refresh and retry once" mitigation helps but adds latency. Mitigation: short cache TTL for property metadata and a "force skip validation" escape hatch.
3. **LLM routing non-determinism.** Moving from keyword heuristics to LLM routing (task 12) improves accuracy but introduces variance. Without the prompt regression suite (task 19), prompt changes can silently break routing. Mitigation: ship the regression suite simultaneously with LLM routing, not after.

---

## Execution Strategy

This plan is designed for **phase-gated execution**:

1. **Phase A first** — tasks 1–11. Foundation modules are additive and can be disabled. Completing Phase A makes the agent robust before adding intelligence features.
2. **Phase B second** — tasks 12–25. Intelligence and UX upgrades build on the stable foundation.
3. **Phase C third** — tasks 26–42. Domain expansion and advanced patterns are contingent on observed usage.

Within each phase, tasks run in the numbered order shown above. Dependencies are satisfied by the ordering.

---

*Generated by Claude Code — Architecture Evolution Pipeline*
