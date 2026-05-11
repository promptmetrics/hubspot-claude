# HubSpot Agent: Architecture Evolution — Research Document

**Date:** 2026-05-07
**Author:** Claude / Izzy collaboration
**Status:** Draft for review
**Companion docs:** [Spec](../specs/2026-05-06-hubspot-agent-design.md) · [Plan](../plans/2026-05-06-hubspot-agent-plan.md)

---

## 1. Purpose & Context

The HubSpot Admin Agent has a complete spec and a 39-task implementation plan. The current design covers 11 specialist sub-agents, parent-routed dispatch, HITL approval, schema cache, undo snapshots, multi-portal support, audit logging, and a research workflow via Claude Code's native `WebSearch`.

That gets us to "production-ready demo." This document maps the territory between that and "production-grade tool you'd hand to a junior admin without anxiety." It is intentionally broad — the goal is to inventory the full possibility space, evaluate each direction honestly, and recommend a phased path forward. Where the spec and plan describe what to *build*, this document describes what to *consider building next*.

The document is opinionated. Each direction carries a verdict (Foundation / Leverage / Speculative / Skip) so the reader can skim to the conclusions and read deeper only where the verdict warrants discussion.

---

## 2. Evaluation Framework

Each direction is judged on five dimensions:

**Failure mode addressed.** What concrete thing breaks today, or will break at scale, without this? An improvement that doesn't fix a real failure mode is decoration.

**Effort.** Lines of code, plan-integration cost, and ongoing maintenance burden — not just initial build.

**New risk.** What does this introduce? Some "improvements" trade a clear failure mode for a fuzzy one.

**Sequencing.** What must exist first?

**Reversibility.** Can we ship and remove cleanly if it doesn't work? Reversible additions deserve more lenient cost-benefit thresholds than load-bearing ones.

The verdict shorthand:

- **Foundation** — needed before scaling beyond demo usage
- **Leverage** — high impact, contained scope, clear win
- **Speculative** — real value but contingent on facts we don't yet have
- **Skip** — the case is weaker than it looks
- **Conditional** — verdict depends on a context question (single vs multi-user, compliance vs personal, etc.)

---

## 3. Reliability Foundations

These directions address failure modes the current design does not handle but will encounter as soon as the agent runs on a real portal with non-trivial volume.

### 3.1 Action ledger for true idempotency

**Failure mode.** The current design's "post-timeout reconciliation via HygieneAgent" fires only after a write timeout. Sub-agents are stateless and the parent re-dispatches via prompt embedding, which means: if the user re-runs the same request, hits "approve" again on a stale plan, or the parent restarts mid-execution, there is no record that says "this action already happened." Duplicate creates and double-applied updates are the predictable consequence.

**Sketch.** Before any write dispatch, the orchestrator appends to `.claude/hubspot/<portal_id>/action_log.jsonl`:

```json
{"action_id": "act_2026-05-07T14:23:01_a4f9", "status": "started",
 "agent": "ObjectsAgent", "endpoint": "POST /crm/v3/objects/contacts",
 "payload_hash": "sha256:...", "approved_by": "izzy@...", "ts": "..."}
```

After the write completes, append `{"action_id": ..., "status": "completed", "result": ..., "ts": "..."}`. On every dispatch, check the ledger first — if a non-completed entry matches the payload hash within a recent window (e.g., 1 hour), the parent surfaces "this action started but didn't complete; check status before retrying" instead of re-dispatching.

**Effort.** Small. ~150 lines + tests. New `ledger.py` module, integration in orchestrator HITL flow.

**Risk.** Adds a write-before-write dependency. If the ledger write fails, the action shouldn't proceed. Need to handle ledger corruption gracefully (fsync, rotation).

**Verdict: Foundation.** This replaces ad-hoc reconciliation with deterministic recovery and addresses the most predictable failure mode in the current design.

### 3.2 Mid-execution checkpointing for bulk operations

**Failure mode.** A 1000-record update is chunked into ten 100-record batches. If batch 7 fails or the user cancels, there is no record of what got applied. The user is left to manually diff. With chunked writes, partial success is the norm, not the exception.

**Sketch.** `hubspot_batch_upsert_objects` writes to `.claude/hubspot/<portal_id>/in_flight/<action_id>.jsonl` after each chunk:

```json
{"chunk_index": 6, "succeeded": 100, "failed": 0, "ts": "..."}
{"chunk_index": 7, "succeeded": 87, "failed": 13, "errors": [...], "ts": "..."}
```

The orchestrator supports resumption: when a request matches a non-completed in-flight file, present "Last run completed 700/1000 with 13 errors. Resume from chunk 8? (y/n/details)". On completion, the in-flight file is moved to `completed/` or pruned per TTL.

**Effort.** Small-to-medium. ~250 lines split across `tools/objects.py`, orchestrator, and tests. Pairs naturally with the action ledger (3.1).

**Risk.** State on disk grows over time. Mitigated by a simple TTL-based cleanup task.

**Verdict: Foundation.** Together with 3.1, this turns "the bulk update mostly worked, I think" into "the bulk update applied A but not B, here's exactly which records."

### 3.3 Schema-aware pre-validation

**Failure mode.** Every tool today is a thin API wrapper. A typo'd property name burns a full round trip and returns a generic 400. In a batch of 100 records, one bad property name fails all 100. This is wasteful (rate limit budget), slow (round-trip latency), and gives the agent only generic feedback for self-correction.

**Sketch.** The `schema_cache.json` you already plan to maintain becomes a validation source. Before any write, the relevant tool checks:

For `hubspot_create_object` / `hubspot_update_object`: every property name in the payload exists in the cache for that object type, and the value matches the property's `fieldType` constraint (text length, number type, enum options, date format).

