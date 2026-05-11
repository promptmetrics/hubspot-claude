# Technical Specification: HubSpot CRM Admin Agent

**Date:** 2026-05-10
**Version:** 0.1.0
**Status:** As-built documentation

---

## 1. System Architecture Overview

### 1.1 What Was Actually Built

The implementation is a Python-based CLI skill for Claude Code that administers HubSpot CRM via natural language. Contrary to the approved design spec's mandate to "use Claude Code's native `Agent` tool for sub-agent dispatch," the implementation built a **custom orchestration framework** consisting of a 1,017-line orchestrator, a 931-line DAG planner, and a full dispatch pipeline. No invocation of Claude Code's `Agent` tool exists anywhere in the codebase.

### 1.2 Architecture Diagram (Text)

```
+-------------------------------------------------------------+
|                         User Layer                           |
|  /hubspot CLI  ->  cli.py  ->  hubspot_command()           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                     Orchestration Layer                      |
|  orchestrator.py (1,017 lines)                               |
|  - Routing (fast-path keywords + LLM fallback)             |
|  - Scope/capability validation                               |
|  - HITL approval gating                                      |
|  - Anomaly detection (3-sigma baselines)                   |
|  - Role-based access control                                 |
|  - Hook execution (pre/post write/approval)                |
|  - Sandbox preview offers                                    |
|  - Plugin initialization                                     |
|  - Session memory management                               |
+-------------------------------------------------------------+
                              |
              +---------------+---------------+
              |                               |
              v                               v
+----------------------------+   +--------------------------+
|      Planning Engine       |   |     State & Cache        |
|  plan.py (931 lines)       |   |  - SchemaCache (1h TTL)  |
|  - Compound request DAG    |   |  - QueryCache (5m TTL)   |
|  - Topological sort      |   |  - SessionMemory         |
|  - Batch coalescing        |   |  - Checkpoint (JSONL)    |
|  - Interactive modification|   |  - ProgressTracker       |
|  - Risk propagation      |   |  - Undo snapshots        |
+----------------------------+   +--------------------------+
              |
              v
+-------------------------------------------------------------+
|                     Agent Layer (15 agents)                  |
|  objects, properties, workflows, lists, pipelines, users,    |
|  hygiene, analytics, associations, engagements, raw_api,    |
|  custom_objects, service, marketing, cms                     |
|  Each: domain prompt + restricted tool subset                |
+-------------------------------------------------------------+
              |
              v
+-------------------------------------------------------------+
|                      Tool Layer                              |
|  @tool registry (global dict) -> invoke_tool()             |
|  - Per-domain tool modules (~20 tool modules)                |
|  - QueryCache integration for read tools                   |
|  - Domain-aware invalidation on writes                     |
+-------------------------------------------------------------+
              |
              v
+-------------------------------------------------------------+
|                  HubSpot API Integration                     |
|  HubSpotClient (httpx.AsyncClient)                         |
|  - OAuth 2.0 / Private App auth                            |
|  - Rate limiting (100 req/10s semaphore)                   |
|  - Token refresh                                           |
|  - Retry logic for 401/403/429                             |
+-------------------------------------------------------------+
              |
              v
+-------------------------------------------------------------+
|                Observability & Safety Layer                  |
|  - trace.py: structured JSONL traces, cost tracking        |
|  - ledger.py: action ledger for idempotency                |
|  - audit.py: append-only audit.log                         |
|  - anomaly.py: per-portal baselines, 3-sigma threshold     |
|  - replay.py: ReplayEngine against MockHubSpotClient       |
|  - reflection.py: post-write verification                  |
|  - validation.py: schema-aware pre-validation              |
|  - redaction.py: PII redaction (off/pii/full)            |
+-------------------------------------------------------------+
```

### 1.3 Divergence from Approved Spec

| Aspect | Spec Intent | Actual Implementation |
|--------|-------------|----------------------|
| Orchestration | Claude Code native `Agent` tool | Custom 1,017-line orchestrator + 931-line DAG planner |
| Agent count | 11 specialist agents | 15 agents (added custom_objects, service, marketing, cms) |
| Routing | Keyword heuristics + simple conjunction detection | Fast-path keywords + LLM fallback + DAG planner with 16 regex sequencers |
| Out-of-scope items | Custom objects, CMS, marketing, service, webhooks, real-time sync | All implemented except external dashboard |
| State model | Two-tier (conversation + per-portal disk cache) | Same two-tier, but with 12+ additional subsystems (plugins, hooks, RBAC, sandbox, replay, anomaly) |
| Plugin system | Not mentioned | `plugins.py` with restricted builtins sandbox |
| Webhook listener | Explicitly out of scope | `webhooks.py` + `server.py` with aiohttp-based receiver |

---

## 2. Component Breakdown

### 2.1 Core Modules

