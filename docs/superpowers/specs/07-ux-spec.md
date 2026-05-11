# HubSpot Admin Agent — UX Specification (As Built)

**Version:** 1.0 — As-Built  
**Date:** 2026-05-10  
**Scope:** Describes the user-facing behavior of the HubSpot Admin Agent implementation as it exists today. Honest about gaps.

---

## 1. Information Architecture

### 1.1 Command Structure

The agent is invoked through a single CLI prefix (`/hubspot`) within a Claude Code session. There is no standalone GUI, web dashboard, or mobile interface.

```
/hubspot <natural-language-request>        [Main entry point]
/hubspot setup <portal_id> oauth           [OAuth credential setup]
/hubspot setup <portal_id> token <pat>     [Private App token setup]
/hubspot portal auth <portal_id>           [Browser OAuth flow]
/hubspot portal switch <portal_id>         [Change active portal]
/hubspot portal list                       [List configured portals]
/hubspot status                            [Last 24h stats]
/hubspot refresh                           [Flush caches]
/hubspot tour                              [Interactive walkthrough]
```

**Hierarchy:** All commands are flat under `/hubspot`. There is no nested sub-command menu. Natural-language requests are dispatched via keyword heuristics or LLM routing rather than explicit command trees.

**Auto-detection:** If a `.hubspot-portal` file exists in the working directory, its contents (a single portal ID) are used as the default portal for all subsequent `/hubspot` commands. This removes the need to type the portal ID repeatedly.

### 1.2 Agent Taxonomy (What the User Can Ask For)

The user does not type agent names directly. The system maps natural language to one of 15 specialist agents:

| Agent | User-facing keywords | What the user sees |
|---|---|---|
| Objects | contact, company, deal, ticket, record | Search results, record lists, inline diffs |
| Properties | property, field, schema, custom field | Schema previews, validation errors |
| Workflows | workflow, automation, enroll, trigger | Blueprint summaries, enrollment status |
| Lists | list, segment, add to list | Member counts, list definitions |
| Pipelines | pipeline, stage, move to | Stage tables, reorder previews |
| Users | user, permission, team, owner, onboard | User cards, role assignments |
| Hygiene | duplicate, merge, dedup, clean | Duplicate pairs, merge previews |
| Analytics | report, metric, analytics, how many | Calculated numbers, conversion rates |
| Associations | associate, link, relationship | Link tables, association types |
| Engagements | note, task, email, meeting, call, activity | Activity timelines, task cards |
| Raw API | raw api, custom endpoint, direct api | Raw JSON request/response |
| Custom Objects | custom object schema, custom record | Schema definitions, record lists |
| Service | ticket, knowledge base, survey, feedback | Ticket summaries, KB article lists |
| Marketing | campaign, email, ab test, suppression list | Campaign stats, email performance |
| CMS | page, blog, file, social | Page lists, file manager entries |

**Note:** The approved spec defined 11 agents. The implementation ships 15. `custom_objects`, `service`, `marketing`, and `cms` were explicitly listed as out of scope in the MVP spec.

---

## 2. User Flows

### 2.1 Setup Flow

**Goal:** Connect the agent to a live HubSpot portal.

**Path A — Private App Token (fastest, ~5-10 min for technical users)**

1. User creates a Private App in HubSpot Settings > Integrations > Private Apps.
2. User grants scopes (minimum: `crm.objects.contacts.read/write`, `crm.schemas.deals.read`, `automation`).
3. User copies the token (`pat-na1-...`).
4. User types: `/hubspot setup <portal_id> token <pat>`
5. System writes portal config to `~/.claude/hubspot/<portal_id>.json`.
6. System creates `.hubspot-portal` file in working directory.
7. System runs capability probe (7 sequential HTTP calls to HubSpot) and schema cache warm.
8. System reports scope gaps if any.
9. User verifies with `/hubspot status`.

**Path B — OAuth 2.0 (team setup, ~20+ min)**

1. User creates a public app in the HubSpot Developer Portal.
2. User notes App ID, Client ID, Client Secret.
3. User runs a Python snippet to save app credentials to `~/.claude/hubspot/app_credentials.json`.
4. User types: `/hubspot setup <portal_id> oauth`
5. System constructs an authorization URL and opens the browser.
6. User logs into HubSpot, authorizes the app.
7. Callback lands at `http://localhost:3000/oauth/callback`.
8. System exchanges code for access/refresh token and stores them.
9. System runs capability probe and schema cache warm.
10. User verifies with `/hubspot status`.