For `hubspot_create_property`: the proposed `groupName` exists, the `fieldType` is valid for the property `type` (HubSpot has subtle type/fieldType pairing rules), and the `name` doesn't collide with an existing property.

For `hubspot_associate_records`: the association schema between the two object types exists.

Validation errors return a structured shape the agent can act on:

```json
{"validation_error": true,
 "field": "renewal_dat",
 "reason": "property does not exist on contacts",
 "suggestion": "did you mean 'renewal_date'?",
 "candidates": ["renewal_date", "renewal_data"]}
```

**Effort.** Medium. Per-tool validation hooks (~50 lines each), schema cache enrichment to expose lookup helpers, fuzzy-match for suggestions. Roughly a week.

**Risk.** Cache staleness. If the cache hasn't seen a freshly created property, validation falsely rejects. Mitigation: validation failures trigger a cache refresh and one retry before surfacing.

**Verdict: Foundation.** Highest leverage of the three reliability foundations. Catches the most common error class locally, gives the self-correction loop something to work with, and saves rate limit budget on bulk ops.

### 3.4 Error category taxonomy

**Failure mode.** Today, errors come back as `HubSpotError(400, message)` and the agent has to read the message string to decide what to do. HubSpot returns errors in several distinct shapes (validation, auth, rate limit, conflict, not found, server). Treating them uniformly forces every retry/handle/correct decision to depend on string parsing.

**Sketch.** Extend `HubSpotClient._request` to map status codes and response body shapes into a small enum:

```python
class ErrorCategory(str, Enum):
    VALIDATION = "validation"        # 400 with field-level details
    AUTH       = "auth"              # 401
    SCOPE      = "scope"             # 403
    NOT_FOUND  = "not_found"         # 404
    CONFLICT   = "conflict"          # 409 (often duplicates)
    RATE_LIMIT = "rate_limit"        # 429
    SERVER     = "server"            # 5xx
    UNKNOWN    = "unknown"
```

Every `HubSpotError` carries `category: ErrorCategory`. Agent prompts include guidance keyed off the category: "If you see VALIDATION, examine the field-level errors and propose a corrected payload. If CONFLICT, the record may already exist — search before re-attempting."

**Effort.** Tiny. <100 lines in `errors.py` and `client.py`.

**Risk.** None worth mentioning.

**Verdict: Leverage.** Not strictly required, but makes 3.3 and the self-correction loop substantially more effective. Cheap.

---

## 4. Intelligence Upgrades

These directions improve how the agent reasons about requests and handles unexpected situations.

### 4.1 LLM routing replaces keyword heuristics

**Failure mode.** The keyword table in §5 of the spec maps trigger words to agents. This will fail constantly on anything that uses HubSpot vocabulary even slightly off — "smart list" vs "active list" vs "dynamic list" all mean the same thing; "owner" could mean ListsAgent (filter by owner), ObjectsAgent (set owner field), or UsersAgent (manage user records). Every miss becomes a maintenance ticket.

**Sketch.** The parent is already a Claude instance. Drop the keyword table entirely and let the parent reason about routing in its own prompt:

> Available domain agents: [list with descriptions and example requests]. Read the user's request and decide which agent(s) to dispatch. If the request spans domains, decide whether they can run in parallel or have a dependency. If ambiguous, ask the user one clarifying question before dispatching.

Keep the static dependency graph (PropertiesAgent → WorkflowsAgent for properties referenced in workflow criteria) as a hint the parent can use when sequencing — not as the primary routing mechanism.

**Effort.** Medium. The parent's prompt grows but the routing module shrinks. ~200 lines net change. The bigger cost is testing — you need a regression suite of "request → expected agents" so prompt changes don't silently break routing.

**Risk.** Higher token cost per request and routing decisions become non-deterministic. Mitigation: a small set of unambiguous fast-paths (e.g., `/hubspot how many contacts` → AnalyticsAgent without parent reasoning) for the most common requests.

**Verdict: Leverage.** The plan already flags this as a Phase 2 candidate. I'd promote it to early Phase 1 because keyword routing will produce visibly bad behavior on day one, and "keyword maintenance" should not be the dominant work after launch.

### 4.2 Self-correction loop in sub-agents

**Failure mode.** Today, a tool error triggers up to 3 retries with the same payload. That's only useful for transient errors. For systemic ones — wrong field type, missing prerequisite, stale schema — retrying is useless and burns rate limit budget.

**Sketch.** Update each sub-agent's system prompt with explicit error-handling guidance keyed off the category taxonomy (3.4):

> When a tool returns `category: VALIDATION`, examine field-level errors. If a property doesn't exist, search for similar names; if a value is rejected, examine the property's allowed type. Propose a corrected payload and call the tool again at most once.
>
> When a tool returns `category: CONFLICT`, search for the existing record before attempting to create. Decide whether to update instead.
>
> When a tool returns `category: NOT_FOUND`, do not retry. Report what is missing.

Combined with schema-aware validation (3.3), most validation errors get caught locally before the agent is invoked, and the few that escape are precisely categorized so the agent can correct them.

**Effort.** Small. Prompt-only changes. The real cost is regression tests covering each error category per agent.

**Risk.** Agents get clever and self-correct in ways the user didn't expect. Mitigation: any self-correction that changes the proposed payload re-enters the HITL preview flow.

**Verdict: Leverage.** Pairs tightly with 3.3 and 3.4. Each on its own is modest; together they upgrade the agent from "fragile" to "robust."

### 4.3 Workflow blueprint library

**Failure mode.** Workflows are the trickiest domain in HubSpot — the API surface is composable but the semantics (re-enrollment, suppression, branching, delays, criteria operators, action graph dependencies) are deep. Asking the LLM to synthesize a correct workflow from raw API docs every time is a recipe for subtle bugs that only surface in production.

