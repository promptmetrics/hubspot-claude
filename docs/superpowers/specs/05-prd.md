# PRD: HubSpot CRM Admin Agent (As Built)
**Status**: Shipped (v1.0, with caveats)  
**Author**: Product Review  
**Last Updated**: 2026-05-10  
**Version**: 1.0  
**Stakeholders**: Engineering, Security, UX Research, AI Engineer, Database Optimizer, Trend Researcher  

---

## 1. Problem Statement

HubSpot administration is fragmented across dozens of screens, object schemas, and automation tools. A single business request — e.g., "reorganize deal properties and build a follow-up workflow" — requires navigating multiple HubSpot modules, understanding object schemas, and manually translating business logic into HubSpot's native automation language. There is no persistent, conversational layer that lets an administrator describe intent in natural language and delegate execution safely.

**Evidence:**
- The original design spec (2026-05-06) identified this fragmentation as the core pain point.
- No competitive alternative offers natural-language administration with mandatory safety gates for HubSpot.

**Cost of not solving:** Admins spend hours on repetitive CRUD, bulk updates, and workflow configuration. Bulk operations carry high blast-radius risk because HubSpot provides no dry-run API for most write endpoints.

---

## 2. Goals & Success Metrics

| Goal | Metric | Current Baseline | Target | Measurement Window |
|------|--------|-----------------|--------|--------------------|
| Route natural-language requests correctly | Routing accuracy (manual corpus) | 13 test cases covering 7 agents | 100+ cases covering all 15 agents | Before GA |
| Prevent unapproved writes | Write operations with HITL approval | 0% (CLI only dispatches preview mode) | 100% of writes gated | GA |
| Reduce admin time for common ops | Time to update 10 contacts | Native UI: ~5 min | <60 seconds via agent | 30 days post-launch |
| Respect HubSpot rate limits | Rate-limit errors per 1,000 requests | <1% | 0% | 30 days post-launch |
| Multi-portal support | Portals switchable without re-auth | 1 (manual `.hubspot-portal` file) | Unlimited | GA |

**Non-Goals (Actual Scope, Not Aspirational):**
- **End-to-end HITL execute path is not wired in CLI.** `cli.py` dispatches `mode="preview"` only; the approval-and-execute loop described in the original spec is implemented in the orchestrator but not connected to the CLI entry point.
- **Not a Claude Code skill.** Despite the original mandate to use Claude Code's native `Agent` tool, the implementation built a 1,017-line custom orchestrator and 931-line DAG planner. No `Agent` tool invocation exists in the codebase.
- **No external dashboard or UI.** No Streamlit or web frontend exists.
- **No team collaboration / shared sessions.** Sessions are local to the user's machine and conversation context.
- **Undo for deletions is not supported.** HubSpot API has no restore endpoint.
- **No cost budget ceiling or token throttling.** Token usage is traced but not capped.
- **No shared HubSpotClient instance.** Every cache warm, capability probe, and some tools instantiate and close their own client.

---

## 3. User Personas

**Primary: Alex — RevOps Manager**
- Manages a 200-employee company's HubSpot portal daily.
- Needs to bulk-update properties, build workflows, and keep data clean.
- Comfortable with CLI but prefers natural language over clicking through HubSpot UI.
- Risk-averse: one bad bulk update affects the whole sales pipeline.

**Secondary: Jordan — HubSpot Admin / Consultant**
- Manages multiple client portals (5–20).
- Needs fast portal switching and schema-aware validation.
- Uses raw API fallback for edge cases not covered by standard tools.

**Tertiary: Taylor — Sales Ops Lead**
- Needs reports, pipeline velocity, and list segmentation.
- Less technical; relies on previews and confirmations before any write.

**Anti-Persona: Non-technical end user**
- This tool is CLI-first and requires understanding of HubSpot objects, properties, and scopes. It is not a replacement for the HubSpot UI for casual users.

---

## 4. User Stories & Acceptance Criteria

