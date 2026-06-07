# Real Estate Workflow Blueprints: Build Notes & Gotchas

> Reverse-engineered from portal 148408595 via live API testing against HubSpot's V4 Flows API (`/automation/v4/flows`).
> Last updated: 2026-05-13.

---

## What's Still Missing (Overall Project)

The real estate blueprint pipeline (19 workflows + converter + action type map) is **complete and tested**. The broader hubspot-agent project has these items remaining:

1. ~~**`src/hubspot_agent/research.py`**~~ — **Done.** `RESEARCH_PROMPT_BLOCK` and `classify_url()` are implemented and injected into sub-agent prompts.
2. ~~**`objects.py` batch_upsert bug**~~ — **Done.** Deduplicated; create and update chunks are processed once each.
3. ~~**Custom objects agent**~~ — **Done.** `agents/custom_objects.py` is fully wired with CRUD tools, registered in the orchestrator, and covered by tests.
4. **Full HITL wiring** — `orchestrator.py` has routing, scope validation, and dispatch. The `present_preview` rendering of `informing_sources` and post-timeout reconciliation exist but may need integration testing against the CLI.
5. **Integration test completeness** — `tests/test_integration.py` exists but may not cover the full happy path (read → preview → approve → execute → audit).
6. ~~**Type checking**~~ — **Done.** `mypy src/hubspot_agent --ignore-missing-imports` passes with zero errors.
7. ~~**Code coverage**~~ — **Done.** `pytest --cov` is at 81%+ (target >80%).

---

## V4 Flows API: Reverse-Engineered Decisions

### 1. All Object Creation Uses the Same Unified Event ID

**Decision:** Map every creation trigger (contact, offer, showing, etc.) to `4-1463224`.

**Why:** The HubSpot V4 "Unified Events" system uses a single generic event type ID for "CRM Object created" regardless of which object type is involved. The workflow's `objectTypeId` restricts which object actually triggers enrollment. This was discovered by:
- Web searching for "HubSpot unified events eventTypeId"
- Creating test workflows manually and reading them back via `GET /automation/v4/flows/{id}`
- Observing that contact creation and custom-object creation workflows both used `4-1463224` in `eventFilterBranches`

**Gotcha:** The API returns a generic 400 if you guess the wrong eventTypeId. There is no public list.

---

### 2. EVENT_BASED Enrollment Requires Flat Filters (No Nested filterBranches)

**Decision:** In `_build_enrollment_criteria`, flatten nested `filterBranches` into a single `filters` array when `type == "EVENT_BASED"`.

**Why:** The V4 API accepts nested `filterBranches` inside `listFilterBranches` (PROPERTY_BASED/LIST_BASED enrollment) but rejects them inside `eventFilterBranches`. Attempting to nest causes a 400 validation error.

**Code:** `converter.py:296–299`

```python
filters: list[dict[str, Any]] = []
for nested in filter_branch.get("filterBranches", []):
    filters.extend(nested.get("filters", []))
```

---

### 3. Branch Names Have a 50-Character Hard Limit

**Decision:** Truncate `branchName` to 50 characters in `_build_branch_node`.

**Why:** Discovered through binary search. Branch names of 50 chars succeed; 51 chars return HTTP 500 (not 400). This is a server-side bug — the API should return 400 with a validation message.

**Isolation test:**
- Created branches with names 30, 35, 40, 45, 50, 51, 55 characters
- 50 worked; 51 returned 500

**Code:** `converter.py:249`

```python
"branchName": f"{cond_property} {operator} {value}"[:50],
```

---

### 4. Task Due Time Does Not Support `YEARS`

**Decision:** Convert years to months (`* 12`) in `_parse_due`.

**Why:** The `due_time` field for `Create task` (`actionTypeId: 0-3`) accepts `MINUTES`, `HOURS`, `DAYS`, `MONTHS` but returns HTTP 500 for `YEARS`. Tested `MONTHS` (works) and `YEARS` (fails).

**Code:** `converter.py:51–53`

```python
m = re.search(r"\+\s*(\d+)\s*(year|years)", raw)
if m:
    return int(m.group(1)) * 12, "MONTHS"
```

---

### 5. Numeric Branch Conditions Need `operationType: "NUMBER"`

**Decision:** Detect numeric operators (`IS_GREATER_THAN`, `IS_LESS_THAN`, etc.) and emit `operationType: "NUMBER"` with a scalar `value`.