**Sketch.** A library of parameterized blueprints in `src/hubspot_agent/blueprints/workflows/`:

- `renewal_alert(days_before, owner_field, deal_pipeline)` — alerts deal owner N days before close date
- `lead_routing_round_robin(team_id, lead_filter)` — round-robins new MQLs across team members
- `mql_to_sql_handoff(score_threshold, sales_owner_field)` — flips lifecycle stage when score crosses threshold
- `inactive_contact_workflow(days_inactive, action)` — re-engages or archives stale contacts
- `welcome_sequence(trigger_property, email_ids, delays)` — basic onboarding sequence

WorkflowsAgent's prompt says: "Before building a workflow from scratch, check `list_blueprints()` for a parameterized template that matches the user's intent. Use the blueprint when one fits; fall back to raw construction only when no blueprint matches."

**Effort.** Medium-to-large. Each blueprint is ~100-200 lines including integration tests. A starter set of 5-8 blueprints is a 2-3 week project. Ongoing maintenance as HubSpot's workflow API evolves.

**Risk.** Blueprints can drift from HubSpot's actual behavior if the API changes. Need integration tests against a dev portal exercising each blueprint end-to-end.

**Verdict: Leverage** for the first 3-5 blueprints (the patterns covering 80% of common requests); **Speculative** for going beyond that. Maintenance cost grows with the library.

### 4.4 Multi-step planning with explicit DAG

**Failure mode.** Compound requests like "create a renewal date property, build a workflow that uses it, and add affected contacts to a list" require sequencing. The current design uses keyword + static graph for ordering. For three-step requests this is fine; for ten-step requests it's a guessing game.

**Sketch.** When the parent detects a compound request, it constructs an explicit DAG before any dispatch:

```json
{
  "plan_id": "plan_...",
  "nodes": [
    {"id": "n1", "agent": "PropertiesAgent",
     "action": "create renewal_date property", "outputs": ["property_name"]},
    {"id": "n2", "agent": "WorkflowsAgent",
     "action": "create renewal alert workflow",
     "inputs": ["n1.property_name"], "depends_on": ["n1"]},
    {"id": "n3", "agent": "ListsAgent",
     "action": "create renewals-due list",
     "inputs": ["n1.property_name"], "depends_on": ["n1"]}
  ]
}
```

The parent presents the DAG to the user for approval before dispatching anything. Approved DAG is then executed node-by-node, with each node's output becoming the next node's input. Failure of one node can halt execution or skip dependents based on policy.

**Effort.** Medium-to-large. New `plan.py` module, DAG executor, plan-preview rendering, plan-modification UI ("skip n3" / "redo n2"). 1-2 weeks.

**Risk.** Adds an abstraction layer. For simple requests it's overhead. Mitigation: only construct DAGs for compound requests (>2 nodes); single-step requests bypass.

**Verdict: Speculative.** Real value only if users frequently issue compound requests. I'd watch the request distribution after launch and decide based on data.

### 4.5 Reflection / post-action review

**Failure mode.** After a write completes, the agent reports success and moves on. There's no check on whether the change actually achieved the user's intent. "Created the workflow" doesn't mean "the workflow does what you described."

**Sketch.** For non-trivial writes, the agent runs a post-action verification step: re-fetch the created/modified resource and confirm it matches the proposed payload. For workflows, optionally run a no-op enrollment to verify it triggers correctly. Report verification results alongside the success message.

**Effort.** Small-to-medium. ~200 lines + per-domain verification logic.

**Risk.** Adds latency to every write. Mitigation: skip verification for low-risk, well-tested operations (e.g., creating a contact); always verify high-risk ones (workflow changes, association schema changes).

**Verdict: Leverage** for the high-risk subset; **Skip** for everything else.

---

## 5. Observability & Debugging

### 5.1 Structured trace events

**Failure mode.** When the agent routes a request unexpectedly, calls a surprising tool, or returns a confusing result, you have no record of why. The audit log captures writes; this captures everything.

**Sketch.** Emit JSONL trace events to `.claude/hubspot/<portal_id>/traces.jsonl`:

```json
{"event": "request_received", "request_id": "...", "request_text": "...", "ts": "..."}
{"event": "route_decision", "agents": ["ObjectsAgent"], "reason": "...", "ts": "..."}
{"event": "tool_called", "agent": "ObjectsAgent", "tool": "hubspot_search_objects",
 "args_summary": {...}, "ts": "..."}
{"event": "tool_returned", "tool": "...", "result_summary": {...}, "duration_ms": 423}
{"event": "informing_sources", "sources": [...]}
{"event": "preview_presented", "risk_level": "destructive", "impact_count": 47}
{"event": "approval_received", "verdict": "approved", "ts": "..."}
{"event": "request_completed", "outcome": "success", "ts": "..."}
```

A small CLI viewer (`/hubspot trace last`, `/hubspot trace <request_id>`) lets you inspect what happened.

**Effort.** Small. ~200 lines + CLI viewer.

**Risk.** Privacy — traces capture request text. Mitigation: PII redaction layer (6.3) before write; opt-in for full text.

**Verdict: Leverage.** The first time a user asks "why did it do that," you'll regret not having it.

### 5.2 Cost & latency tracking per request

**Failure mode.** Each sub-agent dispatch costs tokens. Sub-agents that do research call WebSearch, adding tokens. A single compound request can rack up significant cost without the user knowing. You also have no signal on which agents/tools are slow.

**Sketch.** Augment trace events with token counts and latency. Emit a final `request_summary` event:

```json
{"event": "request_summary",
 "input_tokens": 4523, "output_tokens": 891,
 "total_tool_calls": 12,
 "duration_ms": 8234,
 "estimated_cost_usd": 0.067}
```