### 4.1 Objects Agent
**Story**: As a RevOps manager, I want to create, read, update, delete, and batch-upsert contacts, companies, deals, and tickets so that I can manage core CRM records without opening the HubSpot UI.  
**Acceptance Criteria**:
- [ ] Given a natural-language request mentioning "contact," "company," "deal," or "ticket," the orchestrator routes to ObjectsAgent.
- [ ] Given a create/update request, the agent returns a `PreviewResult` with `proposed_payload`, `impact_count`, and `original_values`.
- [ ] Given a batch upsert, the agent deduplicates on the input side and reports partial success/failure.
- [ ] Performance: Single-record reads complete in under 10 seconds for portals with <100k records.

### 4.2 Custom Objects Agent
**Story**: As a HubSpot admin, I want to manage custom object records by type ID so that I can operate on portal-specific schemas.  
**Acceptance Criteria**:
- [ ] Given a portal with custom objects, the agent discovers and lists available custom object types from the schema cache.
- [ ] Given a request for a nonexistent custom object type, the agent returns a clear error with available types.

### 4.3 Properties Agent
**Story**: As a RevOps manager, I want to create, update, and delete custom properties and property groups so that I can extend HubSpot's schema to match our business process.  
**Acceptance Criteria**:
- [ ] Given a property creation request, the agent validates the property type against HubSpot's allowed `fieldType` values.
- [ ] Given a property name typo, the agent suggests close matches using fuzzy matching.

### 4.4 Workflows Agent
**Story**: As a RevOps manager, I want to create, update, enroll records in, and toggle workflows so that I can automate follow-ups and lead scoring.  
**Acceptance Criteria**:
- [ ] Given a workflow request, the agent can use 4 built-in blueprints (deal_stage_task, lead_scoring, re_engagement, welcome_email) to accelerate construction.
- [ ] Given an enrollment request, the agent returns the count of enrolled records and any errors.

### 4.5 Lists Agent
**Story**: As a Sales Ops lead, I want to create static and dynamic lists, add/remove members, and build filter-based segments so that I can target the right contacts.  
**Acceptance Criteria**:
- [ ] Given a list creation request, the agent validates that required filters are provided for dynamic lists.

### 4.6 Pipelines Agent
**Story**: As a RevOps manager, I want to manage deal and ticket pipeline stages and reorder them so that our sales process matches the business flow.  
**Acceptance Criteria**:
- [ ] Given a reorder request, the agent returns a preview showing the before/after stage order.

### 4.7 Users Agent
**Story**: As a HubSpot admin, I want to onboard users, assign roles, manage teams, and deactivate accounts so that I can control portal access.  
**Acceptance Criteria**:
- [ ] Given a user creation request, the agent checks for existing users by email to prevent duplicates.

### 4.8 Engagements Agent
**Story**: As a RevOps manager, I want to create and retrieve notes, tasks, calls, meetings, and emails so that I can log activity against records.  
**Acceptance Criteria**:
- [ ] Given an engagement request, the agent associates the engagement with the correct contact/company/deal record.

### 4.9 Associations Agent
**Story**: As a RevOps manager, I want to create association schemas and link/unlink records across objects so that relationships are maintained in HubSpot.  
**Acceptance Criteria**:
- [ ] Given an association request, the agent validates that both object types exist before attempting the link.

### 4.10 Analytics Agent
**Story**: As a Sales Ops lead, I want to fetch reports, calculate conversion rates, measure pipeline velocity, create dashboards, and schedule email delivery so that I can share metrics with leadership.  
**Acceptance Criteria**:
- [ ] Given a metric request, the agent computes client-side where HubSpot API does not provide the aggregate directly.

### 4.11 Service Agent
**Story**: As a customer success manager, I want to manage knowledge base articles, ticket pipelines, service automation, and feedback surveys so that I can support our customers.  
**Acceptance Criteria**:
- [ ] Given a service request, the agent routes to the ServiceAgent and returns the relevant resource.

### 4.12 Marketing Agent
**Story**: As a marketing ops manager, I want to manage campaigns, emails, segments, A/B tests, and suppression lists so that I can execute campaigns from the command line.  
**Acceptance Criteria**:
- [ ] Given an email campaign request, the agent returns a preview of the audience size before any send.

### 4.13 CMS Agent
**Story**: As a marketing manager, I want to update CMS pages, manage files, and publish social posts so that I can keep our web presence current.  
**Acceptance Criteria**:
- [ ] Given a CMS request, the agent routes to CMSAgent and returns page/file metadata or confirmation.