**UX Reality:** The setup wizard detects existing config vs. fresh starts, but it does **not** provide step-by-step interactive guidance during the HubSpot-side configuration. Users follow the User Manual or figure it out themselves. OAuth is a significant barrier for non-engineers.

**Gap:** No inline help during token creation. No video. No click-by-click guide embedded in the CLI.

---

### 2.2 Read Query Flow

**Goal:** Get information from HubSpot without changing anything.

**Trigger:** Any request containing keywords mapped to read agents (e.g., "find all contacts in the northeast", "how many deals closed last month").

**Flow:**
1. User types the natural-language request.
2. System detects default portal from `.hubspot-portal` or errors if missing.
3. System validates portal config and token.
4. System routes the request to one or more agents via keyword fast-path or LLM routing.
5. System checks scopes and capabilities proactively. If missing, returns an exact list of required scopes before any API call.
6. System dispatches agents in parallel (read-only is safe to parallelize).
7. Agents return structured data.
8. System presents results as markdown tables, bullet lists, or inline summaries.
9. Read results are cached for 5 minutes in an LRU query cache.

**Example transcript:**

```
User: /hubspot show me deals closing this quarter

📍 Portal: 1234567 (Professional)
**Routing to:** objects

### objects
Found 24 deals with forecast_close_date in Q2 2026:

| Deal Name | Amount | Stage | Owner |
|-----------|--------|-------|-------|
| Acme Renewal | $50,000 | Negotiation | Dana Smith |
| Beta Corp Expansion | $120,000 | Demo | Bob Jones |
...
```

**Gap:** If routing is ambiguous, the system asks for clarification. However, the LLM routing prompt is static text; there is no confidence score displayed to the user, and no "Did you mean...?" suggestion list.

---

### 2.3 Write with Approval Flow (Intended Design vs. Actual)

**Intended Design:**
1. Agent runs in preview mode — performs read-based preview (search affected records, fetch current values).
2. System renders preview: impact count, inline diff, rollback info.
3. User sees approval prompt: `Approve? (y/n/details)`
4. User types `y`.
5. System saves undo snapshot.
6. System re-dispatches agent in execute mode with the proposed payload embedded.
7. Agent executes the write.
8. Results presented with undo option.

**Actual Implementation:**
1-2 work in code: `dispatch_agent` with `mode="preview"` builds a prompt containing the system prompt, user request, and mode. `present_preview` exists and formats nice markdown.
3-8 **do not work end-to-end in the CLI.**

**Specific gap in `cli.py`:**
- `hubspot_command()` calls `dispatch_agents_parallel(..., mode="preview")`.
- It extracts a one-line snippet from the agent result and appends it to the output.
- It **never** calls `present_preview()`.
- It **never** pauses for user approval.
- It **never** re-dispatches with `mode="execute"`.
- The `AgentResult` contains a `full_prompt` string meant for an LLM, not a human-readable preview.

**What the user actually sees for a write:**

```
User: /hubspot update contact 12345, set lifecyclestage to customer

📍 Portal: 1234567 (Professional)
**Routing to:** objects

### objects
 update contact 12345, set lifecyclestage to customer
```

The user sees the raw request echoed back, not a diff or approval gate. No write occurs because execute mode is never triggered.

**Severity:** Blocker. The core safety mechanism (mandatory HITL approval) is architected but not wired to the CLI entry point.

---

### 2.4 Bulk Update Flow (Intended Design vs. Actual)

**Intended Design:**
1. User requests a bulk update (e.g., "update all contacts where region is west, set timezone to PST").
2. System detects >10 affected records.
3. System renders a full plan preview: affected count, before/after samples, API calls intended.
4. User confirms once for the entire batch.
5. System executes in chunks with progress streaming.

**Batch Approval Modes:**
- **Default (`--batch` absent):** Approve each write individually.
- **`--batch`:** Approve the full plan once up front.
- **`--pattern`:** Approve a sample of 3 records; auto-execute the rest if the sample is approved.

**Actual Implementation:**
- `parse_batch_mode()` correctly extracts `--batch` and `--pattern` from the request text.
- `dispatch_agent()` embeds the batch mode into the prompt sent to the sub-agent.
- However, because the CLI never transitions from preview to execute, no bulk operation ever completes.
- Progress streaming code exists (`progress.py`) but is unreachable from the CLI.

