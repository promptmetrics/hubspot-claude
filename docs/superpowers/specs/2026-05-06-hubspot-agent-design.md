# Design: HubSpot CRM Admin Agent (Claude Code Sub-Agents)

**Date:** 2026-05-06
**Author:** Claude Code / User Collaboration
**Status:** Draft — awaiting final review

---

## 1. Problem Statement

HubSpot administration is fragmented, time-consuming, and error-prone. A single request like "reorganize our deal properties and build a follow-up workflow" requires navigating dozens of screens, understanding object schemas, and manually translating business logic into HubSpot's native automation language. There is no persistent, conversational layer that lets an administrator simply describe intent and delegate execution.

## 2. Proposed Solution

A Claude Code skill (`/hubspot`) that acts as a persistent HubSpot admin assistant using Claude Code's native sub-agent system. Users interact via natural language chat within Claude Code. The parent session routes requests to specialized domain sub-agents, each running in isolation with focused tools and prompts. Results are synthesized back into the main conversation.

**Key characteristics:**
- Runs entirely inside Claude Code — no standalone CLI app
- Natural language input, structured output (markdown tables, diffs, previews)
- Inline HITL approval for all write operations
- Persistent conversation context across requests
- Multi-portal support with isolated state

## 3. Architecture Overview

```
User (Claude Code session)
    |
    v
/hubspot "find duplicate contacts and merge them"
    |
    v
Parent Orchestrator (routing heuristic)
    |
    +---> HygieneAgent (find duplicates)
    |        |
    |        v
    |    Returns: list of 12 duplicate pairs
    |
    +---> HygieneAgent (merge contacts)
             |
             v
    Returns: merged records + preview
             |
             v
Parent: "Found 12 duplicates. Merge all? (y/n/review)"
    |
    v
User: "y"
    |
    v
Parent re-dispatches HygieneAgent (execute mode)
    |
    v
Results presented inline
```

**Parent Orchestrator responsibilities:**
- Receive natural language request
- Route to one or more Domain Sub-Agents via the `Agent` tool
- Collect and synthesize sub-agent results
- Present previews and approval prompts inline
- Track cross-domain context across the conversation

**Why Claude Code sub-agents:**
- No custom orchestration framework needed
- Isolation via worktrees/background execution
- Parallelism built-in
- Result collection and synthesis handled natively

## 4. Sub-Agent Definitions (11 Agents)

| # | Sub-Agent | Domain | Responsibilities |
|---|---|---|---|
| 1 | **ObjectsAgent** | Core CRUD | Read/search/create/update/delete contacts, companies, deals, tickets. Batch operations. |
| 2 | **PropertiesAgent** | Schema | Create/update custom properties, manage property groups, validate property types. |
| 3 | **WorkflowsAgent** | Automation | Create/update workflows, manage enrollment triggers, set actions, toggle status. |
| 4 | **ListsAgent** | Segmentation | Create static/dynamic lists, add/remove members, filter-based list building. |
| 5 | **PipelinesAgent** | Pipelines | Manage deal/ticket pipeline stages, reorder stages, create custom pipelines. |
| 6 | **UsersAgent** | Permissions | Onboard users, assign roles, manage teams, deactivate accounts. |
| 7 | **HygieneAgent** | Data Quality | Find duplicates, merge records, bulk update, standardize field values. |
| 8 | **AnalyticsAgent** | Reporting | Fetch reports, summarize metrics, calculate conversion rates, pipeline velocity. |
| 9 | **AssociationsAgent** | Relationships | Create/update association schemas, associate/disassociate records across objects. |
| 10 | **EngagementsAgent** | Activity | Get, search, create notes, tasks, emails, meetings, calls. |
| 11 | **RawAPIAgent** | Escape-hatch | Direct HubSpot API calls for endpoints not covered by the 10 specialist agents. Power-user fallback.