### 4.14 Hygiene Agent
**Story**: As a RevOps manager, I want to find duplicate records, merge objects, bulk update fields, and preview segments before changes so that data quality remains high.  
**Acceptance Criteria**:
- [ ] Given a deduplication request, the agent returns duplicate pairs with a confidence score.
- [ ] Given a merge request, the agent shows the survivor record and all field mappings before execution.

### 4.15 Raw API Agent
**Story**: As a power user, I want to make direct HubSpot API calls for endpoints not covered by specialist agents so that I am never blocked by missing tool coverage.  
**Acceptance Criteria**:
- [ ] Given a raw API request, the agent validates that the user has the required scopes for the endpoint before dispatching.

---

## 5. Functional Requirements

### 5.1 Request Routing
- **Keyword fast-path**: The orchestrator uses a keyword heuristic map for the top 5–8 most common request types to avoid LLM latency on simple reads.
- **LLM-based routing**: For ambiguous or compound requests, the orchestrator builds a routing prompt and parses the LLM's agent selection. A fast-path ambiguity rule (`score[primary] >= 2 * score[secondary]`) auto-accepts high-confidence matches.
- **Static dependency graph**: PropertiesAgent must run before WorkflowsAgent; ObjectsAgent before ListsAgent and EngagementsAgent. The orchestrator orders dispatches accordingly.
- **Routing overrides**: Per-portal `routing_overrides.json` supports vocabulary aliases and agent overrides.

### 5.2 DAG Planning Engine (`plan.py`)
- **Compound-request detection**: 16 regex sequencers detect sequential phrasing ("and then", "after that", "step 1...").
- **DAG construction**: Requests are split into nodes (agent + action + inputs/outputs). Dependencies are derived via static graph, keyword output extraction, and data-flow heuristics (`created_id` string matching).
- **Topological sort**: Nodes are ordered respecting dependencies.
- **Batch coalescing**: Consecutive writes to the same agent are buffered into a single batch node where safe.
- **Interactive modification**: Users can `skip <node>`, `edit <node> key=value`, or `reorder <node> <position>` via regex-parsed commands.
- **Risk propagation**: The overall plan risk is the maximum node risk.
- **Sandbox execution**: Plans can be executed against a secondary sandbox portal with behavior-diff computation.

### 5.3 Human-in-the-Loop (HITL) Approval
- **Risk levels**: LOW (read-only), MEDIUM (create/single update), HIGH (bulk update >10 records), DESTRUCTIVE (delete/merge/archive).
- **Read-based previews**: Since HubSpot has no dry-run API, previews are generated by reading current values and computing diffs.
- **Preview content**: `preview`, `impact_count`, `rollback_steps`, `risk_level`, `proposed_payload`, `original_values`.
- **Approval modes**: SINGLE (approve one by one), BATCH (approve full plan at once), PATTERN (approve first 3 samples + pattern summary for the rest).
- **Destructive gate**: User must type the exact count of affected records.
- **Undo snapshots**: Original values are saved to `.claude/hubspot/<portal_id>/undo_snapshots/<action_id>.json` before updates.
- **Reflection**: Post-write, the agent re-fetches the record and compares properties against intended values. Mismatches are surfaced.

**Known gap**: The CLI entry point (`cli.py`) only dispatches `mode="preview"`. The execute path exists in the orchestrator but is not wired to the CLI, meaning end-to-end HITL approval is not functional from the user-facing entry point.

### 5.4 Authentication & Portal Management
- **OAuth 2.0**: Authorization URL generation, local callback server on `127.0.0.1:3000`, token exchange, and automatic refresh.
- **Private App tokens**: Direct token entry via CLI.
- **Portal auto-detection**: Reads `.hubspot-portal` file in the working directory.
- **Multi-portal**: Each portal has isolated config, cache, and undo snapshots. Switching does not clear conversation history but abandons pending approvals for the previous portal.
- **Capability probing**: On setup, the system makes 7 sequential HTTP calls to determine portal tier and feature availability (workflows, users, custom objects, etc.). Results are cached for 24 hours.