Surface aggregates via `/hubspot status` and `/hubspot budget`.

**Effort.** Small. Hooks into existing trace infrastructure.

**Risk.** Cost estimates may drift from actual billing. Be conservative.

**Verdict: Leverage.** Not for individual requests but for understanding what the agent costs in aggregate.

### 5.3 Replay tooling

**Failure mode.** When a user reports "the agent did the wrong thing," you can read the trace but not actually re-run the request to debug. Re-running against the live portal is dangerous; re-running against a different portal loses state.

**Sketch.** A `replay` mode that takes a trace file and re-executes it against a mock client (`HubSpotClient` with a recorded-response backend). Useful for regression testing prompt changes against historical requests.

**Effort.** Medium. Recorded-response backend + replay harness + tests.

**Risk.** Recordings drift from real API behavior over time.

**Verdict: Speculative.** Worth it once you have enough volume to justify a regression test corpus. Skip until then.

### 5.4 Anomaly detection on operation outcomes

**Failure mode.** A bulk update normally has 1-2% failures. If a particular run has 30% failures, that's a signal something is wrong — wrong portal, wrong target list, schema drift. The current design treats every batch identically.

**Sketch.** The orchestrator tracks per-portal baselines (median failure rate, median duration) per tool/operation type. When a run deviates significantly (e.g., >3 standard deviations on failure rate), pause and surface: "This run has 30% failures, vs. typical 2%. Continue or abort?"

**Effort.** Medium. Baseline tracking + statistical thresholds + UX for the warning.

**Risk.** False positives are annoying. Need careful threshold tuning.

**Verdict: Speculative.** Real value but contingent on having enough historical data to set baselines. Defer until then.

---

## 6. Safety & Permissions

### 6.1 Portal capability matrix (probe-on-first-use)

**Failure mode.** The current design stores `tier` as a string (Professional, Enterprise) but doesn't actually probe what features are enabled. Custom objects require Enterprise. Calculated properties have separate gating. AI tools have their own. The agent will discover these limits one failed write at a time.

**Sketch.** On first connection to a portal, run a capability probe:

- Fetch `/account-info/v3/details` for tier
- List custom object schemas (succeeds = enterprise, 403 = not)
- Check workflow API access (`/automation/v4/workflows?limit=1`)
- Check user management (`/settings/v3/users?limit=1`)
- Test calculated property creation against a sandbox property
- Cache results in `.claude/hubspot/<portal_id>/capabilities.json`

The capability matrix gates the parent's routing: if a request requires a capability the portal doesn't have, the parent declines with a clear explanation rather than dispatching and discovering mid-flight.

**Effort.** Small. ~150 lines + tests.

**Risk.** Capabilities can change (tier upgrade). TTL the cache (24h) and refresh on `/hubspot refresh`.

**Verdict: Foundation.** Cheap and prevents a class of confusing failures.

### 6.2 Sandbox-first dangerous-change pattern

**Failure mode.** Some changes — workflow logic, association schema changes, pipeline restructuring — are very hard to undo cleanly. Even with the destructive gate, the user is gambling that they understand the blast radius.

**Sketch.** For high-risk operations, the agent offers a "sandbox preview" option: replicate the change to the user's HubSpot sandbox portal first, run a small test workload, and report behavior before applying to production. Requires a sandbox portal mapping in the portal config.

**Effort.** Large. Sandbox replication is non-trivial because schemas may diverge, and "run test workload" requires fixture data. 2-4 weeks.

**Risk.** Sandbox drift produces false confidence ("worked in sandbox, broke in prod").

**Verdict: Speculative.** Real value but high effort. Defer until the first production incident makes the case for it.

### 6.3 PII redaction in traces and logs

**Failure mode.** Trace events and audit logs capture request text and tool args. Both can contain emails, phone numbers, names, and other PII. Storing this on disk indefinitely is a liability — especially in regulated environments.

**Sketch.** A `redaction.py` module that runs over every log/trace write:

- Email-shaped strings → `<email:abc123>` (hashed for correlation)
- Phone numbers → `<phone:def456>`
- Names from a configurable list → `<name:ghi789>`

Configurable redaction levels: `off` (nothing redacted), `pii` (emails/phones/names), `full` (any string longer than N chars).

**Effort.** Medium. Regex + hash mapping + config plumbing + tests against known PII patterns.

**Risk.** Over-redaction makes traces useless for debugging. Under-redaction creates the very liability you're trying to avoid. Hard to get right.

**Verdict: Conditional.** Foundation if the agent will be used in compliance-sensitive environments; Skip if it's solo / personal portals only.

### 6.4 Snapshot pruning + TTL

**Failure mode.** Undo snapshots, traces, and in-flight files accumulate forever in `.claude/hubspot/<portal_id>/`. Without cleanup, the directory becomes both a privacy risk and a disk-space surprise.

**Sketch.** A scheduled cleanup task (run on session start, or via `/hubspot maintenance`) that:

- Prunes undo snapshots older than 30 days
- Prunes completed in-flight files older than 7 days
- Rotates traces.jsonl when it exceeds 100 MB
- Surfaces "last 10 reversible actions" via `/hubspot undo list`

**Effort.** Small. ~150 lines + tests.

**Risk.** Premature pruning of a snapshot the user wanted to undo. Mitigation: warn before pruning anything still within an "undo-able" window.

**Verdict: Foundation.** Cheap and prevents long-term decay.

### 6.5 Role-based access within the agent

**Failure mode.** All users of a portal have the same agent capabilities. In a team setting, you might want some users limited to reads, or to specific domains.

**Sketch.** Per-user role config in `.claude/hubspot/<portal_id>/roles.json`:

```json
{"izzy@...": {"role": "admin", "allowed_agents": "*"},
 "ops@...": {"role": "operator", "allowed_agents": ["ObjectsAgent", "ListsAgent"], "max_risk_level": "medium"}}
```

The orchestrator checks the active user against the role config before dispatching.

**Effort.** Medium.

**Risk.** Role enforcement is only as good as user identification. Without strong auth, this is advisory at best.

**Verdict: Conditional.** Useful in multi-user contexts; pointless solo.

---

## 7. UX & Interaction Patterns

### 7.1 Inline diff viewer for updates

**Failure mode.** The current preview format renders proposed changes as markdown. For an update affecting 10 fields on 50 contacts, the markdown gets unreadable.

**Sketch.** The HITL preview, when the change is an update, renders as a diff:

```
contact #12345 (jane.doe@example.com)
  lifecycle_stage:  marketingqualifiedlead → salesqualifiedlead
  hubspot_owner_id: <unset>                → 28392
  last_contacted:   2025-11-12              → 2026-05-07
```

For bulk updates, render the first 10 in full diff and summarize the rest by aggregate counts ("47 more contacts with the same change pattern").

**Effort.** Small-to-medium. ~300 lines + tests.

**Risk.** None.

**Verdict: Leverage.** Cheap, high user-value, no downside.

### 7.2 Conversation memory beyond chat history

**Failure mode.** The current design uses chat history as primary state. For long sessions, the chat fills with stale context the agent has to re-read every turn. After a session resets (reload, crash), context is gone entirely.

**Sketch.** The orchestrator periodically (every N turns or on session-end) summarizes the active session into `.claude/hubspot/<portal_id>/sessions/<session_id>.json`:

```json
{"summary": "Created 3 properties (renewal_date, ...). Built workflow X. Reviewed 12 duplicate contact pairs, merged 8.",
 "open_threads": ["dup pair {a,b} pending review"],
 "decisions": [...]}
```

On a new session, the parent loads the most recent summary as additional context.

**Effort.** Medium. Summarization prompts, persistence, loading logic.

**Risk.** Summaries can omit important context. Mitigation: keep raw transcripts available; summary is a hint, not the source of truth.

**Verdict: Speculative.** Useful but not foundational. If sessions are typically short, this is overkill.

### 7.3 Progress streaming for long operations

**Failure mode.** A 10,000-record bulk update takes minutes. The user sees nothing until completion, has no idea if it's working or hung, can't cancel cleanly.

**Sketch.** Long-running ops emit progress messages: "Chunk 4 of 100 complete (400/10000). Estimated 8 min remaining. Last error: 0." Pairs naturally with checkpointing (3.2) and cancellation handling.

**Effort.** Small. ~150 lines.

**Risk.** None.

**Verdict: Leverage.** Bulk ops are common and currently invisible in flight.

### 7.4 Batch approval modes

**Failure mode.** A multi-step request with several writes generates several approval prompts. Each requires the user's attention. For a known-safe pattern (e.g., "create 50 tasks for these 50 leads"), prompting 50 times is annoying.

**Sketch.** The HITL flow gains modes:

- `default` — current behavior, approve each write
- `batch` — show full plan up front, approve once for the whole plan
- `pattern` — approve a representative sample (first 3), auto-execute the rest with the same pattern

Mode is requested by the user explicitly: `/hubspot --batch <request>`.

**Effort.** Small-to-medium.

**Risk.** Pattern mode can mask issues if the "rest" diverges from the sample. Limit to read-then-write patterns where divergence is unlikely.

**Verdict: Leverage** for batch mode, **Speculative** for pattern mode.

### 7.5 Interactive plan modification

**Failure mode.** When the parent presents a plan (especially a DAG, 4.4), the user can only approve or reject. They might want to modify: "skip step 3," "do step 2 with a different parameter."

**Sketch.** The approval prompt accepts plan-modification commands:

```
[plan presented]
> skip n3
[plan re-rendered without n3]
> approve
```

**Effort.** Medium. Plan-modification grammar, re-rendering, validation that modified plan is still valid.

**Risk.** Modifying a plan in flight can break dependency invariants.

**Verdict: Speculative.** Pairs with 4.4. Worth it only if DAG planning ships first.

---

## 8. Domain Coverage Expansion

The plan marks several HubSpot areas as out of scope for MVP. Each is a real expansion vector worth considering once the foundation is solid.

### 8.1 Custom objects

The current design only handles the four standard objects (contacts, companies, deals, tickets). Real Enterprise admins use custom objects for things like Subscriptions, Properties (real estate), Vehicles, Patients. Adding custom object support means: (a) the schema cache must handle dynamic object types, (b) the routing layer must match `subscription` to ObjectsAgent dynamically, (c) the validation layer must fetch the schema on demand.

**Effort.** Medium. The Python tools generalize cleanly because they already accept `object_type` as a parameter; the work is mainly in routing, validation, and prompt updates that explain custom objects to each agent.

**Verdict: Conditional.** Leverage if your users need custom objects; Skip otherwise.

### 8.2 Marketing campaigns / email

Email and campaign tools are a separate API surface (`/marketing/v3/emails`, `/marketing/v3/campaigns`, etc.). The patterns are analogous to existing tools but the domain knowledge is heavier — segmentation, A/B testing, deliverability, suppression lists, send-time optimization. Probably its own MarketingAgent and 8-12 new tools.

**Effort.** Large.

**Verdict: Speculative.** Big surface area. Defer unless there's a clear use case.

### 8.3 Service hub (tickets, knowledge base)

Tickets are already covered as an object type, but the surrounding service hub (knowledge base articles, ticket pipelines, service-specific automation, customer feedback surveys) isn't. A natural extension if you have customers who use HubSpot for support.

**Effort.** Medium.

**Verdict: Speculative.**

