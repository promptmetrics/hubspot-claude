# HubSpot CRM Admin Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill (`/hubspot`) that dispatches 11 specialist sub-agents to administer HubSpot CRM via natural language, with mandatory HITL approval for all writes.

**Architecture:** Python-based skill with a shared `HubSpotClient` (async HTTP + rate limiting), ~50 tools organized by domain, 11 sub-agent prompt definitions, a parent orchestrator for routing and HITL, and a skill entry point. Reuses battle-tested `HubSpotClient` patterns from the existing `agent2` project.

**Tech Stack:** Python 3.12+, `httpx`, `pydantic`, `pytest`, `pytest-asyncio`. No LangGraph, no custom orchestration framework — Claude Code's native `Agent` tool handles sub-agent dispatch.

**Spec reference:** `docs/superpowers/specs/2026-05-06-hubspot-agent-design.md`

---

## File Structure

```
/Users/izzy/Documents/hubspot/
├── pyproject.toml
├── .gitignore
├── src/
│   └── hubspot_agent/
│       ├── __init__.py
│       ├── cli.py                 # Skill entry point (/hubspot command)
│       ├── config.py              # Portal config, auth, .hubspot-portal detection
│       ├── client.py              # HubSpotClient (async HTTP, rate limits, retries)
│       ├── errors.py              # Custom exceptions (HubSpotError, RateLimitError, ScopeError)
│       ├── models.py              # Pydantic models (TaskIntent, ExecutionPlan, PreviewResult, etc.)
│       ├── tools/
│       │   ├── __init__.py        # Tool registry, shared decorators
│       │   ├── objects.py         # 7 tools: get, search, create, update, delete, batch_upsert
│       │   ├── properties.py      # 5 tools: get, list, create, update, delete property
│       │   ├── workflows.py       # 6 tools: get, list, create, update, enroll, toggle workflow
│       │   ├── lists.py           # 6 tools: get, list, create, update, add, remove from list
│       │   ├── pipelines.py       # 5 tools: get, list, create, update, reorder pipeline
│       │   ├── users.py           # 5 tools: get, list, create, update, deactivate user
│       │   ├── hygiene.py         # 4 tools: find_duplicates, merge_objects, bulk_update, preview_segment
│       │   ├── analytics.py       # 3 tools: get_report, calculate_metrics, pipeline_velocity
│       │   ├── associations.py    # 4 tools: get/create schema, associate/disassociate records
│       │   ├── engagements.py     # 7 tools: get, search, create note/task/email/meeting/call
│       │   └── raw_api.py         # 1 tool: hubspot_raw_api escape-hatch
│       ├── agents/
│       │   ├── __init__.py        # Agent registry, dispatch helpers
│       │   ├── _base.py           # Base agent prompt builder, shared agent logic
│       │   ├── objects.py         # ObjectsAgent system prompt + tool binding
│       │   ├── properties.py      # PropertiesAgent system prompt + tool binding
│       │   ├── workflows.py       # WorkflowsAgent system prompt + tool binding
│       │   ├── lists.py           # ListsAgent system prompt + tool binding
│       │   ├── pipelines.py       # PipelinesAgent system prompt + tool binding
│       │   ├── users.py           # UsersAgent system prompt + tool binding
│       │   ├── hygiene.py         # HygieneAgent system prompt + tool binding
│       │   ├── analytics.py       # AnalyticsAgent system prompt + tool binding
│       │   ├── associations.py    # AssociationsAgent system prompt + tool binding
│       │   ├── engagements.py     # EngagementsAgent system prompt + tool binding
│       │   └── raw_api.py         # RawAPIAgent system prompt + tool binding
│       └── orchestrator.py        # Parent: routing, HITL approval, state passing, scope validation
├── tests/
│   ├── conftest.py                # Shared fixtures (test client, mock portal)
│   ├── test_client.py             # HubSpotClient tests
│   ├── test_tool_registry.py      # Tool registry tests
│   ├── test_tools_objects.py      # Objects tool tests
│   ├── test_tools_properties.py   # Properties tool tests
│   ├── test_tools_workflows.py    # Workflow tool tests
│   ├── test_tools_lists.py        # List tool tests
│   ├── test_tools_pipelines.py    # Pipeline tool tests
│   ├── test_tools_users.py        # User tool tests
│   ├── test_tools_hygiene.py      # Hygiene tool tests
│   ├── test_tools_analytics.py    # Analytics tool tests
│   ├── test_tools_associations.py # Association tool tests
│   ├── test_tools_engagements.py  # Engagement tool tests
│   ├── test_tools_raw_api.py      # Raw API tool tests
│   ├── test_agents_base.py        # Base agent builder tests
│   ├── test_agents_objects.py     # ObjectsAgent tests
│   ├── test_orchestrator_routing.py    # Routing tests
│   ├── test_orchestrator_scope.py      # Scope validation tests
│   ├── test_orchestrator_hitl.py       # HITL flow tests
│   ├── test_orchestrator_dispatch.py  # Dispatch helper tests
│   ├── test_orchestrator_timeout.py   # Timeout reconciliation tests
│   ├── test_snapshot.py           # Undo snapshot tests
│   ├── test_cache.py              # Cache tests
│   ├── test_audit.py              # Audit log tests
│   ├── test_cli.py                # CLI tests
│   └── test_integration.py        # End-to-end integration tests
└── docs/
    └── superpowers/
        ├── specs/2026-05-06-hubspot-agent-design.md
        └── plans/2026-05-06-hubspot-agent-plan.md
```

---

## Phase 1: Project Scaffolding

### Task 1: Initialize Python project

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/hubspot_agent/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "hubspot-agent"
version = "0.1.0"
description = "Claude Code skill for HubSpot CRM administration"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "respx>=0.21",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Write .gitignore**

```
.venv/
__pycache__/
*.pyc
.env
*.egg-info/
dist/
.claude/hubspot/
.pytest_cache/
```

