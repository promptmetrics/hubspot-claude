# HubSpot Agent Build Pipeline — Task Tracker

**Created:** 2026-05-20
**Scope:** All Phases 0-14 Complete
**Branch:** feat/phase-b-intelligence-ux
**Status:** ALL PHASES COMPLETE — 562 tests passing, 32 agents registered

---

## Completed This Run (Phases 10-14)

### Phase 10: Engagement & Leads
- [x] Scaffold `agents/communications.py` with preview/execute/reconcile handlers
- [x] Scaffold `agents/leads.py` with preview/execute/reconcile handlers
- [x] Register both in `agents/__init__.py` and all 3 dispatch tables
- [x] Write tests

### Phase 11: Projects & Library
- [x] Scaffold `agents/projects.py` with preview/execute/reconcile handlers
- [x] Scaffold `agents/object_library.py` (read-only, preview only)
- [x] Register both in `agents/__init__.py` and dispatch tables
- [x] Write tests

### Phase 12: Automation & Scheduler
- [x] Scaffold `agents/sequences.py` (read + enroll, all 3 dispatch tables)
- [x] Scaffold `agents/scheduler.py` (read-only, preview only)
- [x] Register both in `agents/__init__.py` and dispatch tables
- [x] Write tests

### Phase 13: Account & Analytics
- [x] Scaffold `agents/account_info.py` (read-only, preview only)
- [x] Scaffold `agents/audit_logs.py` (Enterprise-only, read-only, preview only)
- [x] Scaffold `agents/security_history.py` (read-only, preview only)
- [x] Scaffold `agents/email_events.py` (legacy, read-only, preview only)
- [x] Register all 4 in `agents/__init__.py` and dispatch tables
- [x] Write tests

### Phase 14: Forecasts (Beta) & Timeline
- [x] Scaffold `agents/forecasts.py` (read-only beta, preview only)
- [x] Scaffold `agents/timeline_events.py` with preview/execute/reconcile handlers
- [x] Register both in `agents/__init__.py` and dispatch tables
- [x] Write tests

---

## Test Results

| Suite | Tests | Status |
|---|---|---|
| Full suite | 562 | ALL PASSING |
| `test_agents_phase10_14.py` | 43 | PASS |

---

## New / Modified Files (This Run)

| File | Action | Description |
|---|---|---|
| `src/hubspot_agent/agents/communications.py` | **NEW** | CommunicationsAgent (standard object) |
| `src/hubspot_agent/agents/leads.py` | **NEW** | LeadsAgent (standard object) |
| `src/hubspot_agent/agents/projects.py` | **NEW** | ProjectsAgent (standard object) |
| `src/hubspot_agent/agents/timeline_events.py` | **NEW** | TimelineEventsAgent (standard object) |
| `src/hubspot_agent/agents/object_library.py` | **NEW** | ObjectLibraryAgent (read-only config) |
| `src/hubspot_agent/agents/account_info.py` | **NEW** | AccountInfoAgent (read-only portal info) |
| `src/hubspot_agent/agents/audit_logs.py` | **NEW** | AuditLogsAgent (read-only Enterprise) |
| `src/hubspot_agent/agents/security_history.py` | **NEW** | SecurityHistoryAgent (read-only) |
| `src/hubspot_agent/agents/email_events.py` | **NEW** | EmailEventsAgent (read-only legacy) |
| `src/hubspot_agent/agents/forecasts.py` | **NEW** | ForecastsAgent (read-only beta) |
| `src/hubspot_agent/agents/sequences.py` | **NEW** | SequencesAgent (read + enroll) |
| `src/hubspot_agent/agents/scheduler.py` | **NEW** | SchedulerAgent (read-only meeting links) |
| `src/hubspot_agent/agents/__init__.py` | **MODIFY** | Added 12 new agent prompt builders to registry |
| `tests/test_agents_phase10_14.py` | **NEW** | Tests for all 12 new agents |

---

## Historical: Completed in Prior Runs

### Phase 0: Pending Preview Persistence
- [x] Extract inline preview I/O into `persistence.py`
- [x] Update orchestrator to use `persistence.py`
- [x] Update cli.py to import from `persistence.py`
- [x] Add `reap_expired()` to `persistence.py` with TTL-based cleanup

