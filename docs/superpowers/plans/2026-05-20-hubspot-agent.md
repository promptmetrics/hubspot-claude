# HubSpot Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the HubSpot CRM admin skill from a single Objects agent to 14 specialist agents (Forms, Data, Commerce first) with full preview/execute/reconciliation HITL flows, dispatch tables, and comprehensive tests.

**Architecture:** Refactor `orchestrator.py` from hardcoded Objects-only logic to registry-based dispatch (`_PREVIEW_BUILDERS`, `_EXECUTE_DISPATCH`, `_RECONCILE_DISPATCH`). Each agent owns ~4–10 tools. New agents (Forms, Data, Commerce) get tool modules, agent prompts, orchestrator wiring, and tests in parallel.

**Tech Stack:** Python 3.11+, asyncio, HubSpot REST API v3, pytest, pytest-asyncio, Python `Agent` tool (Claude Code native subagent dispatch).

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/hubspot_agent/tools/forms.py` | 5 tools: list, get, create, update, delete HubSpot forms |
| `src/hubspot_agent/tools/data.py` | 6 tools: import_csv, get_import_status, export_records, get_export_url, upload_file, list_files |
| `src/hubspot_agent/tools/commerce.py` | 10 tools: line_items CRUD + products CRUD |
| `src/hubspot_agent/agents/forms.py` | FormsAgent prompt and dispatch registration |
| `src/hubspot_agent/agents/data.py` | DataAgent prompt and dispatch registration |
| `src/hubspot_agent/agents/commerce.py` | CommerceAgent prompt and dispatch registration |
| `src/hubspot_agent/agents/__init__.py` | Agent registry: add forms, data, commerce imports |
| `src/hubspot_agent/orchestrator.py` | Refactor to dispatch tables; wire preview/execute/reconcile for all agents |
| `src/hubspot_agent/cache.py` | Fix `initialize_session` to warm schemas instead of bare refresh |
| `tests/test_tools_forms.py` | Unit tests for forms tools |
| `tests/test_agents_forms.py` | Unit tests for FormsAgent prompt and dispatch |
| `tests/test_tools_data.py` | Unit tests for data tools |
| `tests/test_agents_data.py` | Unit tests for DataAgent prompt and dispatch |
| `tests/test_tools_commerce.py` | Unit tests for commerce tools |
| `tests/test_agents_commerce.py` | Unit tests for CommerceAgent prompt and dispatch |
| `tests/test_orchestrator_init.py` | Tests for `initialize_session` and dispatch table registration |
| `tests/test_audit_new_agents.py` | Tests for audit log entries after new-agent executions |

---

## Phase 1: Bootstrap & Tool Skeletons

### Task 1.1: Create Forms Tools Module

**Files:**
- Create: `src/hubspot_agent/tools/forms.py`
- Test: `tests/test_tools_forms.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_forms.py
import pytest
from hubspot_agent.tools.forms import list_forms, get_form, create_form, update_form, delete_form

@pytest.mark.asyncio
async def test_list_forms_returns_list():
    result = await list_forms()
    assert isinstance(result, list)

@pytest.mark.asyncio
async def test_get_form_requires_form_id():
    with pytest.raises(TypeError):
        await get_form()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_forms.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hubspot_agent.tools.forms'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubspot_agent/tools/forms.py
from __future__ import annotations
from typing import Any

from hubspot_agent.tools import tool
from hubspot_agent.client import HubSpotClient


@tool
def list_forms(client: HubSpotClient) -> list[dict[str, Any]]:
    """List all marketing forms."""
    return client.get("/forms/v2/forms")


@tool
def get_form(client: HubSpotClient, form_id: str) -> dict[str, Any]:
    """Get a single form by GUID."""
    return client.get(f"/forms/v2/forms/{form_id}")