- [ ] **Step 3: Write src/hubspot_agent/__init__.py**

```python
"""HubSpot CRM Admin Agent — Claude Code skill."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Install dependencies**

Run: `cd /Users/izzy/Documents/hubspot && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: Successful install, `pytest` available.

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml .gitignore src/hubspot_agent/__init__.py
git commit -m "chore: initialize hubspot-agent project"
```

---

## Phase 2: Shared Infrastructure

### Task 2: Custom exceptions

**Files:**
- Create: `src/hubspot_agent/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write failing test**

```python
def test_hubspot_error_str():
    from hubspot_agent.errors import HubSpotError
    exc = HubSpotError("something failed", status_code=400)
    assert str(exc) == "HubSpotError(400): something failed"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_errors.py -v`
Expected: `ModuleNotFoundError: No module named 'hubspot_agent.errors'`

- [ ] **Step 3: Implement errors.py**

```python
class HubSpotError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def __str__(self) -> str:
        return f"HubSpotError({self.status_code}): {self.message}"


class RateLimitError(HubSpotError):
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ScopeError(HubSpotError):
    def __init__(self, message: str, required_scopes: list[str] | None = None):
        super().__init__(message, status_code=403)
        self.required_scopes = required_scopes or []
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_errors.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/errors.py tests/test_errors.py
git commit -m "feat: add custom exceptions for HubSpot API errors"
```

---

### Task 3: Pydantic models

**Files:**
- Create: `src/hubspot_agent/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
def test_task_intent_creation():
    from hubspot_agent.models import TaskIntent
    intent = TaskIntent(
        intent_type="search_objects",
        target_object="contacts",
        description="find contacts in northeast",
        risk_level="low",
        required_scopes=["crm.objects.contacts.read"],
    )
    assert intent.intent_type == "search_objects"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_models.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement models.py**

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


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


class AgentResult(BaseModel):
    agent_name: str
    status: str  # "success", "error", "preview", "needs_approval"
    data: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    retryable: bool = False
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_models.py -v`
Expected: All model tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/models.py tests/test_models.py
git commit -m "feat: add pydantic models for intent, plan, and results"
```

---

### Task 4: Config and portal detection

**Files:**
- Create: `src/hubspot_agent/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
import os
from pathlib import Path


def test_detect_portal_from_file(tmp_path):
    from hubspot_agent.config import detect_default_portal
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("1234567\n")
    result = detect_default_portal(str(tmp_path))
    assert result == "1234567"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement config.py**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PortalConfig:
    portal_id: str
    token: str
    tier: str = "unknown"
    scopes_granted: list[str] | None = None


CONFIG_DIR = Path.home() / ".claude" / "hubspot"


def _ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def detect_default_portal(working_dir: str) -> str | None:
    portal_file = Path(working_dir) / ".hubspot-portal"
    if portal_file.exists():
        return portal_file.read_text().strip().splitlines()[0].strip()
    return None


def load_portal_config(portal_id: str) -> PortalConfig | None:
    """Load portal config from environment or config directory."""
    token = os.getenv(f"HUBSPOT_TOKEN_{portal_id}")
    if not token:
        token_file = CONFIG_DIR / f"{portal_id}.token"
        if token_file.exists():
            token = token_file.read_text().strip()
    if not token:
        return None
    return PortalConfig(
        portal_id=portal_id,
        token=token,
        tier=os.getenv(f"HUBSPOT_TIER_{portal_id}", "unknown"),
        scopes_granted=os.getenv(f"HUBSPOT_SCOPES_{portal_id}", "").split(",") if os.getenv(f"HUBSPOT_SCOPES_{portal_id}") else [],
    )


def save_portal_config(portal: PortalConfig) -> None:
    _ensure_config_dir()
    token_file = CONFIG_DIR / f"{portal.portal_id}.token"
    token_file.write_text(portal.token)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed (portal detection, load config, save config).

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/config.py tests/test_config.py
git commit -m "feat: add portal config and .hubspot-portal auto-detection"
```

---

### Task 5: HubSpotClient (async HTTP + rate limiting)

**Files:**
- Create: `src/hubspot_agent/client.py`
- Modify: `src/hubspot_agent/__init__.py` (add client import)
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_client_get_success(respx_mock):
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.config import PortalConfig

    client = HubSpotClient(PortalConfig(portal_id="123", token="test-token"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value={"status_code": 200, "json": {"id": "1", "properties": {"email": "a@b.com"}}}
    )
    resp = await client.get("/crm/v3/objects/contacts/1", portal_id="123")
    assert resp.body["id"] == "1"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_client.py -v`
Expected: `ModuleNotFoundError: hubspot_agent.client`

- [ ] **Step 3: Implement client.py**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from hubspot_agent.config import PortalConfig
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError


@dataclass
class APIResponse:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str]


