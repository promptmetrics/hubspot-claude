# Code Review Findings — 2026-07-14

Full-repository review of `hubspot-agent` 0.2.1, conducted by four parallel
reviewers over the HITL safety core, auth/infrastructure security, CLI/loop
orchestration, and blueprints/tools. Findings are grouped by severity and
annotated with file:line, a one-line defect statement, a concrete failure
scenario, and reviewer confidence.

Status legend: **OPEN** (not yet addressed) · **FIXING** (in progress in the
current PR) · **FIXED** (verified by tests).

---

## Fix status (PR `fix/hitl-bypass-and-loop-safety`)

Verified with the full suite: **978 passed, 3 skipped** (12 new regression
tests added).

- **H1 — FIXED.** Mutating tools now route through the HITL gate.
- **H3 — FIXED.** The daemon rejects mismatched-portal calls; the router
  restarts a daemon bound to the requested portal.
- **H2 — PARTIALLY FIXED.** Three sub-bugs closed (escalate/escalated drift,
  `intent_type`/`proposed_payload` key mismatch, auto-approve default now fails
  closed). Two items remain OPEN and need a product decision, not a bug fix:
  the CLI loop path has no way to collect approval in its synchronous
  return model (so loop writes are now *denied* rather than *auto-executed* —
  safe, but the loop can't write until a deferred-approve UX lands), and the
  agent runtime is absent (`spawn_agent` cannot import `claude_code`). The
  execute-mode "fabricate success for preview-only agents" fallback is also
  still OPEN. See H2 below for the split.

---

## HIGH

### H1 — Mutating tools bypass the HITL approve gate (scope-registry drift)
- **Files:** `handlers.py:64-70` (gate at `:178`), `scope_registry.py` `_TOOL_SCOPES`, `cli.py:1118`
- **Status:** **FIXED**
- **Fix:** added the seven always-write no-suffix tools (refund, import, export,
  create_form, create_report, create_dashboard, schedule_email) to
  `scope_registry.WRITE_TOOLS`, and made `handlers._is_write_tool` /
  `_tool_risk_level` / `_tool_intent_type` method-aware for `hubspot_raw_api`
  (POST/PATCH/PUT/DELETE = write; DELETE = destructive; GET stays a read). Both
  call paths (`handle_tool`, CLI `_handle_tool`) share the predicate. Registry
  scope *emission* was left unchanged deliberately — those CRM scopes aren't
  requested at authorize time, so classifying via `WRITE_TOOLS` avoids a
  scope-precheck regression on OAuth portals. Regression tests:
  `tests/test_cli_tool_dispatch.py` (`test_empty_scope_write_tools_route_through_apply_write`,
  `test_raw_api_get_is_read_path`, `test_raw_api_mutating_methods_route_through_apply_write`).
- **Defect:** `_is_write_tool()` classifies a tool as a write only if a required
  scope ends in `.write`/`.delete` or the tool name is in `WRITE_TOOLS`. Several
  genuinely mutating tools have a `_TOOL_SCOPES` entry of `set()` or a read-only
  scope and are not in `WRITE_TOOLS`, so they execute directly with no preview,
  approval, destructive-count gate, undo snapshot, or audit entry.
- **Affected tools:** `hubspot_raw_api` (POST/PATCH/DELETE to any endpoint),
  `hubspot_create_refund` (moves money), `hubspot_import_data` (bulk
  import/overwrite), `hubspot_create_form`, `hubspot_schedule_email` (recurring
  data egress), `hubspot_create_report`, `hubspot_create_dashboard`,
  `hubspot_export_data`.
- **Scenario:** `hubspot tool hubspot_raw_api --input '{"method":"DELETE","path":"/crm/v3/objects/contacts/123"}'`
  deletes a record with zero human-in-the-loop confirmation.
- **Root cause:** same bug class as the 0.2.0 `WRITE_TOOLS` workflow fix; the fix
  stopped at workflow tools. The registry scopes disagree with the
  `expected_scopes` each tool already sends to the client (which carry `.write`).
- **Fix direction:** reconcile `_TOOL_SCOPES` with each tool's real
  `expected_scopes`; make `raw_api` method-aware (POST/PATCH/DELETE = write). Do
  not classify by tool-name heuristics (per ADR).
- **Confidence:** high (independently reported by two reviewers).
- **Note:** distinct from the previously-refuted "deletes bypass FR-19" finding,
  which was about scope *emission* (correct). This is about tools whose registry
  scope set is *empty*, so classification never runs.

### H2 — Durable-loop path diverges from the safety contract
- **Files:** `cli.py:205,208,823`, `sequential_dispatch.py:194,225,148,265`,
  `orchestrator.py:430-434,461-467,607,721`, `agent_dispatch.py:34-41`
- **Status:** **PARTIALLY FIXED**
- **Fixed in this PR:**
  - Auto-approve default flipped to fail-closed: `execute_single_step` now
    denies a write with no `approve_callback` instead of running
    `lambda _: True`. A caller that wants a loop to write must pass an explicit
    callback. (`sequential_dispatch.py`)
  - Key-name mismatch: `dispatch_agent`'s preview `AgentResult.data` now emits
    `intent_type` (was `impact_type`, which the executor never read) and
    `proposed_payload` (was absent, so creates ran with empty properties).
    (`orchestrator.py`)
  - Escalation resume-gate drift: the resume-clear set now matches the
    `"escalate"` status the controller actually writes (was `"escalated"`), so
    an escalated loop no longer resumes past its human-review halt.
    (`orchestrator.py:607`)
  - Tests updated to the new contract (explicit `approve_callback`) in
    `test_sequential_dispatch.py`, `test_orchestrator_loop.py`,
    `test_snapshot_wiring.py`.
- **Still OPEN (needs a product decision / new subsystem, not a bug fix):**
  - The CLI invokes `run_loop` with no approval callback, and its synchronous
    return model can't prompt interactively. With fail-closed in place, loop
    writes are now *denied* (safe) rather than *auto-executed* (unsafe) — but the
    loop cannot perform writes via the CLI until a deferred-approval UX
    (preview → persist → `approve <id>` → resume) is designed and wired.
  - `spawn_agent` does `from claude_code import Agent`, which always
    `ImportError`s — there is no agent runtime, so triage/verify are
    non-functional in production. This is a missing integration, not a defect to
    patch here.
  - Execute-mode fallback still returns `status="success"` for preview-only
    agents with no execute handler (`orchestrator.py:461-467`).
- **Defect:** the loop path bypasses `execute_pending_write` on multiple axes.
  `use_loop = loop_flag or len(agent_names) > 1` routes *any* multi-domain request
  here, not just `--loop`.
  - Both `run_loop` call sites omit `approve_callback`, so it defaults to
    auto-approve (`lambda _: True`). Execute dispatch calls execute functions
    directly — no destructive-count re-check, no `audit.log_write`; the pending
    preview from the preview pass is orphaned.
  - `sequential_dispatch.py:225` reads a `proposed_payload` key the preview data
    never contains (the key is `impact_type`, not `intent_type`; there is no
    `proposed_payload`), so creates run with empty properties — a blank record
    instead of the intended one.
  - `impact_type` vs `intent_type` mismatch → loop-path undo snapshots get
    `undoable: False`; created IDs never written back → loop-path creates can
    never be undone.
  - `spawn_agent` does `from claude_code import Agent`, which always
    `ImportError`s (not a real package); triage returns a placeholder and
    `verify_step` treats `[agent:...]` results as VERIFIED — verification is a
    permanent no-op.
  - Status-string drift: escalation sets `state.status = "escalate"`
    (`orchestrator.py:721`) but the resume-clear check looks for `"escalated"`
    (`:607`), so an escalated loop resumes past its human-review gate and re-runs
    the write that triggered escalation.
  - Execute-mode fallback returns `status="success"` for agents with no execute
    handler (`orchestrator.py:461-467`) — a never-attempted step is marked done.
- **Scenario:** a multi-domain request routes to `run_loop`; a create step runs
  with empty props (blank record) under auto-approve, verify is a no-op, and the
  step is marked verified with no audit trail.
- **Fix direction:** either route the loop path through `execute_pending_write`
  or gate `run_loop` behind an explicit approval callback; fix the
  `proposed_payload`/`intent_type` key names and the `escalate`/`escalated`
  drift either way.
- **Confidence:** high.

### H3 — Daemon ignores `--portal`
- **Files:** `router.py:44-45,230-238`, `daemon.py:205`
- **Status:** **FIXED**
- **Fix:** the router now includes `portal_id` in the `tool` RPC params; the
  daemon's `_process_line` rejects a call whose `portal_id` differs from the
  portal it was warmed for (`kind: portal_mismatch`), and the router treats that
  rejection like a crash — kill the daemon, restart one bound to the requested
  portal, retry once, else fall back in-process. Also hardened: non-dict
  `params` now yields a structured validation error. Regression test:
  `tests/test_daemon.py::test_daemon_rejects_mismatched_portal`.
- **Defect:** the Unix socket is global (one `hubspot.sock` per plugin data dir).
  `_daemon_tool_path` sends `{tool_name, input, batch_mode}` with no portal, and
  `is_daemon_alive()` never checks which portal the live daemon serves. The
  handler uses `self.portal_config`.
- **Scenario:** a daemon lazily started for portal A is alive; the operator runs
  a tool with `--portal B`. The read returns portal A's data and a write preview
  is stored under portal A's pending dir, so `approve --portal B` reports
  not-found while a live preview sits against the wrong portal.
- **Root cause:** same class as the 0.2.1 CLI `--portal` fix, surviving on the
  daemon path.
- **Fix direction:** include the portal in the RPC params and verify it against
  the running daemon (restart or fall back in-process on mismatch).
- **Confidence:** high.

---

## MEDIUM

### M1 — OAuth `state` path traversal can delete portal credentials
- **Files:** `auth.py:36-37,62-64`
- **Status:** OPEN
- **Defect:** `_oauth_state_file(state)` interpolates `state` (from the pasted
  callback URL) into a filesystem path with no charset validation. A state of
  `../<portal_id>` resolves to the portal token file; `_load_oauth_state` then
  unlinks it (private-app configs have no `expires_at` → treated as expired).
- **Scenario:** the user pastes an attacker-crafted callback URL during setup →
  stored token/refresh-token destroyed → forced re-auth (DoS).
- **Fix:** validate `state` against `[A-Za-z0-9_-]+` before path construction.
- **Confidence:** high mechanics, medium exploitability.

### M2 — Tokens/secrets written world-readable before chmod (TOCTOU)
- **Files:** `config.py:108-109`, `app_credentials.py:45-46`, `auth.py:53-54`
- **Status:** OPEN
- **Defect:** `write_text(...)` then `chmod(0o600)` creates the file with the
  process umask (often world-readable) and narrows afterward. Another local user
  can read the token/refresh-token/`client_secret` in the window.
- **Fix:** create with `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)` or write a
  0o600 temp file then rename (see `persistence.py:44`).
- **Confidence:** high.

### M3 — Daemon socket world-accessible; chmod failure swallowed
- **Files:** `daemon.py:121,128`
- **Status:** OPEN
- **Defect:** the socket is created with the process umask; the narrowing
  `chmod(0o600)` happens after bind and its `OSError` is ignored (`pass`). Any
  local user who connects can issue `approve` to execute a pending destructive
  write — the daemon does not authenticate the peer.
- **Fix:** create the socket in a `0o700` directory and/or set umask before bind;
  treat a chmod failure as fatal.
- **Confidence:** high on design; risk gated by single-user machines.

### M4 — `action_id`/`portal_id` path traversal in pending-preview store
- **Files:** `persistence.py:63,73,124`
- **Status:** OPEN
- **Defect:** `action_id` and `portal_id` are interpolated into the pending file
  path with no validation. A crafted `approve`/`reject` value with `../` escapes
  the pending dir to read/unlink/overwrite arbitrary `*.json`.
- **Fix:** validate `action_id` against its mint format (`^[0-9a-f]{8}$`) and
  reject path separators; validate `portal_id`.
- **Confidence:** high (same-trust-domain, defense-in-depth).

### M5 — Destructive `merge` writes record no undo snapshot
- **Files:** `handlers.py:301`, `snapshot.py:38`
- **Status:** OPEN
- **Defect:** the snapshot guard checks `create/update/delete` but
  `_tool_intent_type` returns `"merge"` for `hubspot_merge_objects`; merge is
  destructive (write+delete) yet no undo artifact is captured.
- **Confidence:** high.

### M6 — Checkpoint records phantom successes on chunk failure
- **Files:** `tools/objects.py:215,237`, `tools/hygiene.py:103-107`
- **Status:** OPEN
- **Defect:** on a chunk-level exception, `record_chunk` logs
  `len(chunk) - len(chunk_errors)` as succeeded — e.g. 99/100 for a chunk where
  zero records landed. Resume then skips records that were never written, and
  `succeeded + failed != total`.
- **Confidence:** high.

### M7 — Batch update payloads include read-only `id` keys
- **Files:** `tools/objects.py:158-162`
- **Status:** OPEN
- **Defect:** update inputs are `{"id": ..., "properties": record}` where
  `record` still contains `id`/`hs_object_id`; HubSpot batch update rejects
  unknown/read-only property names, likely 400-ing the whole batch.
- **Confidence:** medium.

### M8 — `object_type` unvalidated in hygiene URL paths
- **Files:** `tools/hygiene.py:31,93,123`
- **Status:** OPEN
- **Defect:** `object_type` is interpolated into the URL with no
  `_validate_object_type`. A crafted value (e.g. `contacts/batch/archive?`) can
  redirect a MEDIUM-risk bulk update to the archive endpoint (mass delete)
  without tripping the destructive-count gate.
- **Confidence:** medium.

### M9 — `hubspot_merge_objects` hardcodes the contacts endpoint
- **Files:** `tools/hygiene.py:53-72`
- **Status:** OPEN
- **Defect:** named/classified generically but POSTs to
  `/crm/v3/objects/contacts/merge`; merging two companies silently merges two
  contacts with those IDs, and the HITL preview (two bare IDs) can't reveal it.
- **Confidence:** high.

### M10 — Capabilities probe uses the wrong endpoint; poisons cache 24h
- **Files:** `capabilities.py:91-142` (probe at `:105`), `tools/service.py:104`
- **Defect:** the workflows probe hits `GET /automation/v4/workflows`, but the
  real V4 endpoint is `/automation/v4/flows`. Live portals 404 →
  `workflows = False`, cached 24h → every workflows agent declined. Every probe
  also catches bare `Exception` and caches the poisoned matrix unconditionally,
  so one transient failure disables workflow/user/marketing agents for a day.
- **Status:** OPEN
- **Confidence:** medium-high on the endpoint; high on the cache-poisoning.

### M11 — 5s RPC timeout kills healthy daemon and re-executes writes
- **Files:** `router.py:34,200-204,239-253`, `cli.py:959-963`
- **Defect:** a tool call slower than `RPC_TIMEOUT = 5.0` gets the daemon
  SIGTERM'd mid-request, retried (re-executing), then run a third time
  in-process — each write pass persists a distinct pending preview. Separately,
  `--input -` stdin is consumed before the daemon call and lost on fallback,
  yielding a write preview for `{}`.
- **Status:** OPEN
- **Confidence:** high.

### M12 — Crash between execute and checkpoint double-executes; ledger unwired
- **Files:** `orchestrator.py:660-730,678`, `ledger.py`
- **Defect:** `loop_state.save` runs only after verify + `current_step += 1`; a
  crash after the live write re-executes it on resume. `ActionLedger` was built
  to prevent this but has zero call sites. `run_loop` catches only `RuntimeError`,
  so a `HubSpotError` escapes without saving `failed` status.
- **Status:** OPEN
- **Confidence:** high on code; requires a crash/exception mid-step.

### M13 — `undo` deletes the snapshot even when the undo did nothing
- **Files:** `cli.py:722-723`
- **Defect:** `delete_undo_snapshot` runs unconditionally after `_undo_action`,
  which returns failure strings ("not undoable", "no created IDs recorded")
  without touching HubSpot — deleting the one artifact allowing manual
  reconciliation.
- **Status:** OPEN
- **Confidence:** high.

---

## LOW

- **L1** — Undo snapshots written non-atomically with no fsync
  (`snapshot.py:70,89`); a crash mid-write leaves truncated JSON.
- **L2** — `_atomic_write_json` fsyncs the temp file but not the parent directory
  (`persistence.py:45`); rename not guaranteed durable across power loss.
- **L3** — Destructive-count "re-check" compares against the stored preview count,
  not a live re-query (`handlers.py:275-292`); safe today (explicit id lists) but
  a future destructive-by-filter tool would defeat the gate.
- **L4** — `_error_budget_exceeded` requires `state.last_error`, set only where
  the loop returns terminally immediately after (`loop_controller.py:138-140`) —
  budget can never trip.
- **L5** — `loop_state.load()` returns `None` on corrupt JSON, treated as "no
  loop" → re-triage and re-execute from step 0 (`loop_state.py:98-110`).
- **L6** — Call-path error divergence: daemon returns structured `error:` string;
  in-process CLI lets `HubSpotError` escape as a raw traceback
  (`cli.py:1080-1120`, `router.py:210-217`).
- **L7** — `redact_dict_for_disk` matches only email/phone/name; API tokens/keys
  pass through, and `audit.log` has no explicit chmod
  (`redaction.py:11-12`, `audit.py:31`).
- **L8** — daemon stdout/stderr and self-heal pip output go to `install.log` with
  no restrictive mode; exception text may carry response bodies
  (`router.py:146`, `daemon.py:222`).
- **L9** — Blueprint parameterize drops every flag whose value equals the old
  value, not just the edited path (`tools/blueprint_library.py:222-225`).
- **L10** — `param_name` unvalidated against the token grammar
  (`tools/blueprint_library.py:211`); a bad name writes an unsubstitutable
  `{{param:...}}` literal into the created workflow.
- **L11** — `resolve_object_type_id` silently falls back to contacts (`0-1`) for
  unrecognized object types (`blueprints/workflows/action_type_map.py:227-233`).
- **L12** — `_walk` never breaks on revisit; a cyclic action graph loops forever
  (`blueprints/workflows/extractor.py:239-281`).
- **L13** — `validate_blueprint` checks only top-level actions; nested
  `true_branch` actions fail later as a bare `KeyError`
  (`blueprints/workflows/schema.py:208-218,163`).
- **L14** — `SchemaCache._save` is a bare `write_text` (no flock/atomic rename)
  (`cache.py:113-115`); concurrent daemon+CLI writes can tear the file
  (silent refetch, not corruption).
- **L15** — `report_id` interpolated without `quote()`
  (`tools/reporting.py:52`, `tools/analytics.py:18`); `deal_splits.py:41` vs `:56`
  validates with `.get` then subscripts, raising `KeyError` instead of a clean
  error.
- **L16** — `detect_default_portal` returns the raw `.hubspot-portal` string;
  validated only at leaf path-builders (`config.py:38`).

---

## Clean (checked and cleared)

TLS verification (httpx defaults, no `verify=False`); SSRF (region allowlist +
fixed host); shell injection in `bin/hubspot` / `install.sh` (quoted, list-form
Popen, no `curl|sh`, `set -u`); OAuth PKCE + state expiry + portal binding;
blueprint-name path traversal (`_slug` sanitizes); the `tools/__init__.py`
pkgutil registry walk; audit-log injection (`json.dumps` per line escapes
newlines); JSON-RPC method dispatch validation; dispatch-table parity (all 34
execute-registered agents are reconcile-registered); `models.py`, `maintenance.py`,
`learning_log.py`.

**Strongest code:** `execute_pending_write` (`handlers.py:253-455`) — correct
snapshot-before-write ordering, drop-snapshot-keep-pending retry contract, and
create-without-id reasoning. `loop_state.save`'s flock+fsync+rename is the
template the ledger/log/cache writers should copy.