### Phase 1: Dispatch Table Refactor
- [x] Create `dispatch.py` with `_PREVIEW_BUILDERS`, `_EXECUTE_DISPATCH`, `_RECONCILE_DISPATCH` registries
- [x] Add `@register_preview`, `@register_execute`, `@register_reconcile` decorators
- [x] Refactor `_build_preview_for_intent` to registry-based dispatch with fallback
- [x] Refactor `dispatch_agent` execute branch to registry-based dispatch with fallback
- [x] Refactor `reconcile_after_timeout` to registry-based dispatch with fallback
- [x] Move ObjectsAgent logic from orchestrator into `agents/objects.py` with decorators
- [x] Fix test monkeypatches to target `hubspot_agent.agents.objects.invoke_tool`

### Phase 2: Schema Cache Warmup
- [x] Implement `initialize_session` to call `warm_standard_schemas` + `discover_custom_schemas`
- [x] Hook `reap_expired` into `initialize_session`

### Phase 3: ObjectsAgent Stabilization
- [x] ObjectsAgent registers in all 3 dispatch tables (preview + execute + reconcile)
- [x] End-to-end integration tests pass (preview → execute → reconcile)

### Phase 4: Remaining Original Agents
- [x] Register PropertiesAgent in all 3 dispatch tables
- [x] Register WorkflowsAgent
- [x] Register ListsAgent
- [x] Register PipelinesAgent
- [x] Register UsersAgent
- [x] Register HygieneAgent
- [x] Register AnalyticsAgent (preview only — read-only)
- [x] Register AssociationsAgent
- [x] Register EngagementsAgent
- [x] Register RawAPIAgent
- [x] Register CustomObjectsAgent
- [x] Register ServiceAgent
- [x] Fix test isolation bug with `persistence.CONFIG_DIR`

### Phase 5: CLI Subcommands
- [x] `/hubspot status` returns portal + agent counts (preview/execute/reconcile) + pending approvals + trace aggregates
- [x] `/hubspot refresh` re-runs `initialize_session` (schema re-warm + TTL reaper)

### Phase 6: Forms, Data, Commerce
- [x] Scaffold `agents/forms.py` with preview/execute/reconcile handlers
- [x] Scaffold `agents/data.py` with preview/execute/reconcile handlers
- [x] Scaffold `agents/commerce.py` with preview/execute/reconcile handlers
- [x] Create `tools/forms.py` with `hubspot_list_forms`, `hubspot_get_form`, `hubspot_create_form`
- [x] Create `tools/data.py` with `hubspot_import_data`, `hubspot_export_data`, `hubspot_get_import_status`
- [x] Create `tools/commerce.py` with `hubspot_list_payments`, `hubspot_get_payment`, `hubspot_create_refund`
- [x] Register all 3 in `agents/__init__.py` and all 3 dispatch tables
- [x] Write tests

### Phase 7: Pipeline Objects
- [x] Scaffold `agents/appointments.py`
- [x] Scaffold `agents/courses.py`
- [x] Scaffold `agents/listings.py`
- [x] Scaffold `agents/services.py`
- [x] Register all 4 in `agents/__init__.py` and all 3 dispatch tables
- [x] Write tests

### Phase 8: Commerce Objects
- [x] Scaffold `agents/carts.py`
- [x] Scaffold `agents/orders.py`
- [x] Scaffold `agents/quotes.py`
- [x] Scaffold `agents/subscriptions.py`
- [x] Scaffold `agents/invoices.py`
- [x] Register all 5 in `agents/__init__.py` and all 3 dispatch tables
- [x] Write tests (25 tests)

### Phase 9: Financial & Goals
- [x] Scaffold `agents/deal_splits.py` (batch-only)
- [x] Scaffold `agents/discounts.py`
- [x] Scaffold `agents/fees.py`
- [x] Scaffold `agents/taxes.py`
- [x] Scaffold `agents/goals.py`
- [x] Register all 5 in `agents/__init__.py` and all 3 dispatch tables
- [x] Write tests (16 tests)

---

## Verification Rubric

- [x] All 32 registered agents are importable from `hubspot_agent.agents`
- [x] Every agent registers in all applicable dispatch tables
- [x] Preview → Approve → Execute → Reconcile flow works end-to-end for objects agent
- [x] Pending previews persist to disk with UUID filenames
- [x] Timeout reconciliation replays pending previews on startup
- [x] `/hubspot status` returns connected portal + agent counts + pending approvals
- [x] `/hubspot refresh` invalidates SchemaCache and re-warms
- [x] 562 tests passing across all modules