**What the user would see if wired up:**

```
📍 Portal: 1234567 (Professional)
**Routing to:** objects

### Proposed Change (HIGH)
- **Impact:** 847 records
- **Preview:**
  - action: batch_update_contacts
  - affected_records: 847
  - filter: region = west
  - set_fields: timezone = PST

**Batch mode:** Approve this full plan once to execute all steps.
Approve entire plan? (y/n)
```

**Gap:** The plan preview UI is implemented in `present_preview()` but never invoked by `cli.py`. The progress streaming UI ("Chunk 4 of 100 complete...") is implemented but never shown.

---

### 2.5 Compound Request Flow (Intended Design vs. Actual)

**Intended Design (per spec):** Simple conjunction detection — if the request contains "and then" or links two domains, dispatch sequentially or in dependency order.

**Actual Implementation:**
- A full DAG planner (`plan.py`, 931 lines) replaces the simple conjunction detection.
- The planner splits sentences with regex, infers agents and actions, extracts inputs/outputs, builds a dependency graph, performs topological sorting, and coalesces serial writes.
- `cli.py` does **not** invoke the DAG planner at all. Compound requests are routed as a single string to a single agent (or parallel agents if routing returns multiple).

**What the user actually sees:**
- A compound request like "find unassigned deals and create follow-up tasks for each" is routed to one or more agents, but each agent receives the full request text. There is no decomposition into sequential steps visible to the user.

**Gap:** The DAG planner is well-engineered but over-engineered for MVP, and it is not wired into the CLI. It sits dead in the codebase.

---

### 2.6 Error Recovery Flow

**Scope Validation (Working Well):**
- Before dispatch, the system checks required HubSpot scopes against granted scopes.
- If scopes are missing, the user sees an exact list: `objects requires scopes: crm.objects.contacts.write, crm.schemas.contacts.write`.
- No "try and fail" approach. This is a genuine UX win.

**Rate Limiting (Working):**
- `HubSpotClient` implements exponential backoff and retry.
- If 429s persist, the user sees a message suggesting spreading operations or using `--batch`.

**Timeout Recovery (Partial):**
- If a sub-agent times out, the parent reports timeout and suggests breaking the request into chunks.
- Post-timeout reconciliation exists in design (`HygieneAgent` reconciliation check) but is not wired into the CLI flow.

**Graceful Degradation (Working):**
- Missing Enterprise scopes fall back to Professional/Starter equivalents where possible.
- Batch operations auto-chunk if they exceed API limits.

**Missing Scope Explanation (Working Well):**
- Proactive scope validation lists exactly which scopes are missing and which agent needs them.
- Common forgotten scopes (`automation`, `crm.schemas.deals.read`) are documented in the troubleshooting section.

---

## 3. Interaction Patterns

### 3.1 Approval Prompts

The approval prompt framework is implemented in `present_preview()` but not displayed by the CLI. The intended patterns are:

**Create (Low-Medium Risk):**
```
### Proposed Change (MEDIUM)
- **Impact:** 1 records
- **Preview:**
  - action: create_contact
  - properties: name=Dana Smith, email=dana@example.com

Approve? (y/n/details)
```

**Update Single (Medium Risk):**
```
### Proposed Change (MEDIUM)
- **Impact:** 1 records
- **Diff:**
  - email: old@example.com → alice@example.com
  - lifecyclestage: lead → customer

Approve? (y/n/details)
```

**Update Bulk (High Risk):**
```
### Proposed Change (HIGH)
- **Impact:** 847 records
- **Preview:**
  - action: batch_update_contacts
  - sample (first 10 shown in detail, rest aggregated)

**Batch mode:** Approve this full plan once to execute all steps.
Approve entire plan? (y/n)
```

**Destructive (Delete/Merge/Archive):**
```
### Proposed Change (DESTRUCTIVE)
- **Impact:** 12 records
- **Preview:**
  - action: merge_contacts
  - affected: 12 duplicate pairs

**Destructive action.** Type `12` to confirm, or `details` for full record list.
```

**Gap:** None of the above prompts are ever shown to the user in the current CLI.

### 3.2 Diff Viewer

The diff viewer (`preview.py::format_preview`) exists and supports:
- Inline field-by-field diff (old → new) for single-record updates.
- Summary diff for bulk (first 10 in detail, remainder aggregated by count).
- DAG plan table for compound requests (if the DAG planner were wired).