**Design principle:** Each agent receives a focused subset of tools and a domain-specific system prompt. No agent has access to tools outside its domain.

## 5. Routing & Intent Parsing

The parent orchestrator uses **keyword + scope heuristics** for routing. No custom LLM classifier needed for MVP.

**Routing rules:**

| Keywords in request | Primary Agent(s) |
|---|---|
| "contact," "company," "deal," "ticket," "record" | ObjectsAgent |
| "property," "field," "schema," "custom field" | PropertiesAgent |
| "workflow," "automation," "enroll," "trigger" | WorkflowsAgent |
| "list," "segment," "add to list" | ListsAgent |
| "pipeline," "stage," "move to" | PipelinesAgent |
| "user," "permission," "team," "owner," "onboard" | UsersAgent |
| "duplicate," "merge," "dedup," "clean" | HygieneAgent |
| "report," "metric," "analytics," "how many" | AnalyticsAgent |
| "associate," "link," "relationship," "related to" | AssociationsAgent |
| "note," "task," "email," "meeting," "call," "activity," "log" | EngagementsAgent |
| "raw api," "custom endpoint," "direct api," "not covered," "escape hatch" | RawAPIAgent |

**Multi-agent dispatch:**
- Sequential: when agents have dependencies (e.g., create property, then build workflow using it)
- Parallel: when agents are independent (e.g., find unassigned deals + create tasks)

**Dependency detection (MVP):**
For compound requests, the parent uses simple conjunction detection:
- If request contains "and then," "after that," or sequential phrasing → dispatch sequentially
- If request contains "and" linking two distinct domains → dispatch in dependency order based on a static graph:
  - PropertiesAgent → WorkflowsAgent (workflows reference properties)
  - ObjectsAgent → ListsAgent (lists reference object filters)
  - ObjectsAgent → EngagementsAgent (engagements reference objects)
- If dependency is unclear, parent asks: "Should I do X first, then Y?"

**User override:** If routing is ambiguous, the parent asks for clarification before dispatching.

## 6. Tools & HubSpot API Integration

Tools are async Python functions with a `@tool` decorator, invoked directly by sub-agents.

**Tool inventory per agent:**

| Agent | Tool Names |
|---|---|
| ObjectsAgent | `hubspot_get_object`, `hubspot_search_objects`, `hubspot_create_object`, `hubspot_update_object`, `hubspot_delete_object`, `hubspot_batch_upsert_objects` |
| PropertiesAgent | `hubspot_get_property`, `hubspot_list_properties`, `hubspot_create_property`, `hubspot_update_property`, `hubspot_delete_property` |
| WorkflowsAgent | `hubspot_get_workflow`, `hubspot_list_workflows`, `hubspot_create_workflow`, `hubspot_update_workflow`, `hubspot_enroll_workflow`, `hubspot_toggle_workflow` |
| ListsAgent | `hubspot_get_list`, `hubspot_list_lists`, `hubspot_create_list`, `hubspot_update_list`, `hubspot_add_to_list`, `hubspot_remove_from_list` |
| PipelinesAgent | `hubspot_get_pipeline`, `hubspot_list_pipelines`, `hubspot_create_pipeline`, `hubspot_update_pipeline`, `hubspot_reorder_stages` |
| UsersAgent | `hubspot_get_user`, `hubspot_list_users`, `hubspot_create_user`, `hubspot_update_user`, `hubspot_deactivate_user` |
| HygieneAgent | `hubspot_find_duplicates`, `hubspot_merge_objects`, `hubspot_bulk_update_objects`, `hubspot_preview_segment` |
| AnalyticsAgent | `hubspot_get_report` (fetches raw report data from HubSpot), `hubspot_calculate_metrics` (client-side computation over fetched data: conversion rates, averages), `hubspot_pipeline_velocity` (client-side calculation: days between stage transitions) |
| AssociationsAgent | `hubspot_get_association_schema`, `hubspot_create_association_schema`, `hubspot_associate_records`, `hubspot_disassociate_records` |
| EngagementsAgent | `hubspot_get_engagement`, `hubspot_search_engagements`, `hubspot_create_note`, `hubspot_create_task`, `hubspot_create_email`, `hubspot_create_meeting`, `hubspot_create_call` |
| **RawAPIAgent** | `hubspot_raw_api` |