**Known gaps**: OAuth `state` parameter is predictable (set to `portal_id`). PKCE is not implemented. Credential files are written with default (world-readable) permissions.

### 5.5 Caching
- **SchemaCache**: 1-hour TTL for object schemas, properties, pipeline definitions, workflow IDs, list IDs, and user mappings. Stored per-portal in `schema_cache.json`.
- **QueryCache**: 5-minute TTL for read operations (`hubspot_get_*`, `hubspot_search_*`, `hubspot_list_*`). Stored per-portal in `query_cache.json`.
- **CapabilityCache**: 24-hour TTL for portal capability matrices. Stored per-portal in `capabilities.json`.
- **Cache invalidation**: Explicit via `/hubspot refresh`; implicit on TTL expiry; post-write invalidation for affected domains.

### 5.6 Bulk Operations & Resilience
- **Checkpointing**: `CheckpointManager` writes chunk status to `in_flight/<action_id>.jsonl`. On resumption, reads the last completed chunk and offers restart.
- **Progress tracking**: `ProgressTracker` writes a JSON snapshot after each chunk for polling by CLI/tests.
- **Action ledger**: `ActionLedger` provides append-only idempotency logging with payload hashing. Prevents duplicate execution of in-flight actions.
- **Rate limiting**: `HubSpotClient` enforces 100 requests per 10 seconds and 4 concurrent batch operations via async semaphores.
- **Retry logic**: 3 retries with exponential backoff at the tool level; up to 2 re-dispatches at the agent level; hard limit of 3 retries total.

### 5.7 Webhook Listener (`webhooks.py`, `server.py`)
- **aiohttp server**: Binds to `0.0.0.0:8080` by default.
- **HubSpot v3 signature validation**: Verifies HMAC-SHA256 of request body using `client_secret`. Checks timestamp freshness.
- **Event routing table**: Maps webhook event types to agent names (contact/company/deal/ticket -> objects; call/email/meeting/note/task -> engagements; workflow -> workflows; etc.).
- **Fallback**: If V3 headers are missing, falls back to legacy `X-HubSpot-Signature`.

**Known gaps**: No rate limiting, IP allowlisting, or additional authentication on the webhook server. Binding to `0.0.0.0` exposes the listener on all interfaces.

### 5.8 Safety & Observability
- **Audit log**: Append-only `audit.log` per portal with timestamp, action, agent, result summary, and `informing_sources`.
- **Trace events**: Structured traces (`traces.jsonl`) capture request_received, route_decision, tool_call, approval, completion, error, and reflection events. Includes token count and estimated USD cost.
- **Anomaly detection**: Per-portal baselines for tool duration and failure rate. Flags operations deviating >3 sigma.
- **PII redaction**: Three levels — `off`, `pii` (masks emails, phones, long name-like strings), `full` (masks every string >3 chars). Applied to traces and audit logs before disk write.
- **Replay**: `MockHubSpotClient` replays recorded API responses from traces for regression testing.

### 5.9 Extensibility
- **Plugins**: `PluginLoader` scans `~/.claude/hubspot/plugins/*.py`, loads each in an isolated namespace with restricted builtins (`open`, `exec`, `eval`, `compile` removed). Plugin tools are injected into the global tool registry.
- **Hooks**: Global `HookRegistry` supports `pre_write`, `post_write`, `pre_approval`, `post_approval`. Handlers can modify payloads or block operations.
- **RBAC**: `roles.json` per portal defines `user_id`, `allowed_agents`, `max_risk_level`, and `denied_tools`. If no roles file exists, defaults to allow-all.
- **Sandbox preview**: `SandboxRunner` executes a plan against a secondary portal configured via `HUBSPOT_SANDBOX_PORTAL_ID`, then computes a behavior diff.

**Known gaps**: Plugin sandbox is trivially bypassable via Python introspection. Hook registry is a global singleton without portal isolation. RBAC defaults to allow-all with no authentication layer.

### 5.10 Workflow Blueprints
- Four built-in blueprints registered in `hubspot_agent.blueprints.workflows`:
  1. **deal_stage_task** — Create a follow-up task when a deal moves to a specific stage.
  2. **lead_scoring** — Increment a score property on engagement and promote lifecycle stage at threshold.
  3. **re_engagement** — Send an email to inactive contacts after a delay.
  4. **welcome_email** — Send a welcome email to new contacts after an optional delay.