It is designed to render as markdown. It is not invoked by the CLI.

### 3.3 Progress Indicators

For long bulk operations, the intended progress format is:

```
Chunk 4 of 100 complete (400/10000). Estimated 8 min remaining.
```

The progress tracking module (`progress.py`) and checkpointing (`checkpoint.py`) exist. They are not reachable from the CLI.

### 3.4 Session Memory

**Working:**
- Periodic summaries are persisted to `~/.claude/hubspot/<portal_id>/sessions/<session_id>.json`.
- On new session start, the most recent summary is loaded as context.
- Includes agents used and custom objects discovered.

**UX Impact:** Follow-up requests start with relevant context already loaded, reducing the need to re-explain the portal setup.

### 3.5 Query Cache

**Working:**
- Read results cached for 5 minutes.
- Auto-invalidated on writes to the same domain.
- Manual flush via `/hubspot refresh`.

**UX Impact:** Repeating the same read twice in a row returns instantly.

---

## 4. Key Screens / Transcripts

### 4.1 Setup Complete (Private App Token)

```
User: /hubspot setup 1234567 token pat-na1-abc123

✅ Portal 1234567 configured with Private App token.
Warming schema cache... done.
Probed capabilities: 14/18 scopes granted.
Missing scopes: automation.workflows.write, settings.users.write

Some features are unavailable. Run `/hubspot status` for details.
```

### 4.2 Status Dashboard

```
User: /hubspot status

📍 Portal: 1234567 (Professional)

**Last 24 Hours**
- Requests: 142
- Avg latency: 340 ms
- Error rate: 2.1%
- Est. cost: $0.0042
- Tool calls:
  - hubspot_search_objects: 89
  - hubspot_get_object: 34
  - hubspot_create_object: 12
```

### 4.3 Tour Mode

**Trigger:** `/hubspot tour`

**Blocker:** The tour is blocked if no portal is configured. It returns:
```
No default portal found. Create a `.hubspot-portal` file...
```

**If portal is configured:** The tour renders 7 static markdown steps simulating read queries, write previews, and approval flows. None of the steps make live API calls. They are hardcoded demonstrations.

**Example tour step:**
```markdown
## 3. Write preview — Update a contact
**Request:** `update contact 123 email to alice@example.com`

**Routed to:** objects
Write operations generate a preview with impact count and rollback info.

**Preview:**
### Proposed Change (MEDIUM)
- **Impact:** 1 records
- **Preview:**
  - action: update contact 123 email to alice@example.com
  - affected_records: 1

Approve? (y/n/details)
```

**Gap:** The tour is static text, not an interactive walkthrough where the user actually types `y` or `n`. It cannot run without a portal, which means first-time users — the people who need the tour most — cannot use it.

### 4.4 Sandbox Preview (Intended)

**Trigger:** High-risk bulk updates, merges, pipeline changes.

**Flow:**
1. System detects high risk.
2. System offers sandbox preview if `HUBSPOT_SANDBOX_PORTAL_ID` env var is set.
3. User approves sandbox run.
4. System replicates change on sandbox portal.
5. System reports behavior diff.
6. User approves production execution.

**Gap:** The sandbox env var is never documented in the Quick Start or User Manual. The sandbox module exists but is not wired into the CLI approval flow.

### 4.5 Webhook Listener (Background)

**Not user-facing in normal CLI usage.** The webhook server (`webhooks.py`) is a long-running aiohttp process that:
1. Validates `X-HubSpot-Signature` headers (v3 signature validation implemented).
2. Routes events to agents via a static mapping table.
3. Writes events to the trace log.

**UX Impact:** If deployed, this enables reactive automation (e.g., "when a contact is created, do X"). There is no CLI command to start/stop the listener; it is an internal deployment concern.

---

## 5. Accessibility Considerations

### 5.1 Text-Only Interface

The agent is purely text-based within Claude Code. There are no images, charts, color-coded statuses, or mouse-required interactions. This is inherently screen-reader friendly.

### 5.2 Structured Output

Results are delivered as:
- Markdown tables (for record lists)
- Bullet lists (for summaries)
- Inline code blocks (for API payloads, diffs)
- Plain text explanations (for errors)

This structure is parseable by assistive technologies.

### 5.3 Command Consistency

All commands follow the same prefix pattern (`/hubspot`). Arguments are positional and predictable. There is no hidden state or context menu.