| Module | Lines | Responsibility | Key Interfaces |
|--------|-------|----------------|--------------|
| `__init__.py` | ~5 | Package root, version | `__version__ = "0.1.0"` |
| `models.py` | ~70 | Pydantic data models | `RiskLevel`, `BatchApprovalMode`, `TaskIntent`, `PlanStep`, `ExecutionPlan`, `PreviewResult`, `AgentResult` |
| `config.py` | ~105 | Portal configuration, auto-detection | `PortalConfig`, `load_portal_config()`, `save_portal_config()`, `detect_default_portal()` |
| `client.py` | ~200 | Async HTTP client for HubSpot API | `HubSpotClient`, `APIResponse` |
| `errors.py` | ~45 | Exception hierarchy | `HubSpotError`, `RateLimitError`, `ScopeError`, `ErrorCategory` |
| `auth.py` | ~134 | OAuth 2.0 flow + token refresh | `get_authorization_url()`, `exchange_code_for_token()`, `refresh_access_token()` |
| `app_credentials.py` | ~40 | HubSpot app credential storage | `save_app_credentials()`, `load_app_credentials()` |
| `callback_server.py` | ~60 | Local HTTP server for OAuth callback | `run_callback_server()` |
| `server.py` | ~72 | Webhook server entry point | `main()` |
| `cli.py` | ~393 | `/hubspot` CLI command dispatcher | `hubspot_command(request, working_dir)` |

### 2.2 Orchestration Modules

| Module | Lines | Responsibility | Key Interfaces |
|--------|-------|----------------|--------------|
| `orchestrator.py` | ~1,017 | **God object**: routing, dispatch, HITL, scope validation, anomaly detection, role checking, hook execution, sandbox preview, reflection, plugin init | `dispatch_agent()`, `dispatch_agents_parallel()`, `route_request()`, `check_dispatch_readiness()`, `initialize_session()` |
| `routing.py` | ~80 | Per-portal routing overrides | `load_routing_overrides()`, `apply_routing_overrides()` |
| `plan.py` | ~931 | DAG planner for compound requests | `DAGPlanner`, `DAGPlan`, `PlanNode`, `PlanExecutor`, `InteractivePlanModifier` |
| `preview.py` | ~120 | Inline diff viewer, pattern summaries, DAG plan rendering | `format_preview()`, `render_plan()` |

### 2.3 State & Cache Modules

| Module | Lines | Responsibility | Key Interfaces |
|--------|-------|----------------|--------------|
| `cache.py` | ~150 | SchemaCache (1h TTL) for object schemas | `SchemaCache`, `warm_standard_schemas()` |
| `query_cache.py` | ~120 | QueryCache (5m TTL) for read results, domain-aware invalidation | `QueryCache`, `is_read_tool()` |
| `memory.py` | ~90 | SessionMemory / SessionSummary persistence | `SessionMemory.load_last_summary()`, `SessionMemory.save_summary()` |
| `checkpoint.py` | ~110 | Atomic JSONL checkpointing for bulk ops | `CheckpointWriter`, `in_flight/` + `completed/` directories |
| `progress.py` | ~80 | ProgressTracker for long-running ops | `ProgressTracker` |
| `snapshot.py` | ~70 | Undo snapshots before writes | `save_undo_snapshot()`, `load_undo_snapshot()` |

### 2.4 Observability Modules

| Module | Lines | Responsibility | Key Interfaces |
|--------|-------|----------------|--------------|
| `trace.py` | ~240 | Structured JSONL traces, cost/latency tracking | `emit_trace()`, `compute_trace_summary()`, `compute_status_aggregates()` |
| `ledger.py` | ~140 | Action ledger for idempotency (payload hashing, 1h stale window) | `ActionLedger`, `is_duplicate()` |
| `audit.py` | ~50 | Append-only audit.log | `log_write()` |
| `anomaly.py` | ~130 | Per-portal baselines (median failure rate, duration), 3-sigma threshold pausing | `AnomalyDetector`, `should_pause()` |
| `replay.py` | ~90 | ReplayEngine against MockHubSpotClient | `ReplayEngine`, `MockHubSpotClient` |

### 2.5 Safety & Validation Modules

| Module | Lines | Responsibility | Key Interfaces |
|--------|-------|----------------|--------------|
| `validation.py` | ~160 | Schema-aware pre-validation with fuzzy matching (difflib.get_close_matches) | `validate_payload()`, `suggest_corrections()` |
| `reflection.py` | ~100 | Post-write verification (re-fetch + compare) | `reflect_on_write()`, `_normalize_value()` |
| `redaction.py` | ~80 | PII redaction: off/pii/full levels | `redact_dict_for_disk()`, `redact_string()` |
| `sandbox.py` | ~150 | SandboxRunner for high-risk preview, BehaviorDiff | `SandboxRunner`, `SandboxResult`, `should_offer_sandbox()` |

### 2.6 Extensibility Modules