### 8.4 Webhooks / event subscriptions

The current design is request-driven. A webhook listener would let the agent react to HubSpot events ("new lead arrives, route to Sales") without the user asking. Big departure from the current architecture — the agent becomes long-running, needs a transport layer, and a security boundary for webhook validation.

**Effort.** Large.

**Verdict: Speculative.** Significant scope creep. Worth its own design doc if pursued.

### 8.5 CMS, files, social

HubSpot has tools for CMS pages, file management, and social media publishing. Each is its own API surface. Almost certainly out of scope for an admin agent unless the users you have in mind use HubSpot as a marketing platform.

**Verdict: Skip** unless explicitly requested.

### 8.6 Reporting & dashboards

The current AnalyticsAgent fetches raw report data and computes metrics client-side. A natural expansion: create custom reports, build dashboards, schedule report delivery. HubSpot's reporting API is well-documented but has tier-gated features.

**Effort.** Medium.

**Verdict: Speculative.**

---

## 9. Performance & Scale

### 9.1 Smarter caching beyond schema

**Failure mode.** Schema cache is good but doesn't help when the same query is issued repeatedly within a session ("how many contacts in northeast" twice). Every call hits the API.

**Sketch.** An LRU query-result cache for read tools, keyed on `(tool, args_hash, portal_id)`. Short TTL (5 min) so freshness is preserved. Invalidate on writes that affect the queried domain.

**Effort.** Small.

**Risk.** Stale results. Short TTL minimizes this but doesn't eliminate it.

**Verdict: Conditional.** Leverage for read-heavy use cases; Skip otherwise.

### 9.2 Batch coalescing

**Failure mode.** Compound requests can produce many small writes that the agent issues serially: "update contact A, update contact B, update contact C." Each is a round trip when one batch call would suffice.

**Sketch.** The orchestrator buffers writes during a multi-step plan execution and flushes them as batches at plan boundaries. Requires the DAG planner (4.4) to know what's coalescable.

**Effort.** Medium.

**Risk.** Adds latency to single writes (waiting for the buffer) unless carefully tuned.

**Verdict: Speculative.** Helps only at scale. Premature optimization until the problem is observed.

### 9.3 Parallel sub-agent execution

**Failure mode.** The plan supports parallel dispatch in principle but doesn't explicitly orchestrate it. For independent steps (find duplicate contacts + create unrelated workflow), serial execution is wasted time.

**Sketch.** When the routing decision identifies independent agents, dispatch them concurrently using `asyncio.gather` or Claude Code's parallel `Agent` calls. Result-merging happens at the parent level.

**Effort.** Small. Mostly an orchestrator change.

**Risk.** HITL approval gets harder if previews arrive interleaved. Parallelism is safer for read-heavy parallel ops than write-heavy ones.

**Verdict: Leverage** for read-heavy parallel ops, **Skip** for write-heavy ones (HITL coordination not worth it).

### 9.4 Background pre-fetch for likely-needed schemas

**Failure mode.** First request after `/hubspot portal switch` is slow because the schema cache is cold. Each new domain queried hits a fresh API call.

**Sketch.** On portal switch, kick off a background task that warms the schema cache for the four standard object types and the most-recently-queried custom objects. User's next request finds a warm cache.

**Effort.** Small.

**Verdict: Leverage.** Cheap, noticeable UX improvement.

---

## 10. Extensibility

### 10.1 Plugin architecture for custom tools

**Failure mode.** Users with HubSpot setups that use custom integrations (a custom CRM extension, a partner integration) can't register their own tools today. The agent is closed.

**Sketch.** A plugin protocol: drop a Python file into `~/.claude/hubspot/plugins/`, the file registers tools via the existing `@tool` decorator, the orchestrator picks them up at startup. Plugins declare which sub-agent(s) they augment.

**Effort.** Medium. Plugin loader, security boundary (plugins run with full access — this is by design but worth documenting), versioning story.

**Risk.** Security. A malicious plugin has full access to the agent's credentials and HubSpot scopes. Mitigation: plugins must be installed by the user explicitly, not auto-loaded.

**Verdict: Speculative.** Worth it if you imagine multiple users; skip if it's personal-use.

### 10.2 Hook system for pre/post-write events

**Failure mode.** Power users want to wire side effects: "after every workflow change, post to Slack." Today they'd have to fork.

**Sketch.** Pre/post hooks fire on standard events (`pre_write`, `post_write`, `pre_approval`, `post_approval`). Hooks are async callables registered via config. Use cases: Slack notifications, audit log mirroring to external SIEM, custom approval policies.

**Effort.** Medium.

**Verdict: Speculative.**

### 10.3 Custom routing rules per portal

**Failure mode.** Different portals have different conventions. A real estate firm's portal uses "deal" to mean "listing"; a SaaS portal uses "deal" to mean "subscription." Single global routing fits awkwardly.

**Sketch.** Per-portal routing override file: `.claude/hubspot/<portal_id>/routing_overrides.json`:

```json
{"vocabulary": {"listing": "deals", "tenant": "contacts"},
 "agent_aliases": {"renewals": "WorkflowsAgent"}}
```

The parent applies overrides before any routing decision.