- Each blueprint defines a parameter schema and a `build(params)` function returning workflow JSON.

### 5.11 Tour Mode & Setup Wizard
- **Tour**: 7 static markdown steps demonstrating read queries, write previews, batch approval, and workflow blueprints. Blocked if no portal is configured.
- **Setup wizard**: Guides users through auth selection (OAuth vs. Private App), capability probing, schema warming, and scope validation.

---

## 6. Non-Functional Requirements

### 6.1 Security
- **Authentication**: OAuth 2.0 or Private App tokens only. No API key support.
- **Scope validation**: Proactive check before dispatch; no "try and fail."
- **Data safety**: Sub-agents do not persist raw HubSpot data to disk (except schema metadata). PII is redacted in traces/logs.
- **Token storage**: Tokens stored in `~/.claude/hubspot/<portal_id>.json`. 

**Known issues (blockers from validation):**
1. OAuth `state` is predictable (`portal_id`).
2. PKCE is not implemented.
3. Credential files written with default umask (world-readable).
4. Plugin sandbox bypassable via `__import__` / `getattr`.
5. Webhook server binds to `0.0.0.0` with no rate limiting or IP allowlisting.
6. No encryption at rest for tokens.
7. Hooks fail-open on exceptions (pre_write errors are logged but do not block the operation).
8. `portal_id` is not validated before filesystem path construction (path traversal risk in older versions; fixed in later commits).

### 6.2 Performance
- **Rate limiting**: 100 req/10s for standard endpoints; 4 concurrent batch operations max.
- **Latency target**: Simple reads complete within 10 seconds for portals with <100k records.
- **File I/O**: `trace.py` and `ledger.py` use atomic append via temp-file rename. This is O(n) on file size and becomes a bottleneck at >50,000 traces. `query_cache.json` and `schema_cache.json` are rewritten in full on every mutation with no LRU eviction.

### 6.3 Observability
- **Traces**: Every request emits a trace event to `traces.jsonl` with portal_id, trace_id, event_type, and payload.
- **Audit log**: Every approved write appends to `audit.log`.
- **Ledger**: Every action start/completion appends to `action_log.jsonl`.
- **Session summaries**: Saved to `sessions/<session_id>.json` for cross-session context recovery.
- **Maintenance**: `run_maintenance()` prunes undo snapshots (>30 days) and completed checkpoints (>7 days), and rotates JSONL logs.

### 6.4 Reliability
- **Graceful degradation**: Missing Enterprise scopes fall back to Professional/Starter equivalents where possible.
- **Timeout handling**: Tool-level 30s HTTP timeout. Agent-level timeout abandons the result and suggests chunking.
- **Schema validation**: `validation.py` checks property existence and type compatibility with fuzzy matching for typos. Does not validate HubSpot `fieldType`/`type` pairing rules, string length limits, number ranges, date formats, or read-only properties.

---

## 7. Acceptance Criteria

### Must Have (Shipped)
- [x] 15 specialist agents defined with domain-specific prompts and tool bindings.
- [x] Async HTTP client with rate-limit enforcement and token refresh.
- [x] Schema cache (1h TTL) and query cache (5m TTL).
- [x] Keyword + LLM-based routing with dependency ordering.
- [x] DAG planner with topological sort, batch coalescing, and interactive modification.
- [x] Preview/diff generation for write operations.
- [x] Undo snapshot storage for updates.
- [x] Action ledger for idempotency.
- [x] Checkpointing and progress tracking for bulk operations.
- [x] OAuth 2.0 and Private App token auth.
- [x] Portal auto-detection via `.hubspot-portal`.
- [x] Capability probing and setup wizard.
- [x] Webhook listener with v3 signature validation.
- [x] 4 workflow blueprints.
- [x] RBAC, plugins, hooks, sandbox preview, anomaly detection, replay, reflection, tour mode.

### Must Have (Not Functional)
- [ ] End-to-end HITL execute path wired in CLI. The orchestrator supports it, but `cli.py` does not call `mode="execute"`.
- [ ] Claude Code `Agent` tool integration. The system builds prompt objects and returns `AgentResult` dataclasses; it does not invoke Claude Code's native sub-agent dispatch.