| Module | Lines | Responsibility | Key Interfaces |
|--------|-------|----------------|--------------|
| `plugins.py` | ~144 | PluginLoader with restricted builtins (open/exec/eval/compile blocked), namespace isolation | `PluginLoader`, `augment_agent_prompt()` |
| `hooks.py` | ~180 | HookRegistry with PRE_WRITE, POST_WRITE, PRE_APPROVAL, POST_APPROVAL events | `HookRegistry`, `HookEvent`, `HookContext`, `HookResult`, `run_hooks()` |
| `roles.py` | ~70 | RoleManager with per-portal roles.json, allow-all default | `RoleManager`, `RoleConfig`, `can_dispatch()` |

### 2.7 Agent Modules (15)

| Module | Domain | Key Function |
|--------|--------|-------------|
| `agents/objects.py` | Core CRUD | `get_objects_agent_prompt()` |
| `agents/custom_objects.py` | Custom object schemas | `get_custom_objects_agent_prompt()` |
| `agents/properties.py` | Schema management | `get_properties_agent_prompt()` |
| `agents/workflows.py` | Automation | `get_workflows_agent_prompt()` |
| `agents/lists.py` | Segmentation | `get_lists_agent_prompt()` |
| `agents/pipelines.py` | Pipeline stages | `get_pipelines_agent_prompt()` |
| `agents/users.py` | Permissions | `get_users_agent_prompt()` |
| `agents/hygiene.py` | Data quality | `get_hygiene_agent_prompt()` |
| `agents/analytics.py` | Reporting | `get_analytics_agent_prompt()` |
| `agents/associations.py` | Relationships | `get_associations_agent_prompt()` |
| `agents/engagements.py` | Activity | `get_engagements_agent_prompt()` |
| `agents/service.py` | Service hub | `get_service_agent_prompt()` |
| `agents/marketing.py` | Marketing hub | `get_marketing_agent_prompt()` |
| `agents/cms.py` | CMS content | `get_cms_agent_prompt()` |
| `agents/raw_api.py` | Escape-hatch API | `get_raw_api_agent_prompt()` |
| `agents/_base.py` | Prompt builder | `build_agent_prompt()`, `AgentPrompt` |

### 2.8 Tool Modules (~20 modules)

Tools are registered via a global `@tool` decorator in `tools/__init__.py`. Each tool module contains async Python functions decorated with `@tool(name, description)`.

| Module | Domain | Example Tools |
|--------|--------|--------------|
| `tools/objects.py` | Objects | `hubspot_get_object`, `hubspot_search_objects`, `hubspot_create_object`, `hubspot_update_object`, `hubspot_delete_object`, `hubspot_batch_upsert_objects` |
| `tools/properties.py` | Properties | `hubspot_get_property`, `hubspot_list_properties`, `hubspot_create_property`, `hubspot_update_property`, `hubspot_delete_property` |
| `tools/workflows.py` | Workflows | `hubspot_get_workflow`, `hubspot_list_workflows`, `hubspot_create_workflow`, `hubspot_update_workflow`, `hubspot_enroll_workflow`, `hubspot_toggle_workflow` |
| `tools/lists.py` | Lists | `hubspot_get_list`, `hubspot_list_lists`, `hubspot_create_list`, `hubspot_update_list`, `hubspot_add_to_list`, `hubspot_remove_from_list` |
| `tools/pipelines.py` | Pipelines | `hubspot_get_pipeline`, `hubspot_list_pipelines`, `hubspot_create_pipeline`, `hubspot_update_pipeline`, `hubspot_reorder_stages` |
| `tools/users.py` | Users | `hubspot_get_user`, `hubspot_list_users`, `hubspot_create_user`, `hubspot_update_user`, `hubspot_deactivate_user` |
| `tools/engagements.py` | Engagements | `hubspot_get_engagement`, `hubspot_search_engagements`, `hubspot_create_note`, `hubspot_create_task`, `hubspot_create_email`, `hubspot_create_meeting`, `hubspot_create_call` |
| `tools/associations.py` | Associations | `hubspot_get_association_schema`, `hubspot_create_association_schema`, `hubspot_associate_records`, `hubspot_disassociate_records` |
| `tools/analytics.py` | Analytics | `hubspot_get_report`, `hubspot_calculate_metrics`, `hubspot_pipeline_velocity` |
| `tools/reporting.py` | Reporting | Additional report builders |
| `tools/service.py` | Service | Service hub CRUD tools |
| `tools/marketing.py` | Marketing | Campaign and segment tools |
| `tools/cms.py` | CMS | Page, blog, file tools |
| `tools/hygiene.py` | Hygiene | `hubspot_find_duplicates`, `hubspot_merge_objects`, `hubspot_bulk_update_objects`, `hubspot_preview_segment` |
| `tools/raw_api.py` | Raw API | `hubspot_raw_api` |
| `tools/docs.py` | Documentation | Doc search tools |

### 2.9 Supporting Modules