@tool
def create_form(client: HubSpotClient, name: str, fields: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
    """Create a new marketing form."""
    payload = {"name": name, "fields": fields, **kwargs}
    return client.post("/forms/v2/forms", json=payload)


@tool
def update_form(client: HubSpotClient, form_id: str, **kwargs) -> dict[str, Any]:
    """Update an existing form. NOTE: Forms v4 returns BANNED on update via API.
    This tool attempts the PATCH and surfaces the error clearly."""
    return client.patch(f"/forms/v2/forms/{form_id}", json=kwargs)


@tool
def delete_form(client: HubSpotClient, form_id: str) -> dict[str, Any]:
    """Delete a form by GUID."""
    return client.delete(f"/forms/v2/forms/{form_id}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tools_forms.py -v`
Expected: PASS (import resolves, signatures are importable)

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/forms.py tests/test_tools_forms.py
git commit -m "feat(forms): add forms tool module with list/get/create/update/delete"
```

---

### Task 1.2: Create Data Tools Module

**Files:**
- Create: `src/hubspot_agent/tools/data.py`
- Test: `tests/test_tools_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_data.py
import pytest
from hubspot_agent.tools.data import import_csv, get_import_status, export_records, get_export_url, upload_file, list_files

@pytest.mark.asyncio
async def test_import_csv_requires_file_and_object():
    with pytest.raises(TypeError):
        await import_csv()

@pytest.mark.asyncio
async def test_list_files_returns_list():
    result = await list_files()
    assert isinstance(result, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_data.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubspot_agent/tools/data.py
from __future__ import annotations
from typing import Any

from hubspot_agent.tools import tool
from hubspot_agent.client import HubSpotClient


@tool
def import_csv(client: HubSpotClient, file_id: str, object_type: str, **kwargs) -> dict[str, Any]:
    """Start a CSV import job for contacts, companies, etc."""
    payload = {"fileId": file_id, "objectType": object_type, **kwargs}
    return client.post("/crm/v3/imports", json=payload)


@tool
def get_import_status(client: HubSpotClient, import_id: str) -> dict[str, Any]:
    """Check the status of an active import."""
    return client.get(f"/crm/v3/imports/{import_id}")


@tool
def export_records(client: HubSpotClient, object_type: str, format: str = "csv", **kwargs) -> dict[str, Any]:
    """Request an export of CRM records."""
    payload = {"objectType": object_type, "format": format, **kwargs}
    return client.post("/crm/v3/exports", json=payload)


@tool
def get_export_url(client: HubSpotClient, export_id: str) -> dict[str, Any]:
    """Get the download URL for a completed export."""
    return client.get(f"/crm/v3/exports/{export_id}")


@tool
def upload_file(client: HubSpotClient, file_path: str, folder_path: str = "", **kwargs) -> dict[str, Any]:
    """Upload a file to the HubSpot file manager."""
    return client.post_files("/files/v3/files", file_path=file_path, data={"folderPath": folder_path, **kwargs})


@tool
def list_files(client: HubSpotClient, folder_id: str | None = None, **kwargs) -> list[dict[str, Any]]:
    """List files in the file manager."""
    params = {"folderId": folder_id, **kwargs} if folder_id else kwargs
    return client.get("/files/v3/files", params=params)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tools_data.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/data.py tests/test_tools_data.py
git commit -m "feat(data): add data tool module for import/export/file ops"
```

---

### Task 1.3: Create Commerce Tools Module (Line Items)

**Files:**
- Create: `src/hubspot_agent/tools/commerce.py`
- Test: `tests/test_tools_commerce.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_commerce.py
import pytest
from hubspot_agent.tools.commerce import list_line_items, get_line_item, create_line_item, update_line_item, delete_line_item

@pytest.mark.asyncio
async def test_list_line_items_returns_list():
    result = await list_line_items()
    assert isinstance(result, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_commerce.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubspot_agent/tools/commerce.py (first half: line items)
from __future__ import annotations
from typing import Any

from hubspot_agent.tools import tool
from hubspot_agent.client import HubSpotClient


# --- Line Items ---

@tool
def list_line_items(client: HubSpotClient, **kwargs) -> list[dict[str, Any]]:
    """List line items with optional filtering."""
    return client.get("/crm/v3/objects/line_items", params=kwargs)


@tool
def get_line_item(client: HubSpotClient, line_item_id: str) -> dict[str, Any]:
    """Get a single line item by ID."""
    return client.get(f"/crm/v3/objects/line_items/{line_item_id}")


@tool
def create_line_item(client: HubSpotClient, properties: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Create a new line item."""
    payload = {"properties": properties, **kwargs}
    return client.post("/crm/v3/objects/line_items", json=payload)


@tool
def update_line_item(client: HubSpotClient, line_item_id: str, properties: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Update an existing line item."""
    payload = {"properties": properties, **kwargs}
    return client.patch(f"/crm/v3/objects/line_items/{line_item_id}", json=payload)


@tool
def delete_line_item(client: HubSpotClient, line_item_id: str) -> dict[str, Any]:
    """Delete a line item by ID."""
    return client.delete(f"/crm/v3/objects/line_items/{line_item_id}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tools_commerce.py::test_list_line_items_returns_list -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/commerce.py tests/test_tools_commerce.py
git commit -m "feat(commerce): add line items CRUD tools"
```

---

### Task 1.4: Extend Commerce Tools Module (Products)

**Files:**
- Modify: `src/hubspot_agent/tools/commerce.py`
- Modify: `tests/test_tools_commerce.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_tools_commerce.py
@pytest.mark.asyncio
async def test_list_products_returns_list():
    from hubspot_agent.tools.commerce import list_products
    result = await list_products()
    assert isinstance(result, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_commerce.py::test_list_products_returns_list -v`
Expected: FAIL with `ImportError: cannot import name 'list_products'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/hubspot_agent/tools/commerce.py`:

```python
# --- Products ---

@tool
def list_products(client: HubSpotClient, **kwargs) -> list[dict[str, Any]]:
    """List products with optional filtering."""
    return client.get("/crm/v3/objects/products", params=kwargs)


@tool
def get_product(client: HubSpotClient, product_id: str) -> dict[str, Any]:
    """Get a single product by ID."""
    return client.get(f"/crm/v3/objects/products/{product_id}")


@tool
def create_product(client: HubSpotClient, properties: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Create a new product."""
    payload = {"properties": properties, **kwargs}
    return client.post("/crm/v3/objects/products", json=payload)


@tool
def update_product(client: HubSpotClient, product_id: str, properties: dict[str, Any], **kwargs) -> dict[str, Any]:
    """Update an existing product."""
    payload = {"properties": properties, **kwargs}
    return client.patch(f"/crm/v3/objects/products/{product_id}", json=payload)


@tool
def delete_product(client: HubSpotClient, product_id: str) -> dict[str, Any]:
    """Delete a product by ID."""
    return client.delete(f"/crm/v3/objects/products/{product_id}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tools_commerce.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/tools/commerce.py tests/test_tools_commerce.py
git commit -m "feat(commerce): add products CRUD tools"
```

---

## Phase 2: Agent Prompts & Registration

### Task 2.1: Create FormsAgent Prompt

**Files:**
- Create: `src/hubspot_agent/agents/forms.py`
- Test: `tests/test_agents_forms.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agents_forms.py
import pytest
from hubspot_agent.agents.forms import FormsAgent, FORMS_SYSTEM_PROMPT

def test_forms_agent_has_prompt():
    assert "form" in FORMS_SYSTEM_PROMPT.lower()
    assert FormsAgent.system_prompt == FORMS_SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents_forms.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubspot_agent/agents/forms.py
from __future__ import annotations
from typing import Any

from hubspot_agent.agents.base import BaseAgent
from hubspot_agent.tools.forms import list_forms, get_form, create_form, update_form, delete_form


FORMS_SYSTEM_PROMPT = """You are the FormsAgent for HubSpot CRM.
You manage marketing forms: list, read, create, update, and delete.

Constraints:
- Forms v4 returns BANNED on update via API. If update fails, explain this limitation to the user.
- Always validate form_id is a valid GUID before GET/DELETE.
- When creating forms, require at least a name and one field.

Tools available:
- list_forms
- get_form
- create_form
- update_form
- delete_form
"""


class FormsAgent(BaseAgent):
    name = "forms"
    description = "Manages HubSpot marketing forms"
    system_prompt = FORMS_SYSTEM_PROMPT
    tools = [list_forms, get_form, create_form, update_form, delete_form]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agents_forms.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/agents/forms.py tests/test_agents_forms.py
git commit -m "feat(forms): add FormsAgent prompt and dispatch class"
```

---

### Task 2.2: Create DataAgent Prompt

**Files:**
- Create: `src/hubspot_agent/agents/data.py`
- Test: `tests/test_agents_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agents_data.py
import pytest
from hubspot_agent.agents.data import DataAgent, DATA_SYSTEM_PROMPT

def test_data_agent_has_prompt():
    assert "import" in DATA_SYSTEM_PROMPT.lower()
    assert DataAgent.system_prompt == DATA_SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents_data.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubspot_agent/agents/data.py
from __future__ import annotations
from typing import Any

from hubspot_agent.agents.base import BaseAgent
from hubspot_agent.tools.data import import_csv, get_import_status, export_records, get_export_url, upload_file, list_files


DATA_SYSTEM_PROMPT = """You are the DataAgent for HubSpot CRM.
You handle bulk data operations: imports, exports, and file manager tasks.

Constraints:
- Imports are async: always return the import_id so the user can poll status.
- Exports may take minutes; return export_id and suggest polling.
- Files upload to the file manager; list_files searches by folder.

Tools available:
- import_csv
- get_import_status
- export_records
- get_export_url
- upload_file
- list_files
"""


class DataAgent(BaseAgent):
    name = "data"
    description = "Manages HubSpot data import/export and file operations"
    system_prompt = DATA_SYSTEM_PROMPT
    tools = [import_csv, get_import_status, export_records, get_export_url, upload_file, list_files]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agents_data.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/agents/data.py tests/test_agents_data.py
git commit -m "feat(data): add DataAgent prompt and dispatch class"
```

---

### Task 2.3: Create CommerceAgent Prompt

**Files:**
- Create: `src/hubspot_agent/agents/commerce.py`
- Test: `tests/test_agents_commerce.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agents_commerce.py
import pytest
from hubspot_agent.agents.commerce import CommerceAgent, COMMERCE_SYSTEM_PROMPT

def test_commerce_agent_has_prompt():
    assert "line item" in COMMERCE_SYSTEM_PROMPT.lower()
    assert "product" in COMMERCE_SYSTEM_PROMPT.lower()
    assert CommerceAgent.system_prompt == COMMERCE_SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents_commerce.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/hubspot_agent/agents/commerce.py
from __future__ import annotations
from typing import Any

from hubspot_agent.agents.base import BaseAgent
from hubspot_agent.tools.commerce import (
    list_line_items, get_line_item, create_line_item, update_line_item, delete_line_item,
    list_products, get_product, create_product, update_product, delete_product,
)


COMMERCE_SYSTEM_PROMPT = """You are the CommerceAgent for HubSpot CRM.
You manage line items and products for quotes and deals.

Constraints:
- Line items must reference a valid product_id when created.
- Products have a price; validate numeric price > 0 on create.
- Deleting a product does NOT cascade-delete existing line items.

Tools available:
- list_line_items, get_line_item, create_line_item, update_line_item, delete_line_item
- list_products, get_product, create_product, update_product, delete_product
"""


class CommerceAgent(BaseAgent):
    name = "commerce"
    description = "Manages HubSpot line items and products"
    system_prompt = COMMERCE_SYSTEM_PROMPT
    tools = [
        list_line_items, get_line_item, create_line_item, update_line_item, delete_line_item,
        list_products, get_product, create_product, update_product, delete_product,
    ]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agents_commerce.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/agents/commerce.py tests/test_agents_commerce.py
git commit -m "feat(commerce): add CommerceAgent prompt and dispatch class"
```

---

### Task 2.4: Register New Agents in Agent Registry

**Files:**
- Modify: `src/hubspot_agent/agents/__init__.py`

- [ ] **Step 1: Read current registry**

Run: `cat src/hubspot_agent/agents/__init__.py`

- [ ] **Step 2: Add imports and registry entries**

```python
# src/hubspot_agent/agents/__init__.py
from hubspot_agent.agents.objects import ObjectsAgent
from hubspot_agent.agents.forms import FormsAgent
from hubspot_agent.agents.data import DataAgent
from hubspot_agent.agents.commerce import CommerceAgent

AGENTS = {
    ObjectsAgent.name: ObjectsAgent,
    FormsAgent.name: FormsAgent,
    DataAgent.name: DataAgent,
    CommerceAgent.name: CommerceAgent,
}
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from hubspot_agent.agents import AGENTS; print(list(AGENTS.keys()))"`
Expected: `['objects', 'forms', 'data', 'commerce']`

- [ ] **Step 4: Commit**

```bash
git add src/hubspot_agent/agents/__init__.py
git commit -m "feat(agents): register FormsAgent, DataAgent, CommerceAgent"
```

---

## Phase 3: Orchestrator Dispatch Tables

### Task 3.1: Refactor Orchestrator — Add Dispatch Registries

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py` (lines 1–100 for imports and registries)

- [ ] **Step 1: Add dispatch registries after imports**

```python
# src/hubspot_agent/orchestrator.py
_PREVIEW_BUILDERS: dict[str, callable] = {}
_EXECUTE_DISPATCH: dict[str, callable] = {}
_RECONCILE_DISPATCH: dict[str, callable] = {}


def register_agent_dispatch(agent_name: str, *, preview: callable | None = None, execute: callable | None = None, reconcile: callable | None = None):
    """Register preview/execute/reconcile handlers for an agent."""
    if preview:
        _PREVIEW_BUILDERS[agent_name] = preview
    if execute:
        _EXECUTE_DISPATCH[agent_name] = execute
    if reconcile:
        _RECONCILE_DISPATCH[agent_name] = reconcile
```

- [ ] **Step 2: Commit**

```bash
git add src/hubspot_agent/orchestrator.py
git commit -m "refactor(orchestrator): add preview/execute/reconcile dispatch registries"
```

---

### Task 3.2: Extract Objects Agent Logic into Dispatch Functions

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`

- [ ] **Step 1: Extract preview builder for objects**

Refactor `_build_preview_for_intent` so the objects-specific block becomes a standalone function:

```python
def _build_objects_preview(intent: dict, portal_config: dict, cache: SchemaCache) -> dict:
    """Build preview payload for ObjectsAgent."""
    object_type = intent.get("object_type", "contacts")
    operation = intent.get("operation", "list")
    record_id = intent.get("record_id")
    properties = intent.get("properties", {})

    schema = cache.get_schema(object_type)
    if not schema:
        cache.discover_custom_schemas(portal_config)
        schema = cache.get_schema(object_type)

    preview = {
        "agent": "objects",
        "operation": operation,
        "object_type": object_type,
        "record_count": 0,
        "sample_properties": {},
        "warnings": [],
    }

    if operation in ("create", "update"):
        preview["sample_properties"] = {k: v for k, v in list(properties.items())[:3]}
        missing_required = [p for p in schema.get("required", []) if p not in properties]
        if missing_required:
            preview["warnings"].append(f"Missing required properties: {missing_required}")

    elif operation == "delete" and record_id:
        preview["record_count"] = 1
        preview["warnings"].append("This will permanently delete the record.")

    elif operation == "list":
        preview["record_count"] = intent.get("limit", 10)

    return preview
```

- [ ] **Step 2: Extract execute dispatch for objects**

Refactor the execute block in `dispatch_agent` so objects logic becomes:

```python
def _execute_objects(agent: BaseAgent, intent: dict, client: HubSpotClient, cache: SchemaCache) -> dict:
    """Execute ObjectsAgent intent."""
    operation = intent.get("operation", "list")
    object_type = intent.get("object_type", "contacts")
    record_id = intent.get("record_id")
    properties = intent.get("properties", {})

    if operation == "list":
        limit = intent.get("limit", 10)
        return agent.tools[0](client, object_type=object_type, limit=limit)
    elif operation == "get" and record_id:
        return agent.tools[1](client, object_type=object_type, record_id=record_id)
    elif operation == "create":
        return agent.tools[2](client, object_type=object_type, properties=properties)
    elif operation == "update" and record_id:
        return agent.tools[3](client, object_type=object_type, record_id=record_id, properties=properties)
    elif operation == "delete" and record_id:
        return agent.tools[4](client, object_type=object_type, record_id=record_id)
    else:
        return {"error": f"Unsupported objects operation: {operation}"}
```

- [ ] **Step 3: Extract reconcile dispatch for objects**

```python
def _reconcile_objects(intent: dict, result: dict, audit_log: list) -> dict:
    """Reconcile ObjectsAgent execution after timeout."""
    status = result.get("status", "unknown")
    if status in ("success", "completed"):
        audit_log.append({"agent": "objects", "intent": intent, "result": result, "reconciled": True})
        return {"reconciled": True, "status": "confirmed"}
    elif status in ("failed", "error"):
        audit_log.append({"agent": "objects", "intent": intent, "result": result, "reconciled": False, "error": result.get("error")})
        return {"reconciled": False, "status": "failed", "error": result.get("error")}
    else:
        # Timeout or ambiguous — mark for human review
        audit_log.append({"agent": "objects", "intent": intent, "result": result, "reconciled": False, "needs_review": True})
        return {"reconciled": False, "status": "needs_review", "message": "Execution status ambiguous; manual review required."}
```

- [ ] **Step 4: Wire registries at module init**

After the class/function definitions, add:

```python
# Register built-in agents
register_agent_dispatch("objects", preview=_build_objects_preview, execute=_execute_objects, reconcile=_reconcile_objects)
```

- [ ] **Step 5: Update `dispatch_agent` to use `_EXECUTE_DISPATCH`**

Replace the inline objects-only execute block with:

```python
# Inside dispatch_agent, after preview/approval:
execute_handler = _EXECUTE_DISPATCH.get(agent.name)
if execute_handler:
    result = execute_handler(agent, intent, client, cache)
else:
    result = {"error": f"No execute handler registered for agent: {agent.name}"}
```

- [ ] **Step 6: Update `reconcile_after_timeout` to use `_RECONCILE_DISPATCH`**

Replace the inline objects-only reconciliation with:

```python
reconcile_handler = _RECONCILE_DISPATCH.get(agent_name)
if reconcile_handler:
    return reconcile_handler(intent, result, audit_log)
else:
    return {"reconciled": False, "status": "unknown", "error": f"No reconcile handler for {agent_name}"}
```

- [ ] **Step 7: Run existing tests**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS (no regressions in existing objects flow)

- [ ] **Step 8: Commit**

```bash
git add src/hubspot_agent/orchestrator.py
git commit -m "refactor(orchestrator): extract objects logic into dispatch functions"
```

---

### Task 3.3: Add Dispatch Functions for Forms, Data, Commerce

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`

- [ ] **Step 1: Add Forms preview/execute/reconcile**

```python
def _build_forms_preview(intent: dict, portal_config: dict, cache: SchemaCache) -> dict:
    operation = intent.get("operation", "list")
    form_id = intent.get("form_id")
    preview = {"agent": "forms", "operation": operation, "form_id": form_id, "warnings": []}
    if operation == "delete":
        preview["warnings"].append("This will permanently delete the form and all submission data.")
    elif operation == "update":
        preview["warnings"].append("Forms API may return BANNED on update; execution will surface the error.")
    return preview


def _execute_forms(agent, intent, client, cache):
    operation = intent.get("operation", "list")
    form_id = intent.get("form_id")
    name = intent.get("name")
    fields = intent.get("fields", [])
    kwargs = intent.get("properties", {})

    if operation == "list":
        return agent.tools[0](client)
    elif operation == "get" and form_id:
        return agent.tools[1](client, form_id=form_id)
    elif operation == "create":
        return agent.tools[2](client, name=name, fields=fields, **kwargs)
    elif operation == "update" and form_id:
        return agent.tools[3](client, form_id=form_id, **kwargs)
    elif operation == "delete" and form_id:
        return agent.tools[4](client, form_id=form_id)
    return {"error": f"Unsupported forms operation: {operation}"}


def _reconcile_forms(intent, result, audit_log):
    status = result.get("status", "unknown")
    entry = {"agent": "forms", "intent": intent, "result": result, "reconciled": status in ("success", "completed")}
    audit_log.append(entry)
    return {"reconciled": entry["reconciled"], "status": status}
```

- [ ] **Step 2: Add Data preview/execute/reconcile**

```python
def _build_data_preview(intent: dict, portal_config: dict, cache: SchemaCache) -> dict:
    operation = intent.get("operation", "list")
    preview = {"agent": "data", "operation": operation, "warnings": []}
    if operation == "import_csv":
        preview["warnings"].append("Imports are async; you will receive an import_id to poll.")
    elif operation == "export_records":
        preview["warnings"].append("Exports may take several minutes; you will receive an export_id.")
    return preview


def _execute_data(agent, intent, client, cache):
    operation = intent.get("operation", "list")
    file_id = intent.get("file_id")
    object_type = intent.get("object_type")
    import_id = intent.get("import_id")
    export_id = intent.get("export_id")
    file_path = intent.get("file_path")
    folder_path = intent.get("folder_path", "")

    if operation == "list_files":
        return agent.tools[5](client)
    elif operation == "import_csv" and file_id and object_type:
        return agent.tools[0](client, file_id=file_id, object_type=object_type)
    elif operation == "get_import_status" and import_id:
        return agent.tools[1](client, import_id=import_id)
    elif operation == "export_records" and object_type:
        return agent.tools[2](client, object_type=object_type)
    elif operation == "get_export_url" and export_id:
        return agent.tools[3](client, export_id=export_id)
    elif operation == "upload_file" and file_path:
        return agent.tools[4](client, file_path=file_path, folder_path=folder_path)
    return {"error": f"Unsupported data operation: {operation}"}


def _reconcile_data(intent, result, audit_log):
    status = result.get("status", "unknown")
    entry = {"agent": "data", "intent": intent, "result": result, "reconciled": status in ("success", "completed", "pending")}
    audit_log.append(entry)
    return {"reconciled": entry["reconciled"], "status": status}
```

- [ ] **Step 3: Add Commerce preview/execute/reconcile**

```python
def _build_commerce_preview(intent: dict, portal_config: dict, cache: SchemaCache) -> dict:
    operation = intent.get("operation", "list")
    resource = intent.get("resource", "line_items")
    preview = {"agent": "commerce", "operation": operation, "resource": resource, "warnings": []}
    if operation == "delete" and resource == "products":
        preview["warnings"].append("Deleting a product does NOT cascade-delete referencing line items.")
    return preview


def _execute_commerce(agent, intent, client, cache):
    operation = intent.get("operation", "list")
    resource = intent.get("resource", "line_items")
    record_id = intent.get("record_id")
    properties = intent.get("properties", {})

    if resource == "line_items":
        if operation == "list":
            return agent.tools[0](client)
        elif operation == "get" and record_id:
            return agent.tools[1](client, line_item_id=record_id)
        elif operation == "create":
            return agent.tools[2](client, properties=properties)
        elif operation == "update" and record_id:
            return agent.tools[3](client, line_item_id=record_id, properties=properties)
        elif operation == "delete" and record_id:
            return agent.tools[4](client, line_item_id=record_id)
    elif resource == "products":
        if operation == "list":
            return agent.tools[5](client)
        elif operation == "get" and record_id:
            return agent.tools[6](client, product_id=record_id)
        elif operation == "create":
            return agent.tools[7](client, properties=properties)
        elif operation == "update" and record_id:
            return agent.tools[8](client, product_id=record_id, properties=properties)
        elif operation == "delete" and record_id:
            return agent.tools[9](client, product_id=record_id)
    return {"error": f"Unsupported commerce operation: {operation} on {resource}"}


def _reconcile_commerce(intent, result, audit_log):
    status = result.get("status", "unknown")
    entry = {"agent": "commerce", "intent": intent, "result": result, "reconciled": status in ("success", "completed")}
    audit_log.append(entry)
    return {"reconciled": entry["reconciled"], "status": status}
```

- [ ] **Step 4: Register all new dispatch handlers**

```python
register_agent_dispatch("forms", preview=_build_forms_preview, execute=_execute_forms, reconcile=_reconcile_forms)
register_agent_dispatch("data", preview=_build_data_preview, execute=_execute_data, reconcile=_reconcile_data)
register_agent_dispatch("commerce", preview=_build_commerce_preview, execute=_execute_commerce, reconcile=_reconcile_commerce)
```

- [ ] **Step 5: Run existing tests**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/hubspot_agent/orchestrator.py
git commit -m "feat(orchestrator): add forms, data, commerce dispatch handlers"
```

---

## Phase 4: HITL Integration

### Task 4.1: Fix `initialize_session` to Warm Schemas

**Files:**
- Modify: `src/hubspot_agent/cache.py` (if needed)
- Modify: `src/hubspot_agent/orchestrator.py` (line 57–59)

- [ ] **Step 1: Read current `initialize_session`**

Run: `sed -n '55,65p' src/hubspot_agent/orchestrator.py`

- [ ] **Step 2: Replace with schema-warming logic**

```python
def initialize_session(portal_config: dict, cache: SchemaCache) -> None:
    """Warm standard and custom schemas so agents have property metadata available immediately."""
    cache.warm_standard_schemas(portal_config)
    cache.discover_custom_schemas(portal_config)
```

- [ ] **Step 3: Add test for initialization**

```python
# tests/test_orchestrator_init.py
import pytest
from unittest.mock import MagicMock
from hubspot_agent.orchestrator import initialize_session

def test_initialize_session_warms_schemas():
    config = {"portal_id": "123", "access_token": "fake"}
    cache = MagicMock()
    initialize_session(config, cache)
    cache.warm_standard_schemas.assert_called_once_with(config)
    cache.discover_custom_schemas.assert_called_once_with(config)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_orchestrator_init.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hubspot_agent/orchestrator.py tests/test_orchestrator_init.py
git commit -m "fix(orchestrator): initialize_session warms standard and custom schemas"
```

---

### Task 4.2: Pending Preview Storage

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`

- [ ] **Step 1: Add pending preview persistence**

```python
import json
import os
from pathlib import Path

PENDING_PREVIEW_DIR = Path.home() / ".hubspot-agent" / "pending_previews"


def _save_pending_preview(preview_id: str, preview: dict) -> None:
    PENDING_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    path = PENDING_PREVIEW_DIR / f"{preview_id}.json"
    path.write_text(json.dumps(preview, indent=2, default=str), encoding="utf-8")


def _load_pending_preview(preview_id: str) -> dict | None:
    path = PENDING_PREVIEW_DIR / f"{preview_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _remove_pending_preview(preview_id: str) -> None:
    path = PENDING_PREVIEW_DIR / f"{preview_id}.json"
    if path.exists():
        path.unlink()
```

- [ ] **Step 2: Wire into `dispatch_agent` flow**

After building the preview and before the approval prompt:

```python
preview_id = str(uuid.uuid4())
preview["preview_id"] = preview_id
_save_pending_preview(preview_id, preview)
```

After execution (success or failure):

```python
_remove_pending_preview(preview_id)
```

- [ ] **Step 3: Commit**

```bash
git add src/hubspot_agent/orchestrator.py
git commit -m "feat(orchestrator): persist pending previews to disk for timeout recovery"
```

---

### Task 4.3: Timeout Reconciliation Stub → Full Implementation

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`

- [ ] **Step 1: Ensure `reconcile_after_timeout` loads pending preview by ID**

```python
def reconcile_after_timeout(preview_id: str, portal_config: dict, cache: SchemaCache, audit_log: list) -> dict:
    preview = _load_pending_preview(preview_id)
    if not preview:
        return {"reconciled": False, "error": "Preview not found or already processed."}

    agent_name = preview.get("agent")
    intent = preview.get("intent", {})
    # ... existing reconciliation logic using _RECONCILE_DISPATCH ...
```

- [ ] **Step 2: Commit**

```bash
git add src/hubspot_agent/orchestrator.py
git commit -m "feat(orchestrator): reconcile_after_timeout loads persisted preview by ID"
```

---

## Phase 5: Testing

### Task 5.1: Unit Tests for New Tools

**Files:**
- `tests/test_tools_forms.py`
- `tests/test_tools_data.py`
- `tests/test_tools_commerce.py`

- [ ] **Step 1: Add mocked client tests**

For each tool module, add tests that mock `HubSpotClient` and assert the correct HTTP method and path are called:

```python
# Example pattern for tests/test_tools_forms.py
from unittest.mock import MagicMock
import pytest
from hubspot_agent.tools.forms import list_forms, create_form

@pytest.mark.asyncio
async def test_list_forms_calls_correct_endpoint():
    client = MagicMock()
    client.get.return_value = [{"name": "Form A"}]
    result = await list_forms(client)
    client.get.assert_called_once_with("/forms/v2/forms")
    assert result == [{"name": "Form A"}]

@pytest.mark.asyncio
async def test_create_forms_posts_correct_payload():
    client = MagicMock()
    client.post.return_value = {"id": "123"}
    result = await create_form(client, name="Test", fields=[{"name": "email"}])
    client.post.assert_called_once_with("/forms/v2/forms", json={"name": "Test", "fields": [{"name": "email"}]})
```

Repeat analogous tests for `test_tools_data.py` and `test_tools_commerce.py`.

- [ ] **Step 2: Run all tool tests**

Run: `pytest tests/test_tools_forms.py tests/test_tools_data.py tests/test_tools_commerce.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_tools_forms.py tests/test_tools_data.py tests/test_tools_commerce.py
git commit -m "test(tools): add mocked client tests for forms, data, commerce"
```

---

### Task 5.2: Unit Tests for Agent Dispatch

**Files:**
- `tests/test_agents_forms.py`
- `tests/test_agents_data.py`
- `tests/test_agents_commerce.py`

- [ ] **Step 1: Add dispatch table registration tests**

```python
# tests/test_agents_forms.py
from hubspot_agent.orchestrator import _PREVIEW_BUILDERS, _EXECUTE_DISPATCH, _RECONCILE_DISPATCH

def test_forms_dispatch_registered():
    assert "forms" in _PREVIEW_BUILDERS
    assert "forms" in _EXECUTE_DISPATCH
    assert "forms" in _RECONCILE_DISPATCH
```

Repeat for `data` and `commerce`.

- [ ] **Step 2: Run agent tests**

Run: `pytest tests/test_agents_forms.py tests/test_agents_data.py tests/test_agents_commerce.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_agents_forms.py tests/test_agents_data.py tests/test_agents_commerce.py
git commit -m "test(agents): verify forms, data, commerce dispatch registration"
```

---

### Task 5.3: Audit Log Verification Tests

**Files:**
- Create: `tests/test_audit_new_agents.py`

- [ ] **Step 1: Write audit tests**

```python
# tests/test_audit_new_agents.py
import pytest
from hubspot_agent.orchestrator import reconcile_after_timeout

@pytest.mark.asyncio
async def test_forms_audit_log_entry():
    audit = []
    preview = {"agent": "forms", "operation": "delete", "form_id": "abc"}
    result = {"status": "success"}
    reconcile_after_timeout(preview, result, audit)
    assert len(audit) == 1
    assert audit[0]["agent"] == "forms"
    assert audit[0]["reconciled"] is True

@pytest.mark.asyncio
async def test_commerce_audit_log_on_failure():
    audit = []
    preview = {"agent": "commerce", "operation": "create", "resource": "products"}
    result = {"status": "failed", "error": "Price must be > 0"}
    reconcile_after_timeout(preview, result, audit)
    assert audit[0]["reconciled"] is False
    assert audit[0]["result"]["error"] == "Price must be > 0"
```

- [ ] **Step 2: Run audit tests**

Run: `pytest tests/test_audit_new_agents.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_audit_new_agents.py
git commit -m "test(audit): add audit log tests for new agents"
```

---

## Phase 6: CLI Polish

### Task 6.1: Add Status Subcommand

**Files:**
- Modify: `src/hubspot_agent/cli.py`

- [ ] **Step 1: Add `/hubspot status` handling**

```python
# Inside cli.py argument parser or command dispatch
async def _status(portal_config: dict, cache: SchemaCache) -> str:
    lines = [f"Portal: {portal_config['portal_id']}"]
    lines.append(f"Auth: {'valid' if portal_config.get('access_token') else 'missing'}")
    lines.append(f"Cached schemas: {len(cache._schemas)}")
    pending = list(Path.home().glob(".hubspot-agent/pending_previews/*.json"))
    lines.append(f"Pending previews: {len(pending)}")
    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
git add src/hubspot_agent/cli.py
git commit -m "feat(cli): add /hubspot status subcommand"
```

---

### Task 6.2: Add Refresh Subcommand

**Files:**
- Modify: `src/hubspot_agent/cli.py`

- [ ] **Step 1: Add `/hubspot refresh` handling**

```python
async def _refresh(portal_config: dict, cache: SchemaCache) -> str:
    cache.clear()
    cache.warm_standard_schemas(portal_config)
    cache.discover_custom_schemas(portal_config)
    return "Schema cache refreshed."
```

- [ ] **Step 2: Commit**

```bash
git add src/hubspot_agent/cli.py
git commit -m "feat(cli): add /hubspot refresh subcommand"
```

---

## Phase 7: Documentation & Audit

### Task 7.1: Update README

**Files:**
- Modify: `README.md` (or create `docs/README.md` if it doesn't exist)

- [ ] **Step 1: Document new agents**

Add a section:

```markdown
## Supported Agents

| Agent | Operations | Key Constraints |
|-------|------------|-----------------|
| Objects | CRUD on contacts, companies, deals, tickets, custom objects | Schema-aware property validation |
| Forms | List, get, create, update, delete | Update returns BANNED on Forms v4 |
| Data | Import CSV, export records, upload files, list files | Imports/exports are async |
| Commerce | CRUD on line items and products | Product deletion is non-cascading |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document FormsAgent, DataAgent, CommerceAgent"
```

---

### Task 7.2: Audit Log Verification

**Files:**
- Modify: `src/hubspot_agent/orchestrator.py`
- Modify: `tests/test_audit_new_agents.py`

- [ ] **Step 1: Ensure every execution path appends to `audit_log`**

Verify that `_execute_*` and `_reconcile_*` functions append to the audit_log list passed by reference. If any path misses it, add the append.

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS (all tests green)

- [ ] **Step 3: Commit**

```bash
git add src/hubspot_agent/orchestrator.py tests/test_audit_new_agents.py
git commit -m "fix(audit): ensure all execution paths append to audit_log"
```

---

## Phase 8: Final Integration

### Task 8.1: End-to-End Smoke Test

**Files:**
- None (manual verification)

- [ ] **Step 1: Run the CLI locally**

```bash
python -m hubspot_agent.cli /hubspot setup --portal-id 123
python -m hubspot_agent.cli /hubspot status
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from hubspot_agent.orchestrator import _PREVIEW_BUILDERS, _EXECUTE_DISPATCH, _RECONCILE_DISPATCH; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit any fixes**

If smoke test surfaces issues, fix and commit with message:

```bash
git commit -m "fix: resolve import issues from e2e smoke test"
```

---

## Verification Rubric

Before marking complete, confirm:

- [ ] `pytest tests/` passes with zero failures.
- [ ] `python -m hubspot_agent.cli /hubspot status` runs without import errors.
- [ ] `src/hubspot_agent/agents/__init__.py` exports 4 agents (objects, forms, data, commerce).
- [ ] `src/hubspot_agent/orchestrator.py` has `_PREVIEW_BUILDERS`, `_EXECUTE_DISPATCH`, `_RECONCILE_DISPATCH` populated for all 4 agents.
- [ ] `~/.hubspot-agent/pending_previews/` is created on first preview and cleaned after execution.
- [ ] `initialize_session` calls `warm_standard_schemas` and `discover_custom_schemas`.
- [ ] Each new agent has a system prompt, tool list, and dispatch functions.
- [ ] Audit log contains entries for every execution path.

---

**Plan complete.**
