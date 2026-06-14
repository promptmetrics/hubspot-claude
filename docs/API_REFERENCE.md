# HubSpot Admin Agent — Developer API Reference

This reference covers the public Python API for extending the `hubspot_agent` package or building on top of it. All examples assume `from __future__ import annotations` and Python 3.12+.

---

## Table of Contents

1. [Package Overview](#1-package-overview)
2. [Tool Registry](#2-tool-registry)
3. [Agent Prompt System](#3-agent-prompt-system)
4. [Orchestrator API](#4-orchestrator-api)
5. [Models Reference](#5-models-reference)
6. [Client API](#6-client-api)
7. [Auth API](#7-auth-api)
8. [Config API](#8-config-api)
9. [Adding a New Agent](#9-adding-a-new-agent)
10. [Adding a New Tool](#10-adding-a-new-tool)
11. [CLI Entry Point](#11-cli-entry-point)

---

## 1. Package Overview

`hubspot_agent` is a Claude Code skill that administers HubSpot CRM via natural language. The package is organized into three layers:

| Layer | Module Path | Responsibility |
|-------|-------------|----------------|
| **Tools** | `hubspot_agent.tools.*` | Low-level CRUD functions decorated with `@tool`. Each tool is an async function that calls the HubSpot API and returns a `dict`. |
| **Agents** | `hubspot_agent.agents.*` | Prompt builders that assemble a `system_prompt`, tool list, and domain description for a specific HubSpot domain (e.g., objects, workflows). |
| **Orchestrator** | `hubspot_agent.orchestrator` | Intent parsing, request routing, preview generation, and agent dispatch (sequential or parallel). |
| **Client** | `hubspot_agent.client` | Async HTTP client with automatic rate limiting and OAuth token refresh. |
| **Models** | `hubspot_agent.models` | Pydantic models for intents, previews, results, and execution plans. |

### Key Design Decisions

- Sub-agents are **stateless**. The orchestrator passes `proposed_payload` in the re-dispatch prompt.
- All write operations require human-in-the-loop approval. There is no dry-run API in HubSpot; previews are read-based reconstructions.
- Rate limiting is enforced client-side (100 requests / 10 seconds) with an async semaphore.
- Authentication supports OAuth 2.0 (PKCE) and Private App tokens.

---

## 2. Tool Registry

Tools are the atomic units of HubSpot API interaction. Every tool is an async function registered via the `@tool` decorator.

### `@tool(name, description)`

Decorator that registers a function in the global tool registry.

```python
from hubspot_agent.tools import tool

@tool(name="my_custom_tool", description="Does something useful.")
async def my_custom_tool(portal_id: str, client: HubSpotClient, **kwargs) -> dict[str, Any]:
    ...
```

**Parameters:**
- `name` (`str`, required) — Unique identifier used when invoking the tool.
- `description` (`str`, required) — Human-readable description injected into agent prompts.

**Returns:** The original function, unmodified.

**Notes:**
- Registration happens at import time. The module containing the tool must be imported before `list_tools()` is called.
- The decorator introspects the function with `inspect.iscoroutinefunction`. Only async functions should perform I/O.

### `ToolDef`

```python
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable[..., Any]
    is_async: bool
```

Dataclass stored in the global registry. `is_async` is auto-detected by the decorator.

### `registry: dict[str, ToolDef]`

Global mutable mapping of tool name to `ToolDef`. Direct mutation is discouraged; use the `@tool` decorator.

### `get_tool(name: str) -> ToolDef | None`

Lookup a registered tool by name.

```python
from hubspot_agent.tools import get_tool

tool_def = get_tool("hubspot_search_objects")
print(tool_def.description)
```

### `list_tools() -> list[ToolDef]`

Return all registered tools.

```python
from hubspot_agent.tools import list_tools

for t in list_tools():
    print(f"{t.name}: {t.description}")
```

### `invoke_tool(name: str, portal_id: str, **kwargs: Any) -> Any`

Execute a registered tool by name.

**Parameters:**
- `name` (`str`, required) — Tool name.
- `portal_id` (`str`, required) — Passed positionally for routing/logging.
- `**kwargs` — Forwarded to the tool function. Must include `client` and any domain-specific arguments.

**Returns:** The raw return value of the tool function (typically a `dict`).

**Raises:**
- `ValueError` — Tool not found in registry.
- `HubSpotError`, `RateLimitError`, `ScopeError` — Bubbled up from the underlying tool (if not caught internally).

```python
from hubspot_agent.tools import invoke_tool
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import load_portal_config

portal = load_portal_config("12345")
client = HubSpotClient(portal)
result = await invoke_tool(
    "hubspot_search_objects",
    "12345",
    object_type="contacts",
    query={"query": "hello", "limit": 10},
    client=client,
    portal_id="12345",
)
```

---

## 3. Agent Prompt System

An **agent** is a domain-specific prompt builder. It does not hold state; it produces an `AgentPrompt` dataclass that the orchestriator dispatches to an LLM.

### `AgentPrompt`

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AgentPrompt:
    agent_name: str
    system_prompt: str
    tool_names: list[str] = field(default_factory=list)
    domain_description: str = ""
```

**Fields:**
- `agent_name` (`str`) — Display name (e.g., "Objects Agent").
- `system_prompt` (`str`) — Full system prompt including tool descriptions, portal context, and instruction blocks.
- `tool_names` (`list[str]`) — Names of tools available to this agent.
- `domain_description` (`str`) — Short paragraph describing the agent's domain.

### `build_agent_prompt(...)`

```python
def build_agent_prompt(
    agent_name: str,
    domain_description: str,
    available_tools: list[ToolDef],
    portal_config: PortalConfig | None = None,
) -> AgentPrompt
```

Assemble a complete `AgentPrompt` from parts.

**Parameters:**
- `agent_name` (`str`, required) — Human-readable agent name.
- `domain_description` (`str`, required) — Domain narrative inserted after the role line.
- `available_tools` (`list[ToolDef]`, required) — Tools to include in the prompt.
- `portal_config` (`PortalConfig | None`) — If provided, appends portal ID and tier to the prompt.

**Returns:** `AgentPrompt`

**Behavior:**
- Automatically appends `SELF_CORRECTION_PROMPT_BLOCK` to every prompt.
- Appends `REFLECTION_PROMPT_BLOCK` only if `available_tools` contains any write-oriented tool (matched by substring: `create`, `update`, `delete`, `batch`).

### Prompt Blocks

#### `SELF_CORRECTION_PROMPT_BLOCK: str`

Injected into every agent prompt. Instructs the LLM to retry on `VALIDATION`, `CONFLICT`, and `NOT_FOUND` errors, and to return a corrected payload as structured JSON with `status: "corrected"`.

#### `REFLECTION_PROMPT_BLOCK: str`

Injected when write tools are present. Instructs the LLM to re-fetch and verify any record mutated by `CREATE`, `UPDATE`, or `BATCH` operations before reporting success.

### Agent Registry

#### `_AGENT_REGISTRY: dict[str, Callable[..., AgentPrompt]]`

Global mapping of agent key (e.g., `"objects"`) to a prompt builder function. Defined in `hubspot_agent.agents.__init__`.

#### `get_agent_prompt(agent_name: str, portal_config=None) -> AgentPrompt | None`

Look up and invoke a registered agent builder.

```python
from hubspot_agent.agents import get_agent_prompt

prompt = get_agent_prompt("objects", portal_config=portal_config)
print(prompt.system_prompt[:200])
```

#### `list_agent_names() -> list[str]`

Return all registered agent keys.

```python
from hubspot_agent.agents import list_agent_names
print(list_agent_names())
# ['objects', 'properties', 'workflows', 'lists', ...]
```

---

## 4. Orchestrator API

The orchestrator is the central router. It decides which agents to run, builds previews, and dispatches execution.

### `route_request(request_text: str, portal_id: str | None = None) -> list[str]`

Keyword-based routing with conjunction detection.

**Parameters:**
- `request_text` (`str`, required) — Natural language request from the user.
- `portal_id` (`str | None`) — Used for custom object fast-path lookups.

**Returns:** `list[str]` — Ordered list of agent keys to dispatch. Empty list means no match.

**Behavior:**
- Scores the request against keyword maps for each agent domain.
- Detects conjunctions (` and `, ` then `, ` followed by `). If two distinct domains score closely, both are returned in dependency order.
- Dependencies are resolved so prerequisites run first (e.g., `properties` before `workflows`).

```python
from hubspot_agent.orchestrator import route_request

agents = route_request("Find contacts in Seattle and create a workflow for them", portal_id="12345")
print(agents)  # ['objects', 'workflows']
```

### `dispatch_agent(...)`

```python
async def dispatch_agent(
    agent_name: str,
    request_text: str,
    portal_config,
    mode: str = "preview",
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
    proposed_payload: dict[str, Any] | None = None,
) -> AgentResult
```

Dispatch a single agent in preview or execute mode.

**Parameters:**
- `agent_name` (`str`, required) — Key from `_AGENT_REGISTRY`.
- `request_text` (`str`, required) — Original user request.
- `portal_config` (`PortalConfig`, required) — Authenticated portal configuration.
- `mode` (`str`) — `"preview"` (default) or `"execute"`.
- `trace_id` (`str | None`) — Optional trace ID for observability.
- `batch_mode` (`BatchApprovalMode`) — Approval granularity. Default `SINGLE`.
- `proposed_payload` (`dict | None`) — Payload from a prior preview or correction cycle.

**Returns:** `AgentResult`

**Behavior:**
- In `"preview"` mode, parses intent, builds a `PreviewResult`, stores it to disk under `~/.claude/hubspot/<portal_id>/pending_previews/`, and returns a summary.
- In `"execute"` mode, routes to the appropriate tool calls based on parsed intent (currently hard-pathed for the `objects` agent; extensible in future phases).

### `dispatch_agents_parallel(...)`

```python
async def dispatch_agents_parallel(
    agent_names: list[str],
    request_text: str,
    portal_config,
    mode: str = "preview",
    trace_id: str | None = None,
    batch_mode: BatchApprovalMode = BatchApprovalMode.SINGLE,
    proposed_payload: dict[str, Any] | None = None,
) -> list[AgentResult]
```

Dispatch multiple agents concurrently using `asyncio.gather`.

**Parameters:** Same as `dispatch_agent`, except `agent_names` is a list.

**Returns:** `list[AgentResult]` — One result per agent, in the same order as `agent_names`.

### `parse_batch_mode(request: str) -> tuple[BatchApprovalMode, str]`

Parse batch approval keywords (`--batch`, `approve all`) from raw request text.

**Returns:** `(mode, cleaned_request)`

### `check_dispatch_readiness(agent_names: list[str], portal_config) -> dict[str, Any]`

Validate that the portal's subscription tier supports the requested agents.

**Returns:**
```python
{"ready": True}
# or
{"ready": False, "decline_reason": "workflows: workflows; users: users"}
```

### Internal Helpers

#### `_parse_agent_intent(agent_name: str, request_text: str) -> TaskIntent`

Keyword-based intent parser. Detects `search`, `create`, `update`, `delete`, and `unknown` intents, assigns `RiskLevel`, and extracts target object types for the `objects` agent.

#### `_build_preview_for_intent(...)`

```python
async def _build_preview_for_intent(
    agent_name: str,
    intent: TaskIntent,
    client: HubSpotClient,
    portal_id: str,
) -> PreviewResult
```

Builds a read-based preview. For `objects` agent, performs a live search to estimate impact count.

### Preview, Trace, and Capability Helpers

#### `format_preview(...)`

```python
def format_preview(
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    impact_count: int,
    mode: str = "diff",
) -> str
```

Render a markdown preview string. `mode="diff"` shows per-field diffs for the first 10 records plus a pattern summary for the remainder.

#### `emit_trace(portal_id, event_type, trace_id, data)`

```python
def emit_trace(
    portal_id: str,
    event_type: str,
    trace_id: str,
    data: dict[str, Any],
) -> None
```

Append a trace event to `~/.claude/hubspot/<portal_id>/traces.jsonl`. `event_type` must be one of:
`request_received`, `webhook_received`, `route_decision`, `tool_call`, `approval`, `completion`, `error`, `reflection`.

#### `compute_status_aggregates(portal_id, window_hours=24) -> dict[str, Any]`

Compute aggregate stats from traces: `total_requests`, `avg_latency_ms`, `total_estimated_usd`, `tool_call_counts`, `error_rate`.

---

## 5. Models Reference

All models are Pydantic `BaseModel` subclasses (except where noted).

### `RiskLevel(str, Enum)`

```python
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"
```

### `BatchApprovalMode(str, Enum)`

```python
class BatchApprovalMode(str, Enum):
    SINGLE = "single"
    BATCH = "batch"
    PATTERN = "pattern"
```

### `TaskIntent`

```python
class TaskIntent(BaseModel):
    intent_type: str
    target_object: str | None = None
    description: str
    risk_level: RiskLevel
    estimated_impact: int | None = None
    required_scopes: list[str] = Field(default_factory=list)
```

**Fields:**
- `intent_type` — `search`, `create`, `update`, `delete`, or `unknown`.
- `target_object` — For the `objects` agent: `contacts`, `companies`, `deals`, `tickets`.
- `risk_level` — Auto-assigned: `search` -> `LOW`, `create`/`update` -> `MEDIUM`, `delete` -> `DESTRUCTIVE`.
- `estimated_impact` — `1` for write intents, `None` for reads.

### `PreviewResult`

```python
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
```

### `AgentResult`

```python
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

### `PlanStep`

```python
class PlanStep(BaseModel):
    step_number: int
    agent: str
    action: str
    hubspot_endpoint: str | None = None
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    validation_rules: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
```

### `ExecutionPlan`

```python
class ExecutionPlan(BaseModel):
    plan_id: str
    thread_id: str
    steps: list[PlanStep]
    overall_risk: RiskLevel
    rollback_available: bool
    estimated_duration_seconds: int
```

---

## 6. Client API

### `APIResponse`

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class APIResponse:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str]
```

### `HubSpotClient`

Async HTTP client with client-side rate limiting and automatic OAuth token refresh.

```python
class HubSpotClient:
    BASE_URL = "https://api.hubapi.com"
```

**Constructor:**

```python
client = HubSpotClient(portal: PortalConfig)
```

**Internal Limits:**
- `_RATE_LIMIT` = 100 requests per 10 seconds
- `_BATCH_CONCURRENT` = 4 concurrent batch requests
- `_REFRESH_BUFFER_SECONDS` = 300 (refresh token if within 5 minutes of expiry)

### Methods

#### `async get(path, portal_id, expected_scopes=None) -> APIResponse`

Perform a GET request.

**Parameters:**
- `path` (`str`, required) — API path (e.g., `/crm/v3/objects/contacts`).
- `portal_id` (`str`, required) — Portal ID for scope validation and logging.
- `expected_scopes` (`list[str] | None`) — Scopes required for this endpoint. Used to raise `ScopeError` on 403.

#### `async post(path, portal_id, body=None, expected_scopes=None) -> APIResponse`

Perform a POST request.

**Parameters:**
- `body` (`dict | None`) — JSON payload.
- Other parameters same as `get`.

#### `async patch(path, portal_id, body=None, expected_scopes=None) -> APIResponse`

Perform a PATCH request.

#### `async put(path, portal_id, body=None, expected_scopes=None) -> APIResponse`

Perform a PUT request.

#### `async delete(path, portal_id, expected_scopes=None) -> APIResponse`

Perform a DELETE request.

#### `async post_files(path, portal_id, data=None, files=None, expected_scopes=None) -> APIResponse`

Multipart POST for file uploads.

**Parameters:**
- `data` (`dict | None`) — Form fields.
- `files` (`dict | None`) — File attachments forwarded to `httpx`.

#### `async close() -> None`

Close the underlying `httpx.AsyncClient`.

**Usage Pattern:**

```python
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import load_portal_config

portal = load_portal_config("12345")
client = HubSpotClient(portal)
try:
    resp = await client.get("/crm/v3/objects/contacts/12345", portal_id="12345")
    print(resp.body)
finally:
    await client.close()
```

### Error Types

All client methods raise subclasses of `HubSpotError` on non-2xx responses.

#### `HubSpotError(Exception)`

```python
class HubSpotError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        category: ErrorCategory | None = None,
        field_errors: list[dict] | None = None,
    )
```

**Attributes:**
- `status_code` (`int | None`) — HTTP status code.
- `category` (`ErrorCategory`) — `VALIDATION`, `AUTH`, `SCOPE`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMIT`, `SERVER`, `UNKNOWN`.
- `field_errors` (`list[dict] | None`) — HubSpot field-level validation errors (400 only).

#### `RateLimitError(HubSpotError)`

Raised on HTTP 429. Attribute: `retry_after: int | None`.

#### `ScopeError(HubSpotError)`

Raised on HTTP 403 when expected scopes are provided. Attribute: `required_scopes: list[str]`.

---

## 7. Auth API

Implements OAuth 2.0 with PKCE.

### `get_authorization_url(portal_id, scopes, redirect_uri) -> str`

Generate the HubSpot OAuth authorization URL.

**Parameters:**
- `portal_id` (`str`, required)
- `scopes` (`list[str]`, required) — OAuth scopes to request.
- `redirect_uri` (`str`) — Default: `http://localhost:3000/oauth/callback`.

**Returns:** `str` — Full authorization URL.

**Raises:** `ValueError` if app credentials are not saved.

```python
from hubspot_agent.auth import get_authorization_url

url = get_authorization_url("12345", scopes=["crm.objects.contacts.read"])
```

### `async exchange_code_for_token(portal_id, code, state, redirect_uri) -> dict[str, Any]`

Exchange an authorization code for access and refresh tokens.

**Parameters:**
- `code` (`str`, required) — Authorization code from callback.
- `state` (`str`, required) — State parameter from callback.
- `redirect_uri` (`str`) — Must match the value used in `get_authorization_url`.

**Returns:** Raw token response body (contains `access_token`, `refresh_token`, `expires_in`).

**Raises:** `ValueError` on invalid/expired state or missing credentials.

### `async refresh_access_token(portal_id, refresh_token) -> dict[str, Any]`

Refresh an access token using a refresh token.

**Returns:** Token response body. Also persists the new token to disk via `save_portal_config`.

### `async get_valid_token(portal_id) -> str | None`

Return a valid access token, refreshing automatically if within the 5-minute buffer.

**Returns:** Token string, or `None` if portal not configured or refresh impossible.

### App Credentials

#### `save_app_credentials(client_id, client_secret, app_id=None) -> None`

Persist HubSpot app credentials to `~/.claude/hubspot/app_credentials.json` (mode `0o600`).

#### `load_app_credentials() -> dict[str, Any] | None`

Load app credentials from disk.

#### `get_client_id() -> str | None`

#### `get_client_secret() -> str | None`

Convenience accessors.

---

## 8. Config API

### `PortalConfig`

```python
from dataclasses import dataclass
from typing import Any

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

### `CONFIG_DIR`

```python
CONFIG_DIR = Path.home() / ".claude" / "hubspot"
```

### `save_portal_config(portal: PortalConfig) -> None`

Serialize a portal config to `~/.claude/hubspot/<portal_id>.json` with mode `0o600`. Also removes legacy `.token` files to avoid ambiguity.

### `load_portal_config(portal_id: str) -> PortalConfig | None`

Load a portal config. Resolution order:
1. JSON config file (`<portal_id>.json`)
2. Environment variable `HUBSPOT_TOKEN_<portal_id>`
3. Legacy `.token` file (`<portal_id>.token`)

**Raises:** `ValueError` if `portal_id` is empty or non-numeric.

### `detect_default_portal(working_dir: str) -> str | None`

Read the first line of `<working_dir>/.hubspot-portal` and return it as the default portal ID.

```python
from hubspot_agent.config import detect_default_portal

portal_id = detect_default_portal(".")
```

### Schema Cache

#### `SchemaCache`

Disk-backed cache for HubSpot object schemas (properties and custom object names).

```python
class SchemaCache:
    TTL_SECONDS = 3600  # 1 hour

    def __init__(self, portal_id: str, base_dir: Path | None = None) -> None
```

**Methods:**
- `get(domain: str) -> dict[str, Any] | None` — Fetch cached schema if not expired.
- `set(domain: str, data: dict[str, Any]) -> None` — Store schema with timestamp.
- `invalidate(domain: str) -> None` — Remove a domain from cache.
- `refresh_all() -> None` — Clear entire cache.
- `list_custom_object_names() -> list[str]` — Return non-standard, non-expired cached object names.

#### `async warm_standard_schemas(portal_config: PortalConfig) -> SchemaCache`

Fetch and cache properties for `contacts`, `companies`, `deals`, `tickets`.

#### `async discover_custom_schemas(portal_config: PortalConfig) -> list[str]`

Fetch all custom object schemas from `/crm/v3/schemas` and cache them. Returns list of custom object type names.

---

## 9. Adding a New Agent

Agents are pure prompt builders. To add a new domain:

### Step 1: Create a tool module (if needed)

If the new agent requires new HubSpot operations, create `src/hubspot_agent/tools/<domain>.py` and register tools with `@tool`.

```python
from hubspot_agent.tools import tool
from hubspot_agent.client import HubSpotClient

@tool(name="hubspot_new_operation", description="...")
async def hubspot_new_operation(
    param: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    resp = await client.post("/crm/v3/...", portal_id=portal_id, body={"param": param})
    return resp.body
```

Import the module in `src/hubspot_agent/tools/__init__.py` so registration runs at package load:

```python
import hubspot_agent.tools.new_domain  # noqa: F401
```

### Step 2: Create the agent prompt builder

Create `src/hubspot_agent/agents/<domain>.py`:

```python
from hubspot_agent.agents._base import AgentPrompt, build_agent_prompt
from hubspot_agent.tools import get_tool

_TOOL_NAMES = [
    "hubspot_new_operation",
    # ...
]

_DOMAIN = (
    "You manage X in HubSpot. You can create, update, delete, and list X records."
)


def get_new_domain_agent_prompt(portal_config=None) -> AgentPrompt:
    tools = [t for name in _TOOL_NAMES if (t := get_tool(name)) is not None]
    return build_agent_prompt(
        agent_name="New Domain Agent",
        domain_description=_DOMAIN,
        available_tools=tools,
        portal_config=portal_config,
    )
```

### Step 3: Register the agent

In `src/hubspot_agent/agents/__init__.py`:

```python
from hubspot_agent.agents.new_domain import get_new_domain_agent_prompt

_AGENT_REGISTRY: dict[str, Callable[..., AgentPrompt]] = {
    # ...existing agents...
    "new_domain": get_new_domain_agent_prompt,
}
```

### Step 4: Add routing keywords

In `src/hubspot_agent/orchestrator.py`, add keywords to the `keywords` dict inside `route_request`:

```python
keywords = {
    # ...existing domains...
    "new_domain": ["new_domain_keyword", "related_term"],
}
```

### Step 5: Add capability requirements (optional)

If the domain requires a specific HubSpot tier, add to `capabilities.py`:

```python
_AGENT_CAPABILITY_REQUIREMENTS: dict[str, list[str]] = {
    # ...existing...
    "new_domain": ["marketing"],
}
```

---

## 10. Adding a New Tool

Tools are the only place HubSpot API calls happen. Follow this pattern:

### Step 1: Define the tool function

In `src/hubspot_agent/tools/<domain>.py` (or a new module):

```python
from __future__ import annotations
from typing import Any
from hubspot_agent.tools import tool
from hubspot_agent.client import HubSpotClient
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError

@tool(
    name="hubspot_do_something",
    description="Brief, active-voice description of what this tool does.",
)
async def hubspot_do_something(
    object_id: str,
    properties: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    try:
        resp = await client.patch(
            f"/crm/v3/objects/contacts/{object_id}",
            portal_id=portal_id,
            body={"properties": properties},
            expected_scopes=["crm.objects.contacts.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_do_something"}
```

**Rules:**
- Accept `client: HubSpotClient` and `portal_id: str` as keyword arguments.
- Catch `HubSpotError`, `RateLimitError`, and `ScopeError` and return structured error dicts rather than raising into the LLM context.
- Use `expected_scopes` on every client call so the orchestrator can surface scope errors accurately.

### Step 2: Ensure the module is imported

The `@tool` decorator registers at import time. Make sure the module is imported when the package loads:

```python
# In src/hubspot_agent/tools/__init__.py or agent module
import hubspot_agent.tools.your_domain  # noqa: F401
```

### Step 3: Reference the tool in an agent

Add the tool name to the `_TOOL_NAMES` list in the agent builder so it appears in the agent's prompt:

```python
_TOOL_NAMES = [
    "hubspot_do_something",
    # ...
]
```

---

## 11. CLI Entry Point

The CLI is a single sync function designed to be called by Claude Code's slash-command handler.

### `hubspot_command(request: str, working_dir: str = ".") -> str`

Process a HubSpot admin request and return a markdown-formatted response string.

**Parameters:**
- `request` (`str`, required) — Raw user input (e.g., `"find contacts in Seattle"`).
- `working_dir` (`str`) — Directory to resolve `.hubspot-portal` from. Default: current directory.

**Returns:** `str` — Markdown response for display to the user. Possible statuses:
- Preview ready (includes `action_id`, risk level, impact count, and approval instructions)
- Error message (missing portal, missing token, no matching agents, etc.)
- Success message (after execution)

**Internal Routing:**

| Prefix | Handler |
|--------|---------|
| `portal ` | Portal auth, switch, token, list commands |
| `refresh` | Invalidate schema cache |
| `status` | Show 24-hour aggregate stats |
| `setup` | Initialize portal with OAuth or Private App token |
| `approve ` | Approve a pending preview by action ID |
| `y`, `yes` | Approve the most recent pending preview |
| `n`, `no`, `reject` | Reject the most recent pending preview |
| (default) | Route to agents, preview, or execute |

**Example:**

```python
from hubspot_agent.cli import hubspot_command

response = hubspot_command("find contacts in Seattle", working_dir=".")
print(response)
```

**Typical Output (Preview):**

```markdown
📍 Portal: 12345 (enterprise)

**Routing to:** objects

### objects
⚠️  Preview (action: a1b2c3d4)
Risk: low
Impact: 3 records

**Impact:** 3 records

Approve with `y` or `approve <id>`, reject with `n`.
```

---

## Appendix: Module Index

| Module | Public API |
|--------|------------|
| `hubspot_agent.tools` | `@tool`, `ToolDef`, `get_tool`, `list_tools`, `invoke_tool` |
| `hubspot_agent.agents` | `AgentPrompt`, `build_agent_prompt`, `get_agent_prompt`, `list_agent_names` |
| `hubspot_agent.orchestrator` | `route_request`, `dispatch_agent`, `dispatch_agents_parallel`, `parse_batch_mode`, `check_dispatch_readiness` |
| `hubspot_agent.models` | `TaskIntent`, `PreviewResult`, `AgentResult`, `PlanStep`, `ExecutionPlan`, `RiskLevel`, `BatchApprovalMode` |
| `hubspot_agent.client` | `HubSpotClient`, `APIResponse` |
| `hubspot_agent.auth` | `get_authorization_url`, `exchange_code_for_token`, `refresh_access_token`, `get_valid_token` |
| `hubspot_agent.config` | `PortalConfig`, `CONFIG_DIR`, `save_portal_config`, `load_portal_config`, `detect_default_portal` |
| `hubspot_agent.app_credentials` | `save_app_credentials`, `load_app_credentials` |
| `hubspot_agent.cache` | `SchemaCache`, `warm_standard_schemas`, `discover_custom_schemas` |
| `hubspot_agent.capabilities` | `CapabilityMatrix`, `probe_portal`, `has_capability`, `validate_capabilities` |
| `hubspot_agent.preview` | `format_preview`, `render_field_diff`, `render_pattern_summary` |
| `hubspot_agent.trace` | `emit_trace`, `compute_status_aggregates`, `new_trace_id`, `TraceEvent`, `TraceSummary` |
| `hubspot_agent.errors` | `HubSpotError`, `RateLimitError`, `ScopeError`, `ErrorCategory` |
| `hubspot_agent.cli` | `hubspot_command` |