| Module | Responsibility |
|--------|----------------|
| `capabilities.py` | `CapabilityMatrix` with `probe_portal()` (7 endpoint tests) |
| `maintenance.py` | TTL-based pruning, log rotation |
| `setup.py` | Guided setup wizard with scope gap report |
| `tour.py` | 7-step interactive walkthrough |
| `research.py` | Doc-search guidance block for agents |
| `testing.py` | `ChaosHubSpotClient` for fault injection |

---

## 3. Data Models

### 3.1 Core Models (`models.py`)

```python
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"

class BatchApprovalMode(str, Enum):
    SINGLE = "single"
    BATCH = "batch"
    PATTERN = "pattern"

class TaskIntent(BaseModel):
    intent_type: str
    target_object: str | None = None
    description: str
    risk_level: RiskLevel
    estimated_impact: int | None = None
    required_scopes: list[str] = Field(default_factory=list)

class PlanStep(BaseModel):
    step_number: int
    agent: str
    action: str
    hubspot_endpoint: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    validation_rules: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)

class ExecutionPlan(BaseModel):
    plan_id: str
    thread_id: str
    steps: list[PlanStep]
    overall_risk: RiskLevel
    rollback_available: bool
    estimated_duration_seconds: int

class PreviewResult(BaseModel):
    preview: dict[str, Any]
    impact_count: int
    rollback_steps: list[str] = Field(default_factory=list)
    risk_level: RiskLevel
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    original_values: dict[str, Any] = Field(default_factory=dict)
    informing_sources: list[dict[str, Any]] = Field(default_factory=list)
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE
    pattern_sample_size: int = 3

class AgentResult(BaseModel):
    agent_name: str
    status: str  # "success", "error", "preview", "needs_approval", "corrected"
    data: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    retryable: bool = False
    corrected_payload: dict[str, Any] | None = None
    correction_reason: str | None = None
    reflection: dict[str, Any] | None = None
```

### 3.2 Configuration Models

```python
@dataclass
class PortalConfig:
    portal_id: str
    token: str
    tier: str = "unknown"
    scopes_granted: list[str] | None = None
    auth_type: str = "private_app"  # "oauth" or "private_app"
    refresh_token: str | None = None
    expires_at: float | None = None  # Unix timestamp
```

### 3.3 Plan Models (`plan.py`)

```python
class PlanNode(BaseModel):
    node_id: str
    agent: str
    action: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel

class DAGPlan(BaseModel):
    plan_id: str
    nodes: list[PlanNode]
    edges: list[tuple[str, str]]
    overall_risk: RiskLevel
    estimated_duration_seconds: int
```

### 3.4 Hook Models (`hooks.py`)

```python
class HookEvent(str, Enum):
    PRE_WRITE = "pre_write"
    POST_WRITE = "post_write"
    PRE_APPROVAL = "pre_approval"
    POST_APPROVAL = "post_approval"

class HookContext(BaseModel):
    portal_id: str | None = None
    agent_name: str | None = None
    action_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    preview_result: dict[str, Any] | None = None
    user_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HookResult(BaseModel):
    allowed: bool = True
    modified_payload: dict[str, Any] | None = None
    message: str | None = None
```

### 3.5 Role Models (`roles.py`)

```python
class RoleConfig(BaseModel):
    user_id: str
    allowed_agents: list[str]
    max_risk_level: RiskLevel
    denied_tools: list[str]
```

---

## 4. API Contracts

### 4.1 HubSpotClient Interface

```python
@dataclass
class APIResponse:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str]

class HubSpotClient:
    BASE_URL = "https://api.hubapi.com"
    _RATE_LIMIT = 100          # requests per 10 seconds
    _BATCH_CONCURRENT = 4      # concurrent batch ops
    _WINDOW_SECONDS = 10
    _REFRESH_BUFFER_SECONDS = 300

    def __init__(self, portal: PortalConfig) -> None
    async def get(path, portal_id, expected_scopes=None) -> APIResponse
    async def post(path, portal_id, body=None, expected_scopes=None) -> APIResponse
    async def patch(path, portal_id, body=None, expected_scopes=None) -> APIResponse
    async def put(path, portal_id, body=None, expected_scopes=None) -> APIResponse
    async def delete(path, portal_id, expected_scopes=None) -> APIResponse
    async def post_files(path, portal_id, data=None, files=None, expected_scopes=None) -> APIResponse
    async def close(self) -> None
```

**Behavior:**
- Rate limiting enforced via `asyncio.Semaphore(100)` with a rolling 10-second window.
- Token refresh on 401 for GET/HEAD only (avoids duplicate side effects on writes).
- 429 raises `RateLimitError` with `retry_after`.
- 403 raises `ScopeError` with `required_scopes` if known.
- Auto-retry for 401 on safe methods after forced token refresh.

### 4.2 Tool Registry Contract