**Shared infrastructure:**
- `HubSpotClient` — async HTTP client with OAuth/private app auth, rate limit handling, retry logic
- Portal context (portal_id, tier, granted_scopes) injected into each tool call
- Response normalization — every tool returns a consistent `dict` with standard fields

**Batch operation result format:**
All batch/bulk tools return a structured result supporting partial success:
```json
{
  "succeeded": 42,
  "failed": 3,
  "total": 45,
  "results": [...],
  "errors": [
    {"index": 7, "object_id": "123", "message": "Invalid email format", "category": "VALIDATION"}
  ]
}
```

## 7. State Management & Session Persistence

**Two-tier state model:**

1. **Claude Code conversation context** — the chat history is the primary state store. Sub-agent results are appended as messages. The parent references prior results when building subsequent prompts. There is no persistent in-memory daemon; state survives only as long as the Claude Code session.
2. **Per-portal disk cache** — schema metadata, undo snapshots, and audit logs stored on disk at `.claude/hubspot/<portal_id>/`. These survive across Claude Code sessions.

**Cached per portal:**
- Object schemas (properties per object type)
- Pipeline definitions and stage IDs
- Workflow IDs and names
- List IDs and member counts
- User/team mappings

**Cache invalidation:**
- Explicit: `/hubspot refresh` flushes all caches
- Implicit: 1-hour TTL, auto-refresh on stale reads
- After writes: cache invalidated for affected domain

**Multi-portal support:**
- **Auto-detection:** If a `.hubspot-portal` file exists in the working directory, the skill reads `portal_id` from it and uses it as the default portal on first `/hubspot` invocation. Format: a single line with the portal ID (e.g., `1234567`)
- `/hubspot portal switch <portal_id>` switches active portal
- `/hubspot portal list` shows all configured portals
- Each portal gets its own cache directory and isolated token
- Current portal displayed in every `/hubspot` response header: `📍 Portal: 1234567 (Professional)`
- Switching portals does not clear conversation history, but pending approvals for the previous portal are abandoned (user must re-request)
- Schema cache warms on first use per portal, not at switch time

## 8. Error Handling & Resilience

**Sub-agent failure modes:**

| Scenario | Parent behavior |
|---|---|
| Sub-agent returns error object | Display error + offer retry or alternative |
| Tool call fails (API error) | Receive structured error with `tool_name`, `error_message`, `retryable` flag |
| Rate limit hit | Pause, show retry time, auto-retry with backoff |
| Scope/permission denied | Explain needed scopes, offer reduced-scope alternative |
| Sub-agent times out | Parent stops waiting, reports timeout, suggests breaking request into chunks. Sub-agent runs in isolation; parent cannot force-terminate but abandons the result after timeout. |
| Ambiguous routing | Ask user for clarification before dispatching |

**Retry strategy:**
- Tool-level: 3 retries with exponential backoff (inside `HubSpotClient`)
- Agent-level: up to 2 re-dispatches with modified prompts
- Hard limit: max 3 retries per request at any level

**Write-timeout safety:**
Since sub-agents cannot be force-terminated, write operations use these mitigations:
- All writes are dispatched with a **mandatory chunk size cap** (max 100 records per batch for bulk operations)
- **Idempotency:** Where HubSpot supports it, batch requests include idempotency keys to prevent double-execution on retry
- **Post-timeout reconciliation:** After a timeout, parent dispatches a `HygieneAgent` reconciliation check to verify what was applied vs. what was expected
- **Small-batch default:** Destructive operations default to chunk size 10, requiring more approvals but limiting blast radius