### Should Have (Partial)
- [~] Routing corpus has 13 cases covering 7 agents. Needs expansion to 100+ cases covering all 15 agents before production reliance on LLM routing.
- [~] Onboarding unassisted in <15 minutes is marginal. OAuth requires creating a public developer app; Private App token is ~10 minutes for technical users.

---

## 8. Success Metrics (Measurable)

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Routing accuracy on regression corpus | >= 95% | `tests/routing_corpus.yaml` + manual evaluation |
| Preview generation latency (p95) | < 3s | Trace events for `preview` operations |
| Write operation blast radius (max records affected per unapproved action) | 0 | Audit log review — no writes without approval record |
| Rate limit compliance | 0 429 errors caused by client | HubSpot API response codes in trace logs |
| Schema cache hit rate | > 80% | Cache read vs. miss logging |
| Plugin load success rate | 100% of valid plugins | Plugin loader logs |
| Undo snapshot availability | 100% of updates | Snapshot directory audit |
| Security blocker resolution | 0 open blockers | Security review checklist |

---

## 9. Open Questions

1. **Product scope decision**: The implementation is 40–60% larger than the original 11-agent MVP. Do we prune back to 11 agents and remove out-of-scope subsystems (CMS, Marketing, Service, Custom Objects, Webhooks, DAG planner, RBAC, Plugins, Sandbox, Replay, Anomaly Detection), or do we update the spec to match the implementation?

2. **Orchestration architecture**: The custom orchestrator (`orchestrator.py` + `plan.py`) directly contradicts the original mandate to use Claude Code's native `Agent` tool. Do we refactor to use the `Agent` tool, or do we accept the custom framework and document the deviation?

3. **CLI execute path**: How should the CLI present previews, capture user approval, and re-dispatch for execution? Should this be interactive (prompt in terminal) or file-based (user edits a `.approve` file)?

4. **Security hardening**: Which of the 5 blocker-level security issues (predictable OAuth state, missing PKCE, world-readable credentials, bypassable plugin sandbox, exposed webhook server) are prerequisites for any production use, and which can be mitigated by removing the feature (e.g., remove plugins for MVP)?

5. **Cost control**: `trace.py` captures token cost per request but there is no budget ceiling. What is an acceptable per-session or per-portal cost limit, and what should happen when it is exceeded (hard stop vs. warn-and-continue)?

6. **Market validation**: There is no user research, pilot data, or competitive signal justifying the expanded scope. Should we freeze feature development and run structured problem interviews with 5–10 target RevOps managers before building Phase B/C?

7. **Database strategy**: Flat-file JSON/JSONL is reasonable for a single-user skill but has O(n) append cost and lost-update risk under concurrent writers. Is there a path to SQLite or another embedded store for trace/ledger/checkpoint data?

8. **Competitive differentiation**: HubSpot's own Breeze AI / ChatSpot and open-source alternatives (e.g., DenchClaw) already offer conversational CRM administration. What is the defensible moat for this product, and does the expanded scope increase or decrease that moat?

---

## 10. Appendix

### A. Agent Inventory (As Built)

| # | Agent | Domain | Tools |
|---|---|---|---|
| 1 | ObjectsAgent | Core CRM CRUD | get, search, create, update, delete, batch_upsert |
| 2 | CustomObjectsAgent | Custom object records | get, search, create, update, delete, batch_upsert |
| 3 | PropertiesAgent | Schema management | get, list, create, update, delete property |
| 4 | WorkflowsAgent | Automation | get, list, create, update, enroll, toggle workflow |
| 5 | ListsAgent | Segmentation | get, list, create, update, add, remove from list |
| 6 | PipelinesAgent | Pipeline stages | get, list, create, update, reorder pipeline |
| 7 | UsersAgent | Portal user management | get, list, create, update, deactivate user |
| 8 | EngagementsAgent | Activity logging | get, search, create note/task/email/meeting/call |
| 9 | AssociationsAgent | Record linking | get/create schema, associate/disassociate |
| 10 | AnalyticsAgent | Reporting & metrics | get report, calculate metrics, pipeline velocity, create report/dashboard, schedule email |
| 11 | ServiceAgent | Service Hub | get KB articles, ticket pipelines, service automation, feedback surveys |
| 12 | MarketingAgent | Marketing campaigns | create/get email, create campaign, create segment, A/B test, suppression list |
| 13 | CMSAgent | Content management | get/update page, list/upload file, publish social post |
| 14 | HygieneAgent | Data quality | find duplicates, merge objects, bulk update, preview segment |
| 15 | RawAPIAgent | Escape hatch | direct HubSpot API call |