class HubSpotClient:
    BASE_URL = "https://api.hubapi.com"
    _RATE_LIMIT = 100  # requests per 10 seconds
    _BATCH_CONCURRENT = 4
    _WINDOW_SECONDS = 10

    def __init__(self, portal: PortalConfig):
        self.portal = portal
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {portal.token}"},
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        self._semaphore = asyncio.Semaphore(self._RATE_LIMIT)
        self._batch_semaphore = asyncio.Semaphore(self._BATCH_CONCURRENT)
        self._request_times: list[float] = []

    async def _enforce_rate_limit(self) -> None:
        now = asyncio.get_event_loop().time()
        cutoff = now - self._WINDOW_SECONDS
        self._request_times = [t for t in self._request_times if t > cutoff]
        if len(self._request_times) >= self._RATE_LIMIT:
            sleep_for = self._request_times[0] - cutoff
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        self._request_times.append(asyncio.get_event_loop().time())

    async def _request(
        self,
        method: str,
        path: str,
        portal_id: str,
        body: dict[str, Any] | None = None,
        expected_scopes: list[str] | None = None,
    ) -> APIResponse:
        await self._enforce_rate_limit()
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            raise RateLimitError("Rate limit exceeded", retry_after=retry_after)
        if resp.status_code == 403 and expected_scopes:
            raise ScopeError(
                f"Missing required scopes: {expected_scopes}",
                required_scopes=expected_scopes,
            )
        if resp.status_code >= 400:
            raise HubSpotError(
                resp.text or f"HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return APIResponse(
            status_code=resp.status_code,
            body=resp.json() if resp.text else {},
            headers=dict(resp.headers),
        )

    async def get(
        self, path: str, portal_id: str, expected_scopes: list[str] | None = None
    ) -> APIResponse:
        return await self._request("GET", path, portal_id, expected_scopes=expected_scopes)

    async def post(
        self,
        path: str,
        portal_id: str,
        body: dict[str, Any] | None = None,
        expected_scopes: list[str] | None = None,
    ) -> APIResponse:
        return await self._request("POST", path, portal_id, body, expected_scopes)

    async def patch(
        self,
        path: str,
        portal_id: str,
        body: dict[str, Any] | None = None,
        expected_scopes: list[str] | None = None,
    ) -> APIResponse:
        return await self._request("PATCH", path, portal_id, body, expected_scopes)

    async def delete(
        self, path: str, portal_id: str, expected_scopes: list[str] | None = None
    ) -> APIResponse:
        return await self._request("DELETE", path, portal_id, expected_scopes=expected_scopes)

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_client.py -v`
Expected: GET, POST, PATCH, DELETE, rate limit, and error tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/client.py tests/test_client.py
git commit -m "feat: add async HubSpotClient with rate limiting and retry logic"
```

---

### Task 6: Tool registry and decorator

**Files:**
- Create: `src/hubspot_agent/tools/__init__.py`
- Test: `tests/test_tool_registry.py`

- [ ] **Step 1: Write failing test**

```python
def test_tool_decorator_registers():
    from hubspot_agent.tools import tool, registry

    @tool(name="test_tool", description="A test tool")
    async def test_tool(x: int) -> dict:
        return {"result": x * 2}

    assert "test_tool" in registry
    assert registry["test_tool"].description == "A test tool"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_tool_registry.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement tools/__init__.py**

```python
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable[..., Any]
    is_async: bool


registry: dict[str, ToolDef] = {}


def tool(name: str, description: str) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        registry[name] = ToolDef(
            name=name,
            description=description,
            func=func,
            is_async=inspect.iscoroutinefunction(func),
        )
        return func
    return decorator


def get_tool(name: str) -> ToolDef | None:
    return registry.get(name)


def list_tools() -> list[ToolDef]:
    return list(registry.values())
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_tool_registry.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/__init__.py tests/test_tool_registry.py
git commit -m "feat: add tool registry with @tool decorator"
```

### Task 6b: Shared test fixtures (conftest.py)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Implement conftest.py**

```python
import pytest
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig


@pytest.fixture
def mock_portal():
    return PortalConfig(portal_id="123", token="test-token", tier="Professional")


@pytest.fixture
async def test_client(mock_portal):
    client = HubSpotClient(mock_portal)
    yield client
    await client.close()
```

- [ ] **Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared test fixtures for client and portal config"
```

---

## Phase 3: Tool Library

### Task 7: ObjectsAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/objects.py`
- Test: `tests/test_tools_objects.py`

- [ ] **Step 1: Write failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_hubspot_get_object(respx_mock):
    from hubspot_agent.tools.objects import hubspot_get_object
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.config import PortalConfig

    client = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/crm/v3/objects/contacts/1").mock(
        return_value={"status_code": 200, "json": {"id": "1", "properties": {"email": "a@b.com"}}}
    )
    result = await hubspot_get_object(object_id="1", object_type="contacts", client=client, portal_id="123")
    assert result["id"] == "1"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_tools_objects.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement objects.py**