**Graceful degradation:**
- Missing Enterprise scopes → fall back to Professional/Starter equivalents
- Batch exceeds API limits → auto-chunk
- Missing write scopes → switch to preview mode (show what *would* be done)

## 9. Human-in-the-Loop (HITL) Approval

**Approval triggers by risk level:**

| Risk Level | Trigger |
|---|---|
| Read-only | No approval needed |
| Create | Preview shown, user confirms with `y` or `approve` |
| Update (single record) | Inline diff shown, user confirms |
| Update (bulk > 10 records) | Full plan preview with estimated impact, explicit confirmation required |
| Delete / Merge / Archive | **Destructive gate** — user must type the exact count of affected records to confirm |

**Approval flow:**
1. For writes, sub-agent first performs a **read-based preview** (e.g., search to identify affected records, fetch current values for diff) — NOT an API dry-run, since HubSpot does not support dry-run for most write operations
2. Sub-agent returns structured result with `preview`, `impact_count`, `rollback_steps`, `risk_level`, `proposed_payload` (the exact parameters that would be sent to the write API), and `original_values` (a snapshot of current field values for affected records, used for undo)
3. Parent presents preview in markdown with `Approve? (y/n/details)`
4. On approval, parent stores `proposed_payload` in the conversation context (or a short-lived temp file referenced in the prompt)
5. Parent re-dispatches the same sub-agent with the payload embedded in the prompt: `execute the following payload: {...}`
6. Sub-agent executes the write using the provided payload, returns results
7. Results presented with undo option (if available)

**State passing between preview and execute:**
Since sub-agents are stateless, the parent passes the full execution context explicitly:
- For simple requests: include the payload directly in the re-dispatch prompt
- For complex/batch requests: write payload to a temp JSON file, pass the file path in the prompt, sub-agent reads it via `Read` tool
- Parent retains the original values (for undo) in conversation context or a `.claude/hubspot/<portal_id>/undo_snapshots/` directory

**Undo support:**
- Updates: parent stores original values in `.claude/hubspot/<portal_id>/undo_snapshots/<action_id>.json` before approving. Undo = re-dispatch with original values.
- Creates: delete created records via sub-agent
- Deletes: **not undoable** — HubSpot API has no restore; explicit warning required. No snapshot is taken for deletions.
- `rollback_steps` from the preview result is stored alongside the snapshot as human-readable context (not machine-executable), displayed to the user when they request undo.

**Destructive gate detail view:**
When user types `details` instead of `y` at a destructive gate, the parent re-dispatches the sub-agent with `mode=details` to show:
- Full list of affected record IDs and names
- Confirmation that backups/archives (if any) have been advised
- Exact API calls that will be made

## 10. Security & Auth

**Authentication:**
- HubSpot OAuth 2.0 or Private App token
- Token stored in Claude Code secure credential storage
- Token never logged or displayed in output
- Per-portal token isolation

**Scope validation:**
- Parent checks granted scopes against required tool scopes before dispatch
- Missing scopes = proactive gate with exact scope list
- No "try and fail" approach

**Tool-to-scope mapping (excerpt):**

| Tool Prefix | Required HubSpot Scope |
|---|---|
| `hubspot_get_*`, `hubspot_search_*`, `hubspot_list_*` | `crm.objects.{type}.read` |
| `hubspot_create_object`, `hubspot_update_object` | `crm.objects.{type}.write` |
| `hubspot_delete_object` | `crm.objects.{type}.write` + `crm.objects.{type}.delete` |
| `hubspot_*_property` | `crm.schemas.{type}.write` |
| `hubspot_*_workflow` | `automation.workflows.write` |
| `hubspot_*_list` | `crm.lists.write` |
| `hubspot_*_pipeline` | `crm.pipelines.write` |
| `hubspot_*_user` | `settings.users.write` |
| `hubspot_associate_*` | `crm.objects.{type}.write` |
| `hubspot_*_engagement` | `crm.objects.engagements.write` |