**Effort.** Small (built on top of LLM routing — 4.1 — overrides become extra context in the parent's prompt).

**Verdict: Speculative.** Useful for multi-tenant scenarios; skip otherwise.

---

## 11. Onboarding & First-Run Experience

### 11.1 Guided setup wizard

**Failure mode.** First time a user runs `/hubspot`, they need: a portal ID, a token (OAuth or Private App), the right scopes selected, the schema cache warmed. The current spec glosses over this.

**Sketch.** A `/hubspot setup` wizard that:

1. Detects existing config or starts fresh
2. Walks through OAuth flow (or Private App token paste)
3. Probes capabilities (6.1) and reports what works
4. Warms the schema cache (9.4)
5. Reports total setup time and any scope gaps

For OAuth, a simple local listener (or copy-paste of the callback URL) handles the redirect.

**Effort.** Medium. OAuth flow is the bulk; everything else builds on existing components.

**Risk.** OAuth callback handling adds complexity. For headless environments (CI, remote), Private App tokens remain the simpler path.

**Verdict: Foundation.** Without this, "first run" is bumpy enough to lose users.

### 11.2 Capability detection report

After setup, present a clean readout:

> Connected to portal 1234567 (Professional, US datacenter).
> Capabilities: contacts ✓, companies ✓, deals ✓, tickets ✓, workflows ✓, lists ✓, pipelines ✓, users ✓, custom objects ✗ (Enterprise required), calculated properties ✓.
> Schema cached: 47 contact properties, 23 company properties, 12 deal properties, 8 ticket properties.
> Granted scopes: 14/16 needed. Missing: `automation.workflows.write` (you'll be unable to create workflows).

Sets expectations from the first interaction.

**Effort.** Small (depends on 6.1).

**Verdict: Foundation.**

### 11.3 Tour mode

**Failure mode.** A new user doesn't know what the agent can do. They might guess based on the docs but learn faster with examples.

**Sketch.** `/hubspot tour` cycles through 5-7 example requests with explanations: "Try `/hubspot how many contacts` — this is a read-only request that doesn't require approval. Now try `/hubspot create a contact named X` — see the preview and approval flow." Each example is opt-in.

**Effort.** Small.

**Verdict: Leverage** if you expect users beyond yourself; **Skip** if it's solo.

---

## 12. Testing & Quality

### 12.1 Property-based testing for tools

**Failure mode.** Existing tests cover specific cases. Edge cases in inputs (unicode property names, very long values, boundary numerics) aren't systematically tested.

**Sketch.** Add `hypothesis` to the dev dependencies. Generate random inputs for each tool and assert invariants (no crashes, error responses are well-formed, idempotent operations stay idempotent).

**Effort.** Small-to-medium.

**Verdict: Leverage.** Cheap and surfaces real bugs.

### 12.2 Prompt regression suite

**Failure mode.** Prompt changes (especially to routing or sub-agent behavior) can silently break correct routing or correct decisions. There's no test that confirms "request X still routes to agent Y after prompt changes."

**Sketch.** A YAML corpus of `(request, expected_route, expected_outcome)` cases. A test that runs each case and asserts the route/outcome matches. Run on every prompt change.

**Effort.** Medium. Building the corpus is the bulk of the work.

**Risk.** LLM responses are non-deterministic. Use temperature=0 and tolerate small variations.

**Verdict: Foundation** if 4.1 (LLM routing) ships; **Leverage** otherwise.

### 12.3 Chaos testing

**Failure mode.** The current tests assume the API responds. Real-world: rate limits, network failures, timeouts, partial responses. The agent should degrade gracefully.

**Sketch.** A test harness that wraps the HubSpot client and injects faults: 5% rate-limit responses, 1% network errors, 0.1% truncated responses. Run the existing test suite under chaos and verify the agent recovers correctly.

**Effort.** Medium.

**Verdict: Speculative.** High value but not until the system is otherwise stable.

---

## 13. Phased Roadmap

A defensible ordering:

**Phase A — Foundation hardening (next 4-6 weeks).** Action ledger (3.1), checkpointing (3.2), schema-aware validation (3.3), error category taxonomy (3.4), capability matrix (6.1), snapshot pruning (6.4), guided setup (11.1), capability report (11.2), background pre-fetch (9.4). Together these transform the agent from "demo" to "robust." Roughly 2-3 weeks of engineering effort, well-bounded.

**Phase B — Intelligence and UX (next 2-3 months).** LLM routing (4.1), self-correction loop (4.2), trace events (5.1), cost tracking (5.2), inline diff viewer (7.1), progress streaming (7.3), batch approval mode (7.4), prompt regression suite (12.2). Workflow blueprints (4.3) start here with 3-5 initial blueprints. PII redaction (6.3) if compliance applies. Property-based testing (12.1).

**Phase C — Domain expansion (next 6+ months).** Custom objects (8.1) if user demand exists. Multi-step DAG (4.4) and interactive plan modification (7.5) if request distribution justifies it. Replay tooling (5.3) and anomaly detection (5.4) once enough data accumulates. Plugin architecture (10.1) and custom routing (10.3) if there's a multi-user story. Marketing/service domains (8.2, 8.3) per demand.

**Defer indefinitely.** Sandbox-first (6.2), webhooks (8.4), batch coalescing (9.2), conversation memory (7.2), hooks (10.2), reflection/post-action review (4.5) outside high-risk subset. Real value but the case is contingent on usage patterns we cannot predict yet.

---

## 14. Recommended Top-Three Priorities

If only three items happen, my picks:

**1. Action ledger + checkpointing (3.1 + 3.2 together).** Together they upgrade the agent's failure mode from "silent partial state" to "explicit known state." Without this, every timeout or interruption produces an investigation. Estimated effort: 1 week.

**2. Schema-aware pre-validation (3.3).** Highest leverage of the reliability foundations. Catches the most common error class locally, makes self-correction effective, saves rate limit budget. Estimated effort: 1 week.

**3. LLM routing (4.1).** The keyword table will be the dominant maintenance burden after launch. Removing it before users find the gaps is much cheaper than patching after. Estimated effort: 1 week including the regression test corpus.

These three address the three most likely "production embarrassments": double-execution, opaque validation failures, and bad routing. Total effort ~3 weeks. Everything else can wait or be evaluated against actual usage data.

---

## 15. Open Questions

A few directions where I don't have a strong view and would defer to user input:

**Multi-user story.** Is this agent meant to be solo (Izzy plus your portals) or shared (a team using the same install)? The plugin architecture (10.1), conversation memory (7.2), PII redaction (6.3), role-based access (6.5), and tour mode (11.3) all hinge on this answer. Currently the design treats it as solo.

**Token economics.** LLM routing (4.1) and self-correction loops (4.2) both increase per-request token cost. Is there a budget ceiling we should design around, or is cost an acceptable trade for behavior quality?

**HubSpot API stability.** Several directions (workflow blueprints 4.3, custom object support 8.1) depend on HubSpot not changing the underlying APIs. What's the historical churn rate on these endpoints? If it's high, blueprints become a maintenance trap.

**Failure-mode tolerance.** Some users will accept "the agent occasionally gets routing wrong" as the cost of natural language. Others will treat any miss as broken. Which user is this built for?

**Compliance posture.** Will this run in environments where audit logs and traces have legal-retention or PII-redaction requirements? Affects whether 6.3 and 6.5 are foundation or skip.

**Sandbox availability.** Do users typically have a HubSpot sandbox portal? If yes, 6.2 becomes more attractive. If most users are single-portal, sandbox-first is mostly theoretical.

---

## 16. Decision Summary

| # | Direction | Verdict | Phase | Effort |
|---|-----------|---------|-------|--------|
| 3.1 | Action ledger | Foundation | A | Small |
| 3.2 | Mid-execution checkpointing | Foundation | A | Small-Med |
| 3.3 | Schema-aware pre-validation | Foundation | A | Medium |
| 3.4 | Error category taxonomy | Leverage | A | Tiny |
| 4.1 | LLM routing | Leverage | A/B | Medium |
| 4.2 | Self-correction loop | Leverage | B | Small |
| 4.3 | Workflow blueprint library | Leverage / Speculative | B | Med-Large |
| 4.4 | Multi-step DAG | Speculative | C | Med-Large |
| 4.5 | Reflection / post-action review | Leverage (high-risk only) | B | Small-Med |
| 5.1 | Structured trace events | Leverage | B | Small |
| 5.2 | Cost & latency tracking | Leverage | B | Small |
| 5.3 | Replay tooling | Speculative | C | Medium |
| 5.4 | Anomaly detection | Speculative | C | Medium |
| 6.1 | Portal capability matrix | Foundation | A | Small |
| 6.2 | Sandbox-first | Speculative | Defer | Large |
| 6.3 | PII redaction | Conditional | A or skip | Medium |
| 6.4 | Snapshot pruning + TTL | Foundation | A | Small |
| 6.5 | Role-based access | Conditional | C or skip | Medium |
| 7.1 | Inline diff viewer | Leverage | B | Small-Med |
| 7.2 | Conversation memory | Speculative | Defer | Medium |
| 7.3 | Progress streaming | Leverage | B | Small |
| 7.4 | Batch approval modes | Leverage / Speculative | B | Small-Med |
| 7.5 | Interactive plan modification | Speculative | C | Medium |
| 8.1 | Custom objects | Conditional | C | Medium |
| 8.2 | Marketing campaigns | Speculative | C | Large |
| 8.3 | Service hub | Speculative | C | Medium |
| 8.4 | Webhooks | Speculative | Defer | Large |
| 8.5 | CMS / files / social | Skip | — | — |
| 8.6 | Reporting & dashboards | Speculative | C | Medium |
| 9.1 | Query-result cache | Conditional | B | Small |
| 9.2 | Batch coalescing | Speculative | Defer | Medium |
| 9.3 | Parallel sub-agents | Leverage (read-only) | B | Small |
| 9.4 | Background pre-fetch | Leverage | A | Small |
| 10.1 | Plugin architecture | Speculative | C | Medium |
| 10.2 | Hook system | Speculative | Defer | Medium |
| 10.3 | Custom routing rules | Speculative | C | Small |
| 11.1 | Guided setup | Foundation | A | Medium |
| 11.2 | Capability report | Foundation | A | Small |
| 11.3 | Tour mode | Conditional | B | Small |
| 12.1 | Property-based testing | Leverage | B | Small-Med |
| 12.2 | Prompt regression suite | Foundation (if 4.1) | B | Medium |
| 12.3 | Chaos testing | Speculative | C | Medium |

---

## 17. Closing Thoughts

The current design is solid as a starting point. The three-week investment in Phase A items (action ledger, checkpointing, schema-aware validation, LLM routing) is what separates a demo from a tool you'd actually deploy. Phase B is where the agent becomes pleasant to use; Phase C is where it grows into adjacent domains.

A few patterns worth flagging across the document:

**Cheap observability beats expensive prevention.** Many of the high-leverage items (3.1, 3.2, 5.1, 5.2) are about knowing what happened, not preventing failures. This is correct: in an LLM-driven system, you cannot prevent every bad outcome; you can make sure you can investigate and recover from any of them.

**Prompts are infrastructure now.** Several items (4.1, 4.2, 4.3) move logic from Python code into LLM prompts. This works only if prompt regressions can be caught (12.2). Treat prompt files like production code: version-controlled, tested, reviewed.

**Defer architecture until you have data.** The DAG planner (4.4), conversation memory (7.2), and anomaly detection (5.4) are real ideas, but their value depends on the actual distribution of user requests. Ship the simpler version, watch how it's used, then build the layer that demonstrably solves a real problem rather than the one that sounded good in advance.

**The boundary of "agent" matters less than you think.** Several directions (webhooks 8.4, marketing 8.2, plugins 10.1) push the agent toward becoming a general HubSpot platform. That is a different product than an admin assistant. Be deliberate about whether you're building one or the other.