```python
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from hubspot_agent.client import HubSpotClient
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError
from hubspot_agent.tools import tool

_VALID_OBJECT_TYPES = frozenset({"contacts", "companies", "deals", "tickets"})


def _validate_object_type(object_type: str) -> None:
    if object_type not in _VALID_OBJECT_TYPES:
        raise ValueError(
            f"Invalid object_type '{object_type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_OBJECT_TYPES))}"
        )


@tool(name="hubspot_get_object", description="Retrieve a HubSpot object by ID.")
async def hubspot_get_object(
    object_id: str,
    object_type: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.get(
            f"/crm/v3/objects/{object_type}/{quote(object_id, safe='')}",
            portal_id=portal_id,
            expected_scopes=[f"crm.objects.{object_type}.read"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_get_object"}


@tool(name="hubspot_search_objects", description="Search HubSpot objects using filter groups.")
async def hubspot_search_objects(
    object_type: str,
    query: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.post(
            f"/crm/v3/objects/{object_type}/search",
            portal_id=portal_id,
            body=query,
            expected_scopes=[f"crm.objects.{object_type}.read"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_search_objects"}


@tool(name="hubspot_create_object", description="Create a new HubSpot object record.")
async def hubspot_create_object(
    object_type: str,
    properties: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.post(
            f"/crm/v3/objects/{object_type}",
            portal_id=portal_id,
            body={"properties": properties},
            expected_scopes=[f"crm.objects.{object_type}.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_create_object"}


@tool(name="hubspot_update_object", description="Update an existing HubSpot object record.")
async def hubspot_update_object(
    object_id: str,
    object_type: str,
    properties: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.patch(
            f"/crm/v3/objects/{object_type}/{quote(object_id, safe='')}",
            portal_id=portal_id,
            body={"properties": properties},
            expected_scopes=[f"crm.objects.{object_type}.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_update_object"}


@tool(name="hubspot_delete_object", description="Permanently delete a HubSpot object record.")
async def hubspot_delete_object(
    object_id: str,
    object_type: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.delete(
            f"/crm/v3/objects/{object_type}/{quote(object_id, safe='')}",
            portal_id=portal_id,
            expected_scopes=[f"crm.objects.{object_type}.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_delete_object"}


_BATCH_SIZE = 100


def _partition_records(
    records: list[dict[str, Any]], unique_key: str
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[str, dict[str, Any]] = {}
    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    for record in records:
        key = str(record.get(unique_key, "")).lower().strip()
        if key and key in seen:
            continue
        if key:
            seen[key] = record
        obj_id = record.get("id") or record.get("hs_object_id")
        if obj_id:
            updates.append({"id": str(obj_id), "properties": record})
        else:
            creates.append({"properties": record})
    return seen, creates, updates


def _chunk(inputs: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [inputs[i : i + size] for i in range(0, len(inputs), size)]


@tool(name="hubspot_batch_upsert_objects", description="Batch create or update HubSpot objects with input-side deduplication.")
async def hubspot_batch_upsert_objects(
    object_type: str,
    records: list[dict[str, Any]],
    client: HubSpotClient,
    portal_id: str,
    unique_key: str = "email",
) -> dict[str, Any]:
    _validate_object_type(object_type)
    _, creates, updates = _partition_records(records, unique_key)

    created_count = 0
    updated_count = 0
    errors: list[dict[str, Any]] = []

    for chunk in _chunk(creates, _BATCH_SIZE):
        try:
            resp = await client.post(
                f"/crm/v3/objects/{object_type}/batch/create",
                portal_id=portal_id,
                body={"inputs": chunk},
                expected_scopes=[f"crm.objects.{object_type}.write"],
            )
            body = resp.body
            created_count += len(body.get("results", []))
            errors.extend(body.get("errors", []))
        except (HubSpotError, RateLimitError, ScopeError) as exc:
            errors.append({"message": str(exc), "category": "BATCH_CREATE"})

    for chunk in _chunk(updates, _BATCH_SIZE):
        try:
            resp = await client.post(
                f"/crm/v3/objects/{object_type}/batch/update",
                portal_id=portal_id,
                body={"inputs": chunk},
                expected_scopes=[f"crm.objects.{object_type}.write"],
            )
            body = resp.body
            updated_count += len(body.get("results", []))
            errors.extend(body.get("errors", []))
        except (HubSpotError, RateLimitError, ScopeError) as exc:
            errors.append({"message": str(exc), "category": "BATCH_UPDATE"})

    results: list[dict[str, Any]] = []
    for chunk in _chunk(creates, _BATCH_SIZE):
        try:
            resp = await client.post(
                f"/crm/v3/objects/{object_type}/batch/create",
                portal_id=portal_id,
                body={"inputs": chunk},
                expected_scopes=[f"crm.objects.{object_type}.write"],
            )
            body = resp.body
            created_count += len(body.get("results", []))
            results.extend(body.get("results", []))
            errors.extend(body.get("errors", []))
        except (HubSpotError, RateLimitError, ScopeError) as exc:
            errors.append({"message": str(exc), "category": "BATCH_CREATE"})

    for chunk in _chunk(updates, _BATCH_SIZE):
        try:
            resp = await client.post(
                f"/crm/v3/objects/{object_type}/batch/update",
                portal_id=portal_id,
                body={"inputs": chunk},
                expected_scopes=[f"crm.objects.{object_type}.write"],
            )
            body = resp.body
            updated_count += len(body.get("results", []))
            results.extend(body.get("results", []))
            errors.extend(body.get("errors", []))
        except (HubSpotError, RateLimitError, ScopeError) as exc:
            errors.append({"message": str(exc), "category": "BATCH_UPDATE"})

    return {
        "succeeded": created_count + updated_count,
        "failed": len(errors),
        "total": len(records),
        "results": results,
        "errors": errors,
    }
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_tools_objects.py -v`
Expected: 6 passed (get, search, create, update, delete, batch).

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/objects.py tests/test_tools_objects.py
git commit -m "feat: add objects tools (get, search, create, update, delete, batch upsert)"
```

---

### Task 8: PropertiesAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/properties.py`
- Test: `tests/test_tools_properties.py`

- [ ] **Step 1: Write failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_hubspot_list_properties(respx_mock):
    from hubspot_agent.tools.properties import hubspot_list_properties
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.config import PortalConfig

    client = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/crm/v3/properties/contacts").mock(
        return_value={"status_code": 200, "json": {"results": [{"name": "email"}]}}
    )
    result = await hubspot_list_properties(object_type="contacts", client=client, portal_id="123")
    assert len(result["results"]) == 1
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement properties.py**