**Why:** Using `ENUMERATION` with `values: [value]` for numeric comparisons returns 400. The V4 API requires `NUMBER` type with a scalar `value` field.

**Code:** `converter.py:213–218`

```python
operation = {
    "operationType": "NUMBER",
    "operator": api_op,
    "value": int(value) if str(value).isdigit() else value,
    "includeObjectsWithNoValueSet": False,
}
```

---

### 6. Date Filters Must Use `ROLLING_DATE_RANGE`

**Decision:** Update `re_stale_buyer_deal.py` to use `ROLLING_DATE_RANGE` with `numberOfDays` and `requiresTimeZoneConversion`.

**Why:** Using `ALL_PROPERTY` with `IS_MORE_THAN_X_DAYS_AGO` returns 400. The V4 API requires `ROLLING_DATE_RANGE` for rolling date operators.

**Before (broken):**
```python
{"operationType": "ALL_PROPERTY", "operator": "IS_MORE_THAN_X_DAYS_AGO", ...}
```

**After (working):**
```python
{"operationType": "ROLLING_DATE_RANGE", "operator": "IS_MORE_THAN_X_DAYS_AGO", "numberOfDays": 14, "includeObjectsWithNoValueSet": False, "requiresTimeZoneConversion": False}
```

---

### 7. Task Owner Assignment Is Not Supported in V4 Create Task

**Decision:** Strip `Assigned to` from `Create task` blueprint fields. The API silently ignores owner assignment in action fields.

**Why:** Tested multiple owner assignment formats (`hubspot_owner_id`, `owner_id`, `user_id`, `assigned_to`) in the `0-3` action fields. All were accepted but had no effect. Owner assignment appears to only work through the UI or through separate object update actions.

**Gotcha:** The blueprint still includes `Assigned to` in the UI spec (for manual creation instructions) but the converter ignores it when building the API payload.

---

### 8. Property-Relative Due Dates Are Unsupported

**Decision:** Raise `ValueError` in `_parse_due` for dates like `{{deadline - 5d}}`.

**Why:** The V4 API only supports fixed offsets from enrollment time (`{{timestamp + Xm}}`). Property-relative due dates (e.g., `{{contingency_appraisal_deadline - 5d}}`) have no equivalent in the V4 `due_time` schema.

**Workaround:** Blueprints with property-relative due dates are marked `SKIP` during auto-creation and include manual UI instructions.

**Affected blueprints:**
- `re_buyer_appraisal_alert` (`{{contingency_appraisal_deadline - 5d}}`)
- `re_buyer_financing_alert` (`{{contingency_financing_deadline - 5d}}`)
- `re_buyer_inspection_alert` (`{{contingency_inspection_deadline - 3d}}`)
- `re_vendor_expiry` (`{{license_expiration_date - 30d}}`)

---

### 9. Custom Properties Must Exist Before Workflow Creation

**Decision:** Blueprint prerequisites must list required custom properties. The converter does not create them automatically.

**Why:** The V4 API returns 400 for enrollment filters referencing non-existent properties. The error is generic (`"Invalid request to flow creation"`) and provides no field-level detail.

**Isolation test:**
- Created a deal-based workflow with `dealname` (exists) → OK
- Created the same workflow with `last_showing_date` (missing) → ERROR 400
- Created `last_showing_date` property → same blueprint → OK

**Properties created in portal 148408595:**
- `contacts`: `price_range_max`, `preferred_neighborhoods`, `last_engagement_date`
- `deals`: `last_showing_date`

**Gotcha:** Property labels must be unique across a portal. `last_engagement_date` initially failed because its label collided with `hs_last_sales_activity_timestamp`. Fixed by using label `"Last Engagement Date (Custom)"`.

---

### 10. Deal Stages Must Exist Before Workflow Creation

**Decision:** Blueprint prerequisites must list required deal stages. The converter does not create pipelines/stages automatically.

**Why:** Similar to custom properties — referencing a non-existent stage in an enrollment filter returns 400.

**Stage created in portal 148408595:**
- `activebuyer` in Buyer Pipeline (`pipelineId: 3802390752`)

---

### 11. Marketing Email Requires Pre-Created `content_id`

**Decision:** Blueprints using `Send marketing email` require a valid `content_id` and are marked `SKIP` if a placeholder is provided.

**Why:** The `0-4` action type requires a `content_id` referencing an existing marketing email. There is no API to create marketing emails on-the-fly from a subject/body.