```python
@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable[..., Any]
    is_async: bool

def tool(name: str, description: str) -> Callable[[Callable], Callable]
def get_tool(name: str) -> ToolDef | None
def list_tools() -> list[ToolDef]
async def invoke_tool(name: str, portal_id: str, **kwargs: Any) -> Any
```

**Tool registration pattern:**
```python
from hubspot_agent.tools import tool

@tool("hubspot_get_object", "Retrieve a single HubSpot object by ID")
async def hubspot_get_object(object_type: str, object_id: str, portal_id: str) -> dict:
    ...
```

**Caching behavior in `invoke_tool`:**
- Read tools (determined by `is_read_tool(name)`) are cached in `QueryCache(portal_id)`.
- Write tools invalidate their domain in `QueryCache` after execution.

### 4.3 Orchestrator Dispatch Contract

```python
async def dispatch_agent(
    agent_name: str,
    user_request: str,
    portal_config: PortalConfig,
    mode: str = "preview",        # "preview" | "execute"
    payload: dict[str, Any] | None = None,
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
) -> AgentResult

async def dispatch_agents_parallel(
    agent_names: list[str],
    user_request: str,
    portal_config: PortalConfig,
    mode: str = "preview",
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
) -> list[AgentResult]
```

**Critical gap:** `dispatch_agent()` constructs a prompt string and returns an `AgentResult`. It does **not** invoke Claude Code's `Agent` tool. The skill, as built, cannot execute as a true Claude Code skill.

### 4.4 Routing Contract

```python
def route_request(
    request_text: str,
    llm_response: str | None = None,
    portal_id: str | None = None,
) -> list[str]
```

**Routing algorithm:**
1. If `llm_response` provided, parse as JSON array of agent names.
2. Fast-path keyword match against `_FAST_PATH_KEYWORDS`.
3. Apply per-portal routing overrides from `routing_overrides.json`.
4. Ambiguity rule: primary score must be >= 2x secondary score.
5. If ambiguous, return empty list (caller must use LLM fallback).
6. Dependency ordering via `_STATIC_DEPENDENCIES` (properties before workflows, objects before lists/engagements).

---

## 5. Integration Points

### 5.1 HubSpot API Integration

**Base URL:** `https://api.hubapi.com`

**Authentication methods:**
- **OAuth 2.0:** Authorization code flow (no PKCE). Token endpoint: `POST /oauth/v1/token`.
- **Private App tokens:** Long-lived tokens passed as `Authorization: Bearer <token>`.

**Rate limits enforced client-side:**
- Standard endpoints: 100 requests per 10 seconds (`asyncio.Semaphore(100)`)
- Batch operations: max 4 concurrent (`asyncio.Semaphore(4)`)

**HubSpot API coverage:**
- CRM Objects (contacts, companies, deals, tickets, products, line items, quotes)
- CRM Properties and Schemas
- CRM Pipelines
- CRM Lists (static and dynamic)
- CRM Associations
- CRM Engagements (notes, tasks, emails, meetings, calls)
- Automation Workflows
- Settings Users
- Analytics and Reporting
- Service Hub (tickets, knowledge base, surveys)
- Marketing Hub (campaigns, segments, A/B tests)
- CMS (pages, blogs, files, social)
- Custom Objects
- Webhooks (v1 subscriptions + v3 signature validation)
- Raw API escape-hatch for uncovered endpoints

### 5.2 OAuth Integration

**Flow:**
1. `get_authorization_url(portal_id, scopes)` builds URL with `state=portal_id` (predictable, no PKCE).
2. Browser opens to HubSpot authorization page.
3. Local callback server (`callback_server.py`) listens on `localhost:3000` for `GET /oauth/callback?code=...&state=...`.
4. `exchange_code_for_token()` exchanges code for access/refresh tokens.
5. Tokens saved to `~/.claude/hubspot/<portal_id>.json`.
6. `HubSpotClient` auto-refreshes tokens within 5 minutes of expiry.

**Known gaps:**
- `state` parameter is statically set to `portal_id` (CSRF vulnerability).
- PKCE (`code_challenge`, `code_verifier`) is not implemented.
- Token files written with default umask (typically world-readable).

### 5.3 Webhook Integration

**Server:** aiohttp-based `WebhookServer` bound to `0.0.0.0` (configurable).

**Signature validation:**
- Primary: HubSpot v3 signatures (`X-HubSpot-Signature-v3` + timestamp, 5-minute freshness window).
- Fallback: Legacy `X-HubSpot-Signature` HMAC-SHA256 (vulnerable to replay).

**Event routing:**
```python
_EVENT_ROUTING = {
    "contact": "objects",
    "company": "objects",
    "deal": "objects",
    "ticket": "objects",
    "workflow": "workflows",
    "list": "lists",
    ...
}
```

**Webhook safety:** All webhook-triggered dispatches run in `mode="preview"` requiring human approval before writes.

**Subscription management:** `WebhookSubscriptionManager` creates/deletes subscriptions via `/webhooks/v1/<app_id>/subscriptions`.