(Complete mapping maintained in the tool registry metadata, not hardcoded in the spec.)

**Data safety:**
- Sub-agents don't persist raw HubSpot data to disk (except schema metadata)
- No PII in traces or logs
- Rate limit enforcement: `HubSpotClient` maintains a shared async semaphore that enforces HubSpot's actual limits — 100 requests per 10 seconds for standard endpoints, 4 concurrent batch operations max. Limits are tracked globally across all tools in the active session, not per-tool.

**Audit trail:**
- Every approved write logged to `.claude/hubspot/<portal_id>/audit.log`
- Fields: timestamp, user, action, sub-agent, result summary
- Local only — no external transmission

## 11. Testing & Validation Strategy

**Integration testing against HubSpot:**
- All tests run against a HubSpot **developer test portal** (free, full API access)
- No mocking of HubSpot API responses — mock only the LLM/sub-agent layer if needed
- VCR.py or similar for recording/replaying API interactions in CI
- Each sub-agent has its own test suite covering happy path + primary error modes

**Sub-agent isolation testing:**
- Spawn each sub-agent via the `Agent` tool in tests, verify it returns expected structured output
- Test timeout handling by dispatching with very short timeouts
- Test scope validation by running against a portal with restricted scopes

**HITL flow testing:**
- Simulate approval/rejection/details paths using test harnesses
- Verify that proposed payloads match executed payloads exactly

**Rate limit testing:**
- Stress tests with batch operations > 1000 records to verify chunking and rate-limit respect

## 12. Success Criteria

1. User can say "how many contacts in the northeast" and get an answer within 10 seconds
2. User can say "create a custom deal property called Renewal Date and build a workflow that alerts the owner 30 days before" and the system executes with HITL approval
3. All write operations show a preview before execution
4. Destructive operations require explicit count-based confirmation
5. Multi-portal switching works without losing conversation context
6. Rate limits are respected without manual intervention
7. Missing scopes are detected proactively, not via API failures

## 13. Out of Scope (MVP)

- Custom object support (future phase)
- HubSpot CMS/file manager tools
- Multi-step workflow building with complex branching logic
- Real-time sync / webhook listening
- External dashboard or UI
- Team collaboration / shared sessions
- Undo for deletions (HubSpot API limitation)

## 14. Decisions & Open Questions

**Decisions made:**
1. **Auth:** OAuth 2.0 and Private App tokens only. No API key support (deprecated by HubSpot).
2. **Pagination:** Standard HubSpot pagination (100 records per page) with automatic iteration for previews. For portals with 100k+ records, previews are capped at 1000 records with a warning: "Preview shows first 1000 records. Full operation will affect all matching records."
3. **Routing:** Keyword heuristics for MVP. LLM-based routing considered for Phase 2 if heuristics prove insufficient.
4. **agent2 reuse:** Reuse `HubSpotClient` and individual tool implementations from `agent2` where they are clean and well-tested. Replace the custom orchestration layer (LangGraph, coordinator, routing) entirely with Claude Code sub-agents.
5. **Fallback for failing sub-agents:** After 2 retries, parent surfaces the error to the user with options: (a) rephrase request, (b) break into smaller steps, (c) manually execute via raw API tool.

**Resolved questions:**
1. **Raw API escape-hatch:** Yes — added as RawAPIAgent with `hubspot_raw_api` tool. Triggered by keywords "raw api," "custom endpoint," "direct api." Available as fallback when no specialist agent matches, and explicitly for power users who need uncovered endpoints.
2. **Portal auto-detection:** Yes — the skill auto-detects the portal from a `.hubspot-portal` file in the working directory on first invocation. Format is a single line with the portal ID.

**Remaining open questions:**
1. None — all open questions from Round 1 are now resolved.