**Affected blueprints:**
- `re_anniversary_touch`
- `re_open_house_followup`

---

### 12. Rotate Leads Requires Pre-Created Team ID

**Decision:** Blueprints using `Rotate leads` require a valid `team_id` and are marked `SKIP` if a placeholder is provided.

**Why:** The `0-11` action type requires `team_ids` array with existing team IDs. No API to create teams from blueprint parameters.

**Affected blueprint:**
- `re_hygiene_unassigned`

---

## Blueprint Converter Architecture Decisions

### Why UI Spec → V4 Payload Instead of Direct API?

The original design returned UI instructions because the V4 API was undocumented. The converter bridges this gap:

1. **Blueprints define UI specs** — human-readable actions, enrollment triggers, prerequisites
2. **`converter.py` transforms** UI actions → V4 action nodes with correct `actionTypeId`, `connection` edges, and `enrollmentCriteria`
3. **`action_type_map.py`** holds the reverse-engineered mapping from UI action names → V4 action type metadata

This two-layer approach means:
- Blueprints remain readable for manual creation
- Auto-creation works for supported action types
- Unsupported features fail fast with descriptive `ValueError` messages

### Graph Building

Workflows are DAGs. `_build_graph` recursively connects action nodes:

- Sequential actions: `connection: {edgeType: "STANDARD", nextActionId: "N"}`
- Branch nodes: `LIST_BRANCH` with `yes_next_id` and `default_next_id`
- True branch contents are recursively built and appended after the branch node

Action IDs are sequential integers starting at 1. `_size()` accounts for nested true branches to compute correct continuation IDs.

---

## Action Type Registry

Reverse-engineered from portal 148408595:

| UI Action | actionTypeId | Version | type |
|-----------|--------------|---------|------|
| Delay | 0-1 | 0 | SINGLE_CONNECTION |
| Delay until date | 0-35 | 0 | SINGLE_CONNECTION |
| Create task | 0-3 | 0 | SINGLE_CONNECTION |
| Set property value | 0-5 | 0 | SINGLE_CONNECTION |
| Send marketing email | 0-4 | 0 | SINGLE_CONNECTION |
| Send internal email notification | 0-8 | 0 | SINGLE_CONNECTION |
| Add to static list | 0-63809083 | 5 | SINGLE_CONNECTION |
| Rotate leads | 0-11 | 0 | SINGLE_CONNECTION |

**Unsupported (not in registry):**
- Create record (custom object)
- Set record property
- Send notification to team
- Create deal
- Rotate leads to contact
- Set lifecycle stage
- Trigger webhook
- Send Slack message

These were discovered by creating a manual workflow in the UI and reading it back via the API.

---

## Testing Strategy

### End-to-End Blueprint Test

```python
async def test_blueprint(name):
    blueprint = get_blueprint(name)
    spec = blueprint.build({})
    payload = blueprint_to_v4_payload(spec)
    # POST to /automation/v4/flows
    # DELETE immediately after creation
```

### Portal State Requirements

Before running the full suite, ensure:
1. Contact properties: `price_range_max`, `preferred_neighborhoods`, `last_engagement_date`
2. Deal property: `last_showing_date`
3. Deal stage: `activebuyer` in a pipeline
4. Marketing emails exist (for `re_anniversary_touch`, `re_open_house_followup`)
5. Team exists (for `re_hygiene_unassigned`)

### Expected Results

| Status | Count | Reason |
|--------|-------|--------|
| OK | 14 | Auto-creates successfully |
| SKIP | 5 | Unsupported V4 feature (due date, placeholder) |
| SKIP | 2 | Missing prerequisite (marketing email, team) |
| ERROR | 0 | None (after fixing property/stage issues) |

---

## Recommendations for Plugin Developers

1. **Always validate portal prerequisites before workflow creation.** The V4 API error messages are opaque for missing properties/stages.
2. **Test each action type in isolation first.** Create a minimal workflow with one action, read it back, and compare the payload structure.
3. **Use `[TEST]` prefix for temporary workflows** and clean them up immediately.
4. **Document action type IDs as they are discovered.** HubSpot does not publish a public registry.
5. **Watch for silent API behavior.** Task owner assignment is accepted but ignored. Always verify actions have the intended effect.
6. **Property labels must be unique.** Creating a property with a colliding label returns `VALIDATION_ERROR` with the conflicting property name in the error context.