**Known gaps:**
- Default bind address `0.0.0.0` with no rate limiting or IP allowlisting.
- No validation that source IPs match HubSpot's published ranges.
- Legacy signature fallback weakens security posture.

---

## 6. Security Considerations

### 6.1 Implemented Security Measures

| Control | Implementation | Status |
|---------|----------------|--------|
| Token isolation | Per-portal token storage (`<portal_id>.json`) | Implemented |
| Scope pre-validation | `validate_scopes()` checks granted scopes before dispatch | Implemented |
| HITL approval | Preview mode for all writes; destructive gate requires count confirmation | Partial (preview works, execute path not wired in CLI) |
| PII redaction | `redaction.py` with off/pii/full levels; applied to trace/ledger writes | Implemented |
| Webhook signature validation | V3 + legacy fallback | Implemented (but fallback is a weakness) |
| Plugin sandbox | Restricted builtins (`open`, `exec`, `eval`, `compile` removed); filtered `__import__` | Implemented (trivially bypassable) |
| Audit trail | Append-only `audit.log` with timestamp, user, action, agent | Implemented |
| Role-based access | `roles.json` per portal with agent/risk/tool restrictions | Implemented (defaults to allow-all) |
| Token refresh | Auto-refresh within 5-minute buffer | Implemented |

### 6.2 Known Security Gaps (Blocker Level)

| Gap | Location | Risk |
|-----|----------|------|
| Predictable OAuth `state` | `auth.py:get_authorization_url()` | CSRF — attacker can forge authorization responses |
| Missing PKCE | `auth.py` | Authorization code interception for public clients |
| World-readable credentials | `config.py:save_portal_config()`, `app_credentials.py` | Local privilege escalation |
| Plugin sandbox bypass | `plugins.py:_load_single_plugin()` | Arbitrary code execution via `__import__`, `getattr`, `__builtins__` |
| Webhook server on `0.0.0.0` | `webhooks.py`, `server.py` | Exposed to network with no rate limiting |
| No portal_id path validation | `config.py` | Path traversal if malicious `portal_id` like `../../../etc/passwd` |
| Hooks fail-open | `hooks.py:run()` | `pre_write` hook exception does not block operation |
| No encryption at rest | `config.py`, `app_credentials.py` | Plaintext token storage |
| RBAC allow-all default | `roles.py:can_dispatch()` | Missing `roles.json` = no restrictions |
| Legacy webhook fallback | `webhooks.py:_handle_webhook()` | Accepts weaker legacy signature if V3 missing |

---

## 7. Performance Requirements and Bottlenecks

### 7.1 Performance Targets (from Spec)

- Simple read queries should return within 10 seconds.
- Rate limits enforced without manual intervention.
- Batch operations auto-chunked at 100 records per batch.

### 7.2 Actual Bottlenecks

| Bottleneck | Location | Impact |
|------------|----------|--------|
| **O(n) atomic append** | `trace.py:emit_trace()`, `ledger.py:_append()` | Reads entire file into memory, appends one line, writes back via temp-file rename. At 50,000 traces, every append is a multi-millisecond full-file rewrite. |
| **Full-file scans** | `trace.py:get_recent_traces(limit=5000)` | Reads entire `traces.jsonl`, parses every line, then slices. Grows linearly with history. |
| **Lost-update race condition** | `trace.py`, `ledger.py` | Temp-file-rename is atomic for readers but not across concurrent writers. Two concurrent appends can result in one being lost. |
| **Cache write vulnerability** | `cache.py`, `query_cache.py`, `capabilities.py` | Write directly to target files without temp-file rename or file locking. Killed mid-write = corrupted cache. |
| **No LRU/size cap on caches** | `query_cache.json`, `schema_cache.json` | Rewritten in full on every mutation. No TTL garbage collection, size cap, or eviction. |
| **Capability probing latency** | `capabilities.py:probe_portal()` | 7 sequential HTTP calls, each wrapped in bare `except Exception: pass`. Adds significant cold-start latency. |
| **No per-request latency budget** | `orchestrator.py` | 10-second target exists in spec but no enforcement in code. |
| **No cost ceiling** | `trace.py` | Tracks `token_count` and `estimated_usd` but has no per-request, per-session, or per-portal hard stop. |

### 7.3 File I/O Performance Summary

For the intended use case (single-user Claude Code skill), flat-file persistence is reasonable. However, the read-modify-write append pattern on `traces.jsonl` and `action_log.jsonl` will degrade measurably after ~10,000 entries. Recommend true append-mode writes with file locking, or per-day rotation.

---

## 8. Deployment Strategy

### 8.1 As a Claude Code Skill

The codebase is structured as a Python package `hubspot_agent` under `src/`. It is **not** currently deployable as a Claude Code skill because:

1. **No `Agent` tool invocation:** The orchestrator returns prompt objects and `AgentResult` dataclasses rather than dispatching via Claude Code's native `Agent` tool.
2. **CLI entry point only:** `cli.py` provides `hubspot_command()` for direct Python invocation. There is no skill manifest or `claude.md` skill definition.
3. **Standalone dependencies:** Requires `httpx`, `pydantic`, `aiohttp` — standard Python packages, but must be available in the Claude Code environment.

### 8.2 Installation (as implemented)

```bash
# Install package
pip install -e .

# Configure portal
/hubspot setup <portal_id> oauth
# or
/hubspot setup <portal_id> token <private-app-token>

# Run requests
/hubspot "find duplicate contacts"

# Run webhook server (optional)
python -m hubspot_agent.server --host 127.0.0.1 --port 8080
```

### 8.3 File-Based State Layout

All state stored under `~/.claude/hubspot/<portal_id>/`:

```
~/.claude/hubspot/
|-- <portal_id>.json              # Portal config (token, tier, scopes)
|-- <portal_id>.token             # Legacy token file
|-- app_credentials.json          # OAuth client_id/client_secret/app_id
|-- <portal_id>/
|   |-- schema_cache.json         # Object schema metadata (1h TTL)
|   |-- query_cache.json          # Read result cache (5m TTL)
|   |-- capabilities.json         # Probed capability matrix
|   |-- action_log.jsonl          # Idempotency ledger
|   |-- traces.jsonl              # Structured traces
|   |-- audit.log                 # Append-only audit trail
|   |-- roles.json                # RBAC configuration
|   |-- hooks.json                # Hook handler registrations
|   |-- routing_overrides.json    # Per-portal routing rules
|   |-- baselines.json            # Anomaly detection baselines
|   |-- sessions/*.json           # Session memory files
|   |-- progress/*.json           # Progress tracker files
|   |-- undo_snapshots/*.json     # Pre-write snapshots
|   |-- in_flight/*.jsonl         # Checkpoint in-flight
|   |-- completed/*.jsonl         # Checkpoint completed
```

### 8.4 Portal Auto-Detection

- Reads `.hubspot-portal` file in working directory (single line with portal ID).
- No validation of file permissions or contents.
- File created world-readable.

---

## 9. Tech Stack Justification

### 9.1 Selected Stack

| Component | Choice | Justification |
|-----------|--------|---------------|
| Language | Python 3.12+ | Spec requirement; async/await for concurrent API calls |
| HTTP client | `httpx` | Async-first, compatible with `HubSpotClient` from agent2 project |
| Data validation | `pydantic` | Used pervasively for models, config, hook contexts |
| Webhook server | `aiohttp` | Async HTTP server for webhook receiver |
| Testing | `pytest`, `pytest-asyncio`, `respx`, `hypothesis` | Standard Python testing; `respx` for HTTP mocking; `hypothesis` for property-based testing |
| Build | `hatchling` | Modern Python packaging |

### 9.2 Reuse from agent2 Project

The spec directed reuse of `HubSpotClient` from `/Users/izzy/Documents/agent2/src/hive/hubspot/client.py`. The implementation built a **new** `HubSpotClient` in `client.py` (200 lines) rather than importing from agent2. The new client maintains the same interface concepts but is a fresh implementation with its own rate-limiting and token-refresh logic.

### 9.3 Absent Technologies (Correctly Avoided)

| Technology | Decision | Rationale |
|------------|----------|-----------|
| LangGraph | Not used | Spec explicitly prohibited custom orchestration frameworks |
| Postgres/MongoDB | Not used | Spec mandated flat-file per-portal state |
| LangChain | Not used | No dependency on external orchestration frameworks |

---

## 10. Known Technical Debt and Risks

### 10.1 Critical Risks

| Risk | Severity | Description |
|------|----------|-------------|
| **Cannot run as a Claude Code skill** | Blocker | The custom orchestrator does not invoke Claude Code's `Agent` tool. The product is a Python CLI library, not a skill. |
| **HITL execute path not wired** | Blocker | `cli.py` only dispatches `mode="preview"`. No mechanism exists in the CLI to present previews, capture approval, and re-dispatch with `mode="execute"`. The core safety mechanism is incomplete end-to-end. |
| **Security vulnerabilities** | Blocker | 5 blocker-level security issues (OAuth CSRF, missing PKCE, world-readable credentials, plugin sandbox bypass, webhook exposure). |
| **Scope creep** | Blocker | Implementation is 40-60% larger than approved MVP. 15 agents vs 11. Every out-of-scope item implemented except external dashboard. |

### 10.2 Architectural Debt