```python
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from hubspot_agent.client import HubSpotClient
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError
from hubspot_agent.tools import tool

_VALID_OBJECT_TYPES = frozenset({"contacts", "companies", "deals", "tickets"})


def _validate_object_type(object_type: str) -> None:
    if object_type not in _VALID_OBJECT_TYPES:
        raise ValueError(f"Invalid object_type '{object_type}'")


@tool(name="hubspot_get_property", description="Retrieve a HubSpot custom property definition.")
async def hubspot_get_property(
    property_name: str,
    object_type: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.get(
            f"/crm/v3/properties/{object_type}/{quote(property_name, safe='')}",
            portal_id=portal_id,
            expected_scopes=[f"crm.schemas.{object_type}.read"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_get_property"}


@tool(name="hubspot_list_properties", description="List all properties for a HubSpot object type.")
async def hubspot_list_properties(
    object_type: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.get(
            f"/crm/v3/properties/{object_type}",
            portal_id=portal_id,
            expected_scopes=[f"crm.schemas.{object_type}.read"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_list_properties"}


@tool(name="hubspot_create_property", description="Create a new HubSpot custom property.")
async def hubspot_create_property(
    object_type: str,
    name: str,
    label: str,
    property_type: str,
    field_type: str,
    group_name: str = "contactinformation",
    client: HubSpotClient = None,
    portal_id: str = "",
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.post(
            f"/crm/v3/properties/{object_type}",
            portal_id=portal_id,
            body={
                "name": name,
                "label": label,
                "type": property_type,
                "fieldType": field_type,
                "groupName": group_name,
            },
            expected_scopes=[f"crm.schemas.{object_type}.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_create_property"}


@tool(name="hubspot_update_property", description="Update an existing HubSpot custom property.")
async def hubspot_update_property(
    property_name: str,
    object_type: str,
    updates: dict[str, Any],
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.patch(
            f"/crm/v3/properties/{object_type}/{quote(property_name, safe='')}",
            portal_id=portal_id,
            body=updates,
            expected_scopes=[f"crm.schemas.{object_type}.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_update_property"}


@tool(name="hubspot_delete_property", description="Delete a HubSpot custom property.")
async def hubspot_delete_property(
    property_name: str,
    object_type: str,
    client: HubSpotClient,
    portal_id: str,
) -> dict[str, Any]:
    _validate_object_type(object_type)
    try:
        resp = await client.delete(
            f"/crm/v3/properties/{object_type}/{quote(property_name, safe='')}",
            portal_id=portal_id,
            expected_scopes=[f"crm.schemas.{object_type}.write"],
        )
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_delete_property"}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_tools_properties.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/properties.py tests/test_tools_properties.py
git commit -m "feat: add properties tools (get, list, create, update, delete)"
```

---

### Task 9: WorkflowsAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/workflows.py`
- Test: `tests/test_tools_workflows.py`

- [ ] **Step 1: Write failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_hubspot_list_workflows(respx_mock):
    from hubspot_agent.tools.workflows import hubspot_list_workflows
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.config import PortalConfig

    client = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.get("https://api.hubapi.com/automation/v4/workflows").mock(
        return_value={"status_code": 200, "json": {"results": [{"id": "1", "name": "Test"}]}}
    )
    result = await hubspot_list_workflows(client=client, portal_id="123")
    assert len(result["results"]) == 1
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement workflows.py**

6 tools: `hubspot_get_workflow` (GET `/automation/v4/workflows/{id}`), `hubspot_list_workflows` (GET `/automation/v4/workflows`), `hubspot_create_workflow` (POST `/automation/v4/workflows`, body: `name`, `type`, `actions`, `enrollment`), `hubspot_update_workflow` (PATCH `/automation/v4/workflows/{id}`), `hubspot_enroll_workflow` (POST `/automation/v4/workflows/{id}/enrollments`, body: `objectIds`), `hubspot_toggle_workflow` (POST `/automation/v4/workflows/{id}/toggle`). Each wraps errors consistently with `objects.py`. Required scope: `automation.workflows.write` for writes, `automation.workflows.read` for reads.

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_tools_workflows.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/workflows.py tests/test_tools_workflows.py
git commit -m "feat: add workflow tools (get, list, create, update, enroll, toggle)"
```

---

### Task 10: ListsAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/lists.py`
- Test: `tests/test_tools_lists.py`

- [ ] **Step 1-5:** Implement 6 tools with TDD:

`hubspot_get_list` (GET `/crm/v3/lists/{id}`), `hubspot_list_lists` (GET `/crm/v3/lists` with `objectType` param), `hubspot_create_list` (POST `/crm/v3/lists`, body: `name`, `objectTypeId`, `processingType` `"STATIC"` or `"DYNAMIC"`), `hubspot_update_list` (PUT `/crm/v3/lists/{id}`), `hubspot_add_to_list` (PUT `/crm/v3/lists/{id}/memberships/add`, body: `recordIds`), `hubspot_remove_from_list` (PUT `/crm/v3/lists/{id}/memberships/remove`, body: `recordIds`). Required scope: `crm.lists.write`.

Commit: `feat: add list tools (get, list, create, update, add, remove)`

---

### Task 11: PipelinesAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/pipelines.py`
- Test: `tests/test_tools_pipelines.py`

- [ ] **Step 1-5:** Implement 5 tools with TDD:

`hubspot_get_pipeline` (GET `/crm/v3/pipelines/{objectType}/{pipelineId}`), `hubspot_list_pipelines` (GET `/crm/v3/pipelines/{objectType}`), `hubspot_create_pipeline` (POST `/crm/v3/pipelines/{objectType}`, body: `label`, `displayOrder`, `stages`), `hubspot_update_pipeline` (PATCH `/crm/v3/pipelines/{objectType}/{pipelineId}`), `hubspot_reorder_stages` (PATCH `/crm/v3/pipelines/{objectType}/{pipelineId}/stages`, body reordered stages). Required scope: `crm.pipelines.write`.

Commit: `feat: add pipeline tools (get, list, create, update, reorder)`

---

### Task 12: UsersAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/users.py`
- Test: `tests/test_tools_users.py`

- [ ] **Step 1-5:** Implement 5 tools with TDD:

`hubspot_get_user` (GET `/settings/v3/users/{id}`), `hubspot_list_users` (GET `/settings/v3/users`), `hubspot_create_user` (POST `/settings/v3/users`, body: `email`, `roleId`, `sendWelcomeEmail`), `hubspot_update_user` (PATCH `/settings/v3/users/{id}`, body: `roleId`, `primaryTeamId`), `hubspot_deactivate_user` (DELETE `/settings/v3/users/{id}`). Required scope: `settings.users.write`.

Commit: `feat: add user tools (get, list, create, update, deactivate)`

---

### Task 13: HygieneAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/hygiene.py`
- Test: `tests/test_tools_hygiene.py`

- [ ] **Step 1-5:** Implement 4 tools with TDD:

`hubspot_find_duplicates` (POST `/crm/v3/objects/contacts/search` with filter groups on `email` OR `phone` OR `domain`, returns pairs with matching values). `hubspot_merge_objects` (POST `/crm/v3/objects/contacts/merge`, body: `primaryObjectId`, `objectIdToMerge`; MVP only contacts). `hubspot_bulk_update_objects` (POST `/crm/v3/objects/{type}/batch/update` with chunking, returns `{succeeded, failed, total, results, errors}`). `hubspot_preview_segment` (POST `/crm/v3/objects/{type}/search`, returns `{object_type, total, results, preview: True}`).

Commit: `feat: add hygiene tools (find duplicates, merge, bulk update, preview segment)`

---

### Task 14: AnalyticsAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/analytics.py`
- Test: `tests/test_tools_analytics.py`

- [ ] **Step 1-5:** Implement 3 tools with TDD:

`hubspot_get_report` (GET `/analytics/v2/reports/{report_id}`, returns raw report data). `hubspot_calculate_metrics` (client-side: accepts `data` array, computes `conversion_rate`, `average_deal_size`, `win_rate`). `hubspot_pipeline_velocity` (client-side: accepts deal stage history, computes average days between each stage transition; formula: `(stage_exit_date - stage_enter_date).days` averaged per stage).

Commit: `feat: add analytics tools (get report, calculate metrics, pipeline velocity)`

---

### Task 15: AssociationsAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/associations.py`
- Test: `tests/test_tools_associations.py`

- [ ] **Step 1-5:** Implement 4 tools with TDD:

`hubspot_get_association_schema` (GET `/crm/v4/associations/{fromObjectType}/{toObjectType}/labels`). `hubspot_create_association_schema` (POST `/crm/v4/associations/{fromObjectType}/{toObjectType}/labels`, body: `name`, `label`). `hubspot_associate_records` (PUT `/crm/v4/objects/{fromType}/{fromId}/associations/{toType}/{toId}`, body: `associationTypeId`). `hubspot_disassociate_records` (DELETE `/crm/v4/objects/{fromType}/{fromId}/associations/{toType}/{toId}/{associationTypeId}`).

Commit: `feat: add association tools (schema CRUD, associate, disassociate)`

---

### Task 16: EngagementsAgent tools

**Files:**
- Create: `src/hubspot_agent/tools/engagements.py`
- Test: `tests/test_tools_engagements.py`

- [ ] **Step 1-5:** Implement 7 tools with TDD:

`hubspot_get_engagement` (GET `/crm/v3/objects/engagements/{id}`). `hubspot_search_engagements` (POST `/crm/v3/objects/engagements/search`). `hubspot_create_note` (POST `/crm/v3/objects/engagements`, body: `properties` with `hs_engagement_type: NOTE`, `hs_note_body`). `hubspot_create_task` (same endpoint, `hs_engagement_type: TASK`, `hs_task_subject`, `hs_task_status`, `hs_timestamp`). `hubspot_create_email` (`hs_engagement_type: EMAIL`, `hs_email_subject`, `hs_email_body`). `hubspot_create_meeting` (`hs_engagement_type: MEETING`, `hs_meeting_title`, `hs_meeting_start_time`). `hubspot_create_call` (`hs_engagement_type: CALL`, `hs_call_title`, `hs_call_duration`). Required scope: `crm.objects.engagements.write`.

Commit: `feat: add engagement tools (get, search, create note/task/email/meeting/call)`

---

### Task 17: RawAPIAgent tool

**Files:**
- Create: `src/hubspot_agent/tools/raw_api.py`
- Test: `tests/test_tools_raw_api.py`

- [ ] **Step 1: Write failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_hubspot_raw_api(respx_mock):
    from hubspot_agent.tools.raw_api import hubspot_raw_api
    from hubspot_agent.client import HubSpotClient
    from hubspot_agent.config import PortalConfig

    client = HubSpotClient(PortalConfig(portal_id="123", token="t"))
    respx_mock.post("https://api.hubapi.com/crm/v3/objects/contacts").mock(
        return_value={"status_code": 200, "json": {"id": "1"}}
    )
    result = await hubspot_raw_api(
        method="POST",
        path="/crm/v3/objects/contacts",
        body={"properties": {"email": "test@example.com"}},
        client=client,
        portal_id="123",
    )
    assert result["id"] == "1"
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement raw_api.py**

```python
from __future__ import annotations

from typing import Any

from hubspot_agent.client import HubSpotClient
from hubspot_agent.errors import HubSpotError, RateLimitError, ScopeError
from hubspot_agent.tools import tool


@tool(
    name="hubspot_raw_api",
    description="Direct HubSpot API call for uncovered endpoints. Power-user escape hatch.",
)
async def hubspot_raw_api(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    client: HubSpotClient = None,
    portal_id: str = "",
    expected_scopes: list[str] | None = None,
) -> dict[str, Any]:
    if client is None:
        return {"error": "HubSpotClient not provided", "tool": "hubspot_raw_api"}
    try:
        if method.upper() == "GET":
            resp = await client.get(path, portal_id=portal_id, expected_scopes=expected_scopes)
        elif method.upper() == "POST":
            resp = await client.post(path, portal_id=portal_id, body=body, expected_scopes=expected_scopes)
        elif method.upper() == "PATCH":
            resp = await client.patch(path, portal_id=portal_id, body=body, expected_scopes=expected_scopes)
        elif method.upper() == "DELETE":
            resp = await client.delete(path, portal_id=portal_id, expected_scopes=expected_scopes)
        else:
            return {"error": f"Unsupported method: {method}", "tool": "hubspot_raw_api"}
        return resp.body
    except (HubSpotError, RateLimitError, ScopeError) as exc:
        return {"error": str(exc), "tool": "hubspot_raw_api"}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_tools_raw_api.py -v`