### 5.4 Gaps

- **No alt-text for any visual element:** Not applicable today, but if charts or graphs are added later, alt-text is required.
- **No semantic HTML:** Output is markdown, not HTML, so ARIA roles are not used.
- **High cognitive load for compound requests:** The DAG planner (if wired) would produce multi-step plans. Without clear step numbering and progress announcements, users with cognitive disabilities may struggle to track state.
- **Destructive count gate requires exact typing:** This is a deliberate safety feature, but it assumes the user can read and type numbers accurately. Consider an additional confirmation for users who rely on voice input.
- **OAuth flow opens a browser:** Users relying on screen readers may lose context when the browser window opens. The auth URL is printed in text as a fallback.

---

## 6. UX Success Metrics

These metrics describe what the system should achieve when fully wired. Baseline measurements are not yet available because the core execute path is incomplete.

### 6.1 Task Success

| Metric | Target | Measurement Method |
|---|---|---|
| Simple read query latency | < 10 seconds end-to-end | Timestamp from `/hubspot` invocation to rendered result |
| Setup completion rate | > 80% unassisted | Track exits before `/hubspot status` succeeds |
| Setup time (Private App) | < 10 minutes | Self-reported or timed from first command to first successful read |
| Setup time (OAuth) | < 20 minutes | Same as above |
| Write approval comprehension | > 90% of users correctly identify what will change | A/B test with explicit comprehension question after preview |
| Destructive gate failure rate | < 5% accidental confirmations | Track cases where user types wrong count or cancels |

### 6.2 Safety & Trust

| Metric | Target | Measurement Method |
|---|---|---|
| Silent write rate | 0% | Writes should never execute without an explicit approval step |
| Preview accuracy | > 95% | Compare previewed impact count to actual impact count |
| Undo success rate | > 90% | Track successful reversion of updates within 24h |
| Scope-related error rate | < 2% | Proactive scope validation should prevent most 403s |

### 6.3 Efficiency

| Metric | Target | Measurement Method |
|---|---|---|
| Cache hit rate | > 40% for repeated reads | Query cache telemetry |
| Batch mode adoption | > 30% for bulk ops > 50 records | Track `--batch` and `--pattern` usage |
| Re-prompt rate | < 10% | Track how often users need to rephrase due to routing ambiguity |

### 6.4 Current Measurement Gaps

- No telemetry pipeline exists. All metrics would need to be derived from trace logs (`traces.jsonl`) or manual observation.
- The trace system captures request volume, latency, and estimated cost, but not user satisfaction or comprehension.
- No user interviews or usability studies have been conducted.

---

## 7. Known Gaps and Planned Improvements

### 7.1 Blocker-Level Gaps (Prevent Core Functionality)

**HITL execute path is not wired in `cli.py`**
- **What:** `hubspot_command()` dispatches agents in `preview` mode and returns a prompt snippet. It never calls `present_preview()`, captures user approval (`y/n/details`), or re-dispatches in `execute` mode.
- **Impact:** No write operation can actually complete. The agent is read-only in practice.
- **Fix:** Wire `present_preview()` into the CLI response loop. After preview, capture the next user message. If approved, call `dispatch_agents_parallel(..., mode="execute", payload=...)`.

**No invocation of Claude Code's native `Agent` tool**
- **What:** `dispatch_agent()` constructs a prompt string and returns an `AgentResult` dataclass. It never invokes the actual `Agent` tool that would spawn a sub-agent.
- **Impact:** The skill cannot run as a true Claude Code skill. It returns prompts meant for an LLM, not results.
- **Fix:** Replace prompt construction with an actual `Agent` tool call for sub-agent dispatch.

### 7.2 Major UX Gaps

**Tour blocked without portal config**
- **What:** `/hubspot tour` returns an error if no `.hubspot-portal` file exists.
- **Impact:** First-time users — the people who need onboarding help most — cannot access the tour.
- **Fix:** Create a "mock portal" mode for the tour that uses hardcoded data and does not require a live connection.

**OAuth path too long for non-engineers**
- **What:** OAuth requires creating a developer public app, saving credentials via a Python snippet, running a browser flow, and dealing with localhost callback.
- **Impact:** Non-technical RevOps admins are likely to abandon setup.
- **Fix:** Provide a guided OAuth wizard with inline instructions or default to Private App Token with a clearer explanation of when OAuth is actually needed.