| Debt | Location | Description |
|------|----------|-------------|
| God object | `orchestrator.py` | Imports 30+ modules directly. Handles routing, scope validation, capability probing, HITL, anomaly detection, roles, hooks, sandbox, reflection, and plugins. High coupling, low cohesion. |
| DAG planner over-engineering | `plan.py` | 931 lines for a problem the spec solved with keyword conjunction detection. `_infer_action` and `_has_data_flow` use brittle regex heuristics that hallucinate phantom dependencies. |
| Duplicate JSONL append logic | `trace.py`, `ledger.py`, `checkpoint.py` | Three separate modules implement nearly identical atomic-write patterns. Should be consolidated. |
| Global hook registry | `hooks.py` | Module-level `_DEFAULT_REGISTRY = HookRegistry()`. Hooks loaded for portal A are active for portal B. |
| Reflection normalization masks mismatches | `reflection.py:_normalize_value()` | Coerces strings to booleans, tries `json.loads`, then `int`, `float`, strips whitespace. Semantically different values reported as matching. |
| Anomaly detection measures think time | `anomaly.py` | Computes "duration" as `(last_event.timestamp - first_event.timestamp)`, capturing user approval delays and think time rather than actual tool latency. |
| No shared client instance | Multiple | Every cache warm, capability probe, and some tools instantiate and close their own `HubSpotClient`. |

### 10.3 Testing Debt

- 88 test files exist, many testing out-of-scope features.
- Routing regression corpus (`tests/routing_corpus.yaml`) contains only 13 cases covering ~7 agents. Zero cases for 8 of 15 agents.
- No false-positive/negative rates measured for LLM routing.
- No latency budget enforcement tests.
- No cost-ceiling tests.

### 10.4 Recommended Immediate Actions

1. **Decide on product scope:** Either update the spec to match the implementation (platform framework route) or prune the implementation to match the spec (MVP route). Option B is strongly recommended.
2. **Integrate with Claude Code's Agent tool:** The core `dispatch_agent()` function must actually dispatch via the `Agent` tool, not return prompt objects.
3. **Wire HITL execute path in CLI:** `cli.py` must present previews, capture user approval, and handle `mode="execute"`.
4. **Fix file I/O bottlenecks:** Replace full-file-copy atomic append with true append-mode writes or per-day files for `traces.jsonl` and `action_log.jsonl`.
5. **Remove or secure the plugin system:** If plugins are required, run them in a subprocess or use `RestrictedPython` from Zope. At minimum, validate hashes/signatures.
6. **Isolate hooks per portal:** Replace the global `HookRegistry` with a per-portal registry.
7. **Fix OAuth security:** Add cryptographically random `state`, implement PKCE, set `mode=0o600` on credential files.
8. **Replace or constrain DAGPlanner:** Limit compound requests to explicit user confirmation of inferred steps for MVP.
9. **Add per-session token budget:** Hard stop at e.g. $1.00 default.
10. **Tighten reflection value comparison:** Compare raw API values without coercion.

---

## Appendix A: Module Line Counts

```
Total Python modules: 40+
Total lines of Python: ~6,946

Largest modules:
- orchestrator.py     ~1,017 lines
- plan.py              ~931 lines
- cli.py               ~393 lines
- webhooks.py          ~371 lines
- client.py            ~200 lines
- hooks.py             ~180 lines
- tools/objects.py     ~170 lines
- validation.py        ~160 lines
- cache.py             ~150 lines
- trace.py             ~240 lines
```

## Appendix B: Agent-to-Tool Mapping

| Agent | Tool Count | Write Tools |
|-------|-----------|-------------|
| objects | 6 | create, update, delete, batch_upsert |
| properties | 5 | create, update, delete |
| workflows | 6 | create, update, enroll, toggle |
| lists | 6 | create, update, add_to, remove_from |
| pipelines | 5 | create, update, reorder_stages |
| users | 5 | create, update, deactivate |
| hygiene | 4 | merge, bulk_update |
| analytics | 3 | None (read-only) |
| associations | 4 | create_schema, associate, disassociate |
| engagements | 7 | create_note, create_task, create_email, create_meeting, create_call |
| raw_api | 1 | All HTTP methods via raw_api |
| service | ~4 | create, update, delete |
| marketing | ~4 | create, update, delete |
| cms | ~4 | create, update, delete |
| custom_objects | ~4 | create, update, delete |

## Appendix C: Routing Keyword Map (Fast Path)

```python
_FAST_PATH_KEYWORDS = {
    "objects": ["contact", "company", "deal", "ticket"],
    "properties": ["property", "field", "schema", "custom field"],
    "workflows": ["workflow", "automation", "enroll", "trigger"],
    "lists": ["list", "segment", "add to list"],
    "engagements": ["note", "task", "meeting", "call", "activity", "log"],
    "service": ["ticket", "knowledge base", "survey", "feedback"],
    "marketing": ["campaign", "segment", "ab test", "suppression list"],
    "cms": ["page", "blog", "file", "social"],
}
```

## Appendix D: Static Dependencies

```python
_STATIC_DEPENDENCIES = {
    "workflows": ["properties"],      # workflows reference properties
    "lists": ["objects"],              # lists reference object filters
    "engagements": ["objects"],      # engagements reference objects
}
```

When multiple agents are dispatched, dependency-ordering ensures upstream agents execute before downstream agents.