Expected: 4 passed (GET, POST, PATCH, DELETE).

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/raw_api.py tests/test_tools_raw_api.py
git commit -m "feat: add raw_api escape-hatch tool for direct HubSpot API calls"
```

---

## Phase 4: Sub-Agent Definitions

### Task 18: Base agent builder

**Files:**
- Create: `src/hubspot_agent/agents/_base.py`
- Test: `tests/test_agents_base.py`

- [ ] **Step 1-5:** Build `_base.py` with:
- `build_agent_prompt(agent_name, domain_description, available_tools, portal_config)` — constructs system prompt for a sub-agent
- `format_tool_descriptions(tools)` — lists tools with names and descriptions for prompt injection
- `AgentPrompt` dataclass holding system prompt + tool list

Commit: `feat: add base agent prompt builder`

---

### Task 19: ObjectsAgent definition

**Files:**
- Create: `src/hubspot_agent/agents/objects.py`
- Test: `tests/test_agents_objects.py`

- [ ] **Step 1-5:** Define `ObjectsAgent` class/prompt with:
- System prompt: "You are the Objects Agent for HubSpot. You manage contacts, companies, deals, and tickets. Available tools: [list]. Always return structured JSON."
- Tool binding: references to the 7 object tools
- Response format instructions

Commit: `feat: add ObjectsAgent definition`

---

### Tasks 20-29: Remaining 10 agent definitions

Repeat the same pattern for:
- Task 20: PropertiesAgent
- Task 21: WorkflowsAgent
- Task 22: ListsAgent
- Task 23: PipelinesAgent
- Task 24: UsersAgent
- Task 25: HygieneAgent
- Task 26: AnalyticsAgent
- Task 27: AssociationsAgent
- Task 28: EngagementsAgent
- Task 29: RawAPIAgent

Each gets its own file in `src/hubspot_agent/agents/` with domain-specific system prompt and tool list. One commit per agent.

---

## Phase 5: Parent Orchestrator

### Task 30: Routing engine

**Files:**
- Create: `src/hubspot_agent/orchestrator.py`
- Modify: `src/hubspot_agent/agents/__init__.py` (add agent registry)
- Test: `tests/test_orchestrator_routing.py`

- [ ] **Step 1-5:** Build `route_request(request_text: str) -> list[str]` that:
- Parses request for keywords per Section 5 of the spec
- Detects dependencies ("and then" -> sequential, "and" + cross-domain -> static dependency graph)
- Returns ordered list of agent names to dispatch
- For ambiguous requests, returns `[]` with clarification needed

Commit: `feat: add request routing engine with keyword + dependency detection`

---

### Task 31: Scope validation

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`
- Test: `tests/test_orchestrator_scope.py`

- [ ] **Step 1-5:** Add `validate_scopes(agent_names: list[str], portal_scopes: list[str]) -> dict[str, list[str]]` that:
- Maps each agent to its required scopes (from tool metadata)
- Returns missing scopes per agent
- If any missing, returns error dict for parent to display

Commit: `feat: add proactive scope validation before dispatch`

---

### Task 32: HITL approval flow

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`
- Create: `src/hubspot_agent/snapshot.py`
- Test: `tests/test_orchestrator_hitl.py`
- Test: `tests/test_snapshot.py`

- [ ] **Step 1: Write failing test for snapshot storage**

```python
import json
from pathlib import Path


def test_save_undo_snapshot(tmp_path):
    from hubspot_agent.snapshot import save_undo_snapshot
    snapshot_dir = tmp_path / "undo_snapshots"
    save_undo_snapshot(
        str(snapshot_dir),
        action_id="act-123",
        original_values={"contacts": [{"id": "1", "email": "old@example.com"}]},
    )
    file = snapshot_dir / "act-123.json"
    assert file.exists()
    data = json.loads(file.read_text())
    assert data["original_values"]["contacts"][0]["id"] == "1"
```

- [ ] **Step 2: Implement snapshot.py**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_undo_snapshot(
    snapshot_dir: str,
    action_id: str,
    original_values: dict[str, Any],
) -> Path:
    dir_path = Path(snapshot_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{action_id}.json"
    file_path.write_text(
        json.dumps({"action_id": action_id, "original_values": original_values}, indent=2)
    )
    return file_path


def load_undo_snapshot(snapshot_dir: str, action_id: str) -> dict[str, Any] | None:
    file_path = Path(snapshot_dir) / f"{action_id}.json"
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text())


def delete_undo_snapshot(snapshot_dir: str, action_id: str) -> None:
    file_path = Path(snapshot_dir) / f"{action_id}.json"
    if file_path.exists():
        file_path.unlink()
```

- [ ] **Step 3: Write failing test for HITL approval flow**

```python
def test_needs_approval():
    from hubspot_agent.orchestrator import needs_approval
    from hubspot_agent.models import RiskLevel
    assert needs_approval(RiskLevel.LOW) is False
    assert needs_approval(RiskLevel.MEDIUM) is True
    assert needs_approval(RiskLevel.DESTRUCTIVE) is True


def test_present_preview_destructive():
    from hubspot_agent.orchestrator import present_preview
    from hubspot_agent.models import PreviewResult, RiskLevel
    result = PreviewResult(
        preview={"affected": [{"id": "1", "email": "a@b.com"}]},
        impact_count=1,
        risk_level=RiskLevel.DESTRUCTIVE,
        proposed_payload={"id": "1"},
        original_values={"contacts": [{"id": "1", "email": "a@b.com"}]},
    )
    text = present_preview(result)
    assert "1 records" in text
    assert "DESTRUCTIVE" in text
```

- [ ] **Step 4: Implement HITL approval in orchestrator.py**