### B. Core Module Inventory

| Module | Purpose | Lines (approx) |
|---|---|---|
| `orchestrator.py` | Custom routing, scope validation, capability probing, HITL approval, anomaly detection, role checking, hook execution, sandbox preview, reflection | ~1,017 |
| `plan.py` | DAG planning engine with topological sort, batch coalescing, interactive modification | ~931 |
| `client.py` | Async httpx with rate limiting, retry, token refresh | ~200 |
| `cache.py` | Schema cache (1h TTL) + custom object discovery | ~150 |
| `query_cache.py` | Read cache (5m TTL) | ~100 |
| `validation.py` | Schema-aware pre-validation with fuzzy matching | ~150 |
| `errors.py` | ErrorCategory enum + HubSpotError hierarchy | ~50 |
| `auth.py` | OAuth 2.0 + Private App tokens | ~150 |
| `config.py` | Portal config management + `.hubspot-portal` detection | ~150 |
| `cli.py` | Main CLI entry point (`/hubspot` command) | ~300 |
| `ledger.py` | Action log for idempotency | ~150 |
| `checkpoint.py` | Mid-execution checkpointing for bulk ops | ~150 |
| `snapshot.py` | Undo snapshots | ~50 |
| `trace.py` | Structured trace events + cost tracking | ~250 |
| `audit.py` | Append-only audit log | ~100 |
| `anomaly.py` | Per-portal baseline anomaly detection | ~200 |
| `redaction.py` | PII redaction (off/pii/full) | ~100 |
| `reflection.py` | Post-write verification | ~150 |
| `replay.py` | Trace replay against mock client | ~150 |
| `progress.py` | Progress streaming for long ops | ~100 |
| `maintenance.py` | Snapshot pruning, log rotation | ~150 |
| `plugins.py` | Custom Python tool plugins | ~150 |
| `hooks.py` | Pre/post write/approval event hooks | ~200 |
| `roles.py` | RBAC with per-portal roles.json | ~100 |
| `routing.py` | Per-portal routing overrides | ~100 |
| `sandbox.py` | Sandbox preview for high-risk ops | ~200 |
| `capabilities.py` | Portal capability probing | ~200 |
| `research.py` | Research prompt block + URL classifier | ~100 |
| `memory.py` | Session summary persistence | ~100 |
| `preview.py` | Preview formatting (diffs, pattern summaries) | ~150 |
| `webhooks.py` | Webhook listener + signature validation | ~250 |
| `server.py` | aiohttp webhook server CLI | ~100 |
| `callback_server.py` | Local OAuth callback server | ~100 |
| `app_credentials.py` | App client_id/client_secret storage | ~50 |
| `setup.py` | Setup wizard | ~200 |
| `tour.py` | Tour mode | ~150 |
| `agents/_base.py` | Base agent prompt builder | ~150 |
| `blueprints/workflows/` | 4 workflow blueprints | ~200 total |

**Total Python codebase**: ~6,946 lines across 15 agents and 40+ infrastructure modules (88 test files).

### C. Validation Report Summary

The implementation was reviewed by six domain experts on 2026-05-10. Key findings:
- **12 Blockers**, **22 Warnings**, **14 Suggestions**.
- Top 3 risks: (1) Not a Claude Code skill — custom orchestration built instead of using native `Agent` tool; (2) Critical security vulnerabilities in OAuth and plugin system; (3) Scope creep transformed an 11-agent MVP into an unmaintainable platform framework.
- **Recommendation**: Freeze feature development and resolve blockers. Decide between pruning to MVP spec or rewriting the spec to match the implementation.