**Sandbox env var never documented in Quick Start**
- **What:** `HUBSPOT_SANDBOX_PORTAL_ID` is required for sandbox previews but is not mentioned in the User Manual's Quick Start section.
- **Impact:** Users do not know the feature exists.
- **Fix:** Add a "Sandbox Setup" subsection to Quick Start.

**Progress streaming unreachable**
- **What:** Bulk operations are supposed to emit per-chunk progress ("Chunk 4 of 100 complete..."). The code exists but is never triggered because bulk execute is unwired.
- **Impact:** Users staring at a hung bulk operation have no feedback.
- **Fix:** Wire progress streaming into the execute path.

### 7.3 Architectural Over-Engineering

**DAG planner over-engineered for MVP**
- **What:** `plan.py` (931 lines) implements a full dependency-graph engine with topological sort, batch coalescing, and interactive plan modification. The spec wanted simple keyword conjunction detection ("and then").
- **Impact:** Large, untested surface area. High hallucination risk (phantom dependencies). Not wired into the CLI anyway.
- **Fix:** Remove or disable for MVP. Replace with the spec's simpler conjunction detection.

**Anomaly detection in critical path**
- **What:** Every request runs through `AnomalyDetector` which compares request duration against a per-portal baseline. Duration is computed as `(last_event.timestamp - first_event.timestamp)`, which includes user think time and approval delays.
- **Impact:** False positives can block legitimate requests.
- **Fix:** Move anomaly detection to an opt-in or background-only path. Use actual tool latency, not wall-clock time.

**Plugin system security model**
- **What:** Plugins are loaded from `~/.claude/hubspot/plugins/*.py` with a trivial sandbox (blocked builtins: `open`, `exec`, `eval`). Python introspection trivially bypasses this.
- **Impact:** Arbitrary code execution risk.
- **Fix:** Remove plugins for MVP, or run them in a subprocess with `RestrictedPython`.

### 7.4 Minor Gaps and Polish

- **No cost budget ceiling:** Token usage is tracked but not capped. A runaway compound request could accumulate significant cost.
- **Prompt infrastructure lacks versioning:** Sub-agent prompts are constructed dynamically with no hash or version tracking.
- **Reflection normalization masks mismatches:** `reflection.py` coerces types (string → bool → int → float) before comparison, which can hide real API mismatches.
- **No routing confidence score:** The LLM routing parser returns a list of agents with no confidence metric. Users cannot see how certain the system is.
- **Static tour steps:** The 7 tour steps are hardcoded markdown. They do not adapt to the user's actual portal schema or data.
- **Approval prompt does not support voice/text ambiguity:** A user typing "yes please" instead of "y" would be interpreted as a rejection because the parser only checks exact strings.

---

## 8. Honest Assessment Summary

### What Works Today

- **Read queries:** The full read path works end-to-end — routing, scope validation, agent dispatch (prompt construction), result formatting, query caching.
- **Setup and auth:** Both Private App Token and OAuth 2.0 flows are implemented and functional. Portal auto-detection works.
- **Portal management:** Switching, listing, status, and refresh all work.
- **Proactive scope validation:** Missing scopes are detected before any API call, with exact lists.
- **Trace and audit logging:** Every request is logged. Cost is estimated. Audit trail is append-only.
- **Session memory:** Summaries load on session start, providing continuity.
- **Tour rendering:** If a portal is configured, the static tour displays correctly.
- **Webhook listener:** Background server with v3 signature validation is implemented.

### What Does Not Work End-to-End

- **All write operations:** Preview prompts are built but never shown. Approval is never captured. Execute mode is never dispatched. The agent is effectively read-only.
- **Bulk/batch approvals:** The batch approval modes exist in code but are unreachable.
- **Progress streaming:** Implemented but unreachable.
- **DAG planner:** Implemented but not wired into the CLI.
- **Sandbox preview:** Implemented but not wired into the CLI, and its env var is undocumented.
- **Undo snapshots:** Saved to disk, but the undo command is not exposed in the CLI.

### What Is Over-Engineered

- **DAG planner:** Should be simple conjunction detection for MVP.
- **Anomaly detection:** Should not be in the critical path.
- **Plugin system:** Security model is not viable for production.
- **15 agents vs. 11:** 4 agents were explicitly out of scope.

---

*Document status: As-built specification. This document describes the implementation state as of commit `8b2516c` on branch `feat/phase-b-intelligence-ux`.*