```python
def needs_approval(risk_level: RiskLevel) -> bool:
    return risk_level != RiskLevel.LOW


def present_preview(result: PreviewResult, mode: str = "summary") -> str:
    lines = [
        f"### Proposed Change ({result.risk_level.value.upper()})",
        f"- **Impact:** {result.impact_count} records",
    ]
    if mode == "details" and result.preview:
        lines.append("- **Affected records:**")
        for item in result.preview.get("affected", []):
            lines.append(f"  - ID: {item.get('id')} | Name: {item.get('name', 'N/A')}")
        lines.append(f"- **Exact API call:** POST {result.proposed_payload.get('endpoint', 'N/A')}")
        lines.append("- **Backup advised:** This action cannot be undone.")
    elif result.preview:
        lines.append("- **Preview:**")
        for key, value in result.preview.items():
            lines.append(f"  - {key}: {value}")
    if result.risk_level == RiskLevel.DESTRUCTIVE:
        lines.append(f"\n**Destructive action.** Type `{result.impact_count}` to confirm, or `details` for full record list.")
    else:
        lines.append("\nApprove? (y/n/details)")
    return "\n".join(lines)


def store_preview_for_execution(
    portal_id: str,
    action_id: str,
    result: PreviewResult,
) -> Path:
    snapshot_dir = Path.home() / ".claude" / "hubspot" / portal_id / "undo_snapshots"
    return save_undo_snapshot(str(snapshot_dir), action_id, result.original_values)
```

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/snapshot.py src/hubspot_agent/orchestrator.py tests/test_snapshot.py tests/test_orchestrator_hitl.py
git commit -m "feat: add HITL approval flow with undo snapshot storage"
```

---

### Task 33: Sub-agent dispatch helpers

**Files:**
- Modify: `src/hubspot_agent/agents/__init__.py`
- Modify: `src/hubspot_agent/orchestrator.py`
- Test: `tests/test_orchestrator_dispatch.py`

- [ ] **Step 1-5:** Add `dispatch_agent(agent_name: str, prompt: str, payload: dict | None)` helper that:
- Looks up agent definition
- Constructs full prompt with system prompt + user request + payload (if execute mode)
- Returns structured `AgentResult`
- For preview mode: includes `mode=preview` instruction
- For execute mode: includes `mode=execute` + `payload=...` instruction

Commit: `feat: add sub-agent dispatch helpers with preview/execute mode`

---

### Task 33b: Post-timeout reconciliation

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`
- Test: `tests/test_orchestrator_timeout.py`

- [ ] **Step 1-5:** Add `reconcile_after_timeout(portal_id: str, expected_action: str, expected_payload: dict)` that:
- Dispatches `HygieneAgent` with a search query to verify what was actually applied
- Compares expected vs actual state
- Reports discrepancies to the user
- Used only after write-operation timeouts (not reads)

Commit: `feat: add post-timeout reconciliation for write operations`

---

## Phase 6: Cache & Audit (Infrastructure before CLI)

### Task 34: Cache management

**Files:**
- Create: `src/hubspot_agent/cache.py`
- Modify: `src/hubspot_agent/orchestrator.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1-5:** Build `cache.py` with:
- `SchemaCache` class: reads/writes `.claude/hubspot/<portal_id>/schema_cache.json`
- TTL-based invalidation (1 hour)
- Domain-specific invalidation after writes
- `refresh_all(portal_id)` and `refresh_domain(portal_id, domain)` methods

Commit: `feat: add schema cache with TTL and domain invalidation`

---

## Phase 7: Skill Entry Point

### Task 35: CLI / skill entry point

**Files:**
- Create: `src/hubspot_agent/cli.py`
- Modify: `src/hubspot_agent/__init__.py` (expose CLI)
- Test: `tests/test_cli.py`

- [ ] **Step 1-5:** Build `cli.py` with:
- `hubspot_command(request: str)` — main entry point for `/hubspot` skill
- Auto-detects portal from `.hubspot-portal` file in working directory
- Loads portal config
- Calls orchestrator to route request
- Displays results inline
- Handles `/hubspot portal switch`, `/hubspot portal list`, `/hubspot refresh`
- Displays current portal header on every response

Commit: `feat: add skill CLI entry point with portal commands`

---

### Task 36: Audit logging

**Files:**
- Create: `src/hubspot_agent/audit.py`
- Modify: `src/hubspot_agent/orchestrator.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1-5:** Build `audit.py` with:
- `log_write(portal_id, action, agent, result_summary)` — appends to `.claude/hubspot/<portal_id>/audit.log`
- JSON Lines format: `{timestamp, user, action, agent, result_summary}`
- `get_recent_audits(portal_id, limit=50)` — reads tail of log

Commit: `feat: add local audit logging for all write operations`

---

### Task 37: Integration test — end-to-end happy path

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1-5:** Write integration test that simulates:
1. `/hubspot "how many contacts"` -> routes to AnalyticsAgent -> returns count
2. `/hubspot "create a contact with email test@example.com"` -> routes to ObjectsAgent -> preview -> approval -> execute
3. `/hubspot portal switch 456` -> switches portal

Uses `respx` to mock all HubSpot API calls.

Commit: `test: add end-to-end integration test for read + write + portal switch`

---

### Task 38: Final review and cleanup

- [ ] **Step 1:** Run full test suite

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2:** Check code coverage

Run: `pytest tests/ --cov=hubspot_agent --cov-report=term-missing`
Expected: > 80% coverage.

- [ ] **Step 3:** Type check

Run: `python -m mypy src/hubspot_agent/`
Expected: No errors (if mypy installed).

- [ ] **Step 4:** Final commit

```bash
git add -A
git commit -m "feat: complete hubspot-agent skill with 11 sub-agents, HITL, and portal support"
```

---

## Summary

**38 tasks** organized in 7 phases:
1. **Scaffolding** (1 task) — project setup
2. **Shared Infrastructure** (5 tasks) — exceptions, models, config, client, tool registry
3. **Tool Library** (11 tasks) — ~50 tools across 11 domains
4. **Sub-Agent Definitions** (12 tasks) — base builder + 11 agents
5. **Parent Orchestrator** (4 tasks) — routing, scopes, HITL, dispatch
6. **Skill Entry Point** (1 task) — CLI + portal commands
7. **Integration & Polish** (4 tasks) — cache, audit, integration tests, cleanup

**Estimated total:** 38 commits, each representing 2-5 minutes of focused work.
