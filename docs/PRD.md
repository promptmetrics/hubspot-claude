# PRD: HubSpot-Claude Plugin

**Owner:** Izzy Aly · **Last updated:** 2026-07-21 · **Status:** In progress (v0.2.7 shipped; Phases 1–2 in flight)

> Source of truth for this project. Keep it current: update **§6 Status** and the
> **§4 Decisions log** whenever code changes scope, behavior, or a recorded choice.
> **Counts are derived, not hardcoded** — agent/tool/blueprint counts come from the
> registries (`hubspot agents list` / `hubspot tools list`). Figures here (44 agents,
> 79 tools, 19 blueprints) are accurate as of v0.2.7 and will drift; re-derive before quoting.
> **Supersedes** `docs/superpowers/specs/05-prd.md`, retained as a historical artifact of the
> v0.1.0 / 2026-05-10 "As-Built" state. Where the two disagree, this PRD is authoritative for
> current capability; `05-prd.md` remains the source for *history* and *originally-open* questions.

---

## 1. Goal

Give a solo HubSpot admin ("Alex", a RevOps manager) a persistent, conversational,
**safety-gated** CRM admin assistant: describe intent in plain English, get a read-based
preview, approve, and it's done and undoable. The business outcome is completing in
**< 60 seconds** what takes ~5 minutes of hand-clicking in the HubSpot UI, with **zero
unapproved writes** — because HubSpot exposes no dry-run API, every bulk write otherwise
carries real blast-radius risk with no preview and no undo.

## 2. Non-goals

- **Claude Cowork port.** Cowork ignores `SessionStart` hooks and breaks local-execution assumptions; that's a separate MCP-connector project (`README.md:241`).
- **Team collaboration / multi-user / RBAC / shared sessions / conversation memory.** Solo-admin tool (`05-prd.md:32-39`).
- **Undo for deletions/merges.** HubSpot exposes no un-delete/un-merge API; deletes and merges are classified non-undoable and surface that honestly at preview time.
- **External dashboard / UI.** CLI-first; output is markdown tables, diffs, and previews in the Claude session.
- **LLM-based routing.** Deliberately dead code on every production path; LLM-router stubs are retained only for test compatibility. Routing is deterministic keyword matching over a fixed 44-agent allowlist (ADR-0003).
- **Killed/deferred subsystems** (`08-roadmap.md:246-268`): DAG planner, sandbox preview, RBAC, plugin architecture v2, hooks, replay tooling, anomaly detection, reflection engine, batch coalescing, parallel write execution. *(Pattern-approval mode was un-killed 2026-07-22 — see §4 and R14 — after the divergence risk was resolved by per-record compare-and-set.)*
- **Loop autonomy (now).** Durable loops pause at every write by design; auto-applying writes *inside a loop* is explicitly Phase 3, out of scope for the current cycle.

## 3. Requirements

Numbered so code, commits, and this file can reference them precisely. Each is testable.

- **R1.** Deterministic keyword routing (Action-Selector) to ~44 stateless specialist sub-agents; CRM content never re-enters agent selection — acceptance: routing accuracy ≥ 95% on `tests/routing_corpus.yaml`, enforced in CI (ADR-0003).
- **R2.** HITL contract on every write — read-based preview → `approve <id>` → execute → undo snapshot → audit entry — identical across all three call paths (daemon / in-process / CLI) — acceptance: no `approve:<id>` audit entry exists without a human `approve`; behavior parity test across the three paths.
- **R3.** Destructive/multi-record writes require an expected record count, re-checked at execute time — acceptance: a mismatched count is refused at execute (Phase 2 re-keys this gate off `approval_tier`; see R11).
- **R4.** Scope emission via `scope_registry`, not tool-name heuristics; least-privilege, no `.delete` scopes requested at authorize time — acceptance: generated authorize URL omits `.delete` scopes.
- **R5.** Durable deferred-approval loops (`/hubspot --loop '<goal>'`) that pause at every write and resume from shared artifacts — acceptance: loop parks at `awaiting_approval`, resumes after out-of-band `approve` via pending record + audit + undo snapshot; writes land on named records (verbatim tool path).
- **R6.** Workflow blueprint learning loop (extract → parameterize → promote → create); 19 shipped JSON blueprints — acceptance: round-trip create a new workflow from an extracted+parameterized template, HITL-gated.
- **R7.** Multi-portal state isolation + `.hubspot-portal` auto-detection — acceptance: all per-portal state lives under `~/.claude/hubspot/<portal>/`; `--portal` honored by every HITL handler.
- **R8.** Warm-client daemon (Unix-socket JSON-RPC) reusing one `HubSpotClient` + schema cache — acceptance: schema-cache hit rate > 80%; daemon failure falls back to in-process without behavior change.
- **R9.** Quiet/terse output mode with hardened HITL carve-out — acceptance: step narration suppressed, but previews/approvals/count gates are never suppressed (shipped 0.2.7).
- **R10.** CI Evaluation Gate: `pytest -x` + `claude plugin validate ./` + artifact allowlist, Python 3.12, on every PR + push to main — acceptance: the `test-and-validate` check is a required, green status check (branch protection enabled).
- **R11.** Bounded Autonomy — risk-tiered approval `AUTO` / `CONFIRM` / `FULL_GATE`, config-driven thresholds + sensitive properties — acceptance: a low-risk single-record reversible write auto-applies without a count gate; destructive, over-threshold, non-undoable, and sensitive-property writes still gate; **full test suite green**.
- **R12.** Loop cost governance — enforced per-run spend ceiling with per-agent cost attribution — acceptance: a durable loop halts when its spend ceiling trips, with per-agent attribution (today's `$0.50` ceiling is inert — nothing increments it).
- **R13.** Back-pressure — proactive rate-limit pacing + per-step retry with backoff — acceptance: a bulk loop survives HubSpot rate limiting unattended (today's `_drive_loop` fails-and-stops per step).
- **R14.** Pattern approval (divergence-safe) — approve one transformation rule, scale across the matched set with per-record **compare-and-set**; reversible non-sensitive updates only (destructive/sensitive excluded → normal gate); over-threshold requires the typed matched count — acceptance: a drifted record is skipped and never overwritten; a `--pattern` request that is destructive or touches a sensitive field falls back to the per-op gate; over `pattern_confirm_threshold` requires the typed count; the continue-through report enumerates applied/skipped/failed; full suite green.

## 4. Decisions log

Append-only. Every non-trivial decision gets a dated line and one line of why.

- **(design)** Orchestration — chose the native Claude `Agent` tool over a custom 1,017-line orchestrator, for simplicity (Phase 0 rewrite; spec mandate).
- **(design)** Routing — chose a deterministic keyword Action-Selector over LLM routing, as a security property: CRM content never re-enters agent selection, structurally closing prompt-injection-via-CRM-data (ADR-0003).
- **(design)** HITL execute — chose `approve <id> [count]` with an execute-time re-check over an interactive prompt, so the count gate catches wrong-count writes.
- **0.2.4/0.2.5** — Undo made fail-closed; non-undoable ops surface at preview instead of a silent best-effort ("truthful undo").
- **0.2.3** — Durable-loop writes use the verbatim tool path (`tool_name`/`tool_input`) over free-text dispatch, because Bug 2's fuzzy payloads landed on the wrong record.
- **2026-07-21** — Approval tiers are config-driven (`approval_policy.json`) with `sensitive_property_action` default `"confirm"` (not hardcoded `full_gate`), so field-level + count thresholds are customizable per portal.
- **2026-07-21** — CI gate scope: pytest + `plugin validate` + artifact allowlist, Python 3.12 only (matching `requires-python`), using the real validator (`decision-log.md:34-44`).
- **2026-07-21** — PRD created at repo root via `/everything-claude-code:prp-prd`, then moved to `docs/PRD.md` to match the `prd-sync-check.sh` Stop hook's expected path; `docs/PRD.md` un-ignored in `.gitignore` so it is tracked. No spec/code behavior changed in the move.
- **2026-07-21** — Restructured this PRD onto the `~/Downloads/PRD.md` template (hybrid: template spine — Goal / Non-goals / numbered Requirements / Decisions / Open questions / Status — plus retained narrative sections below), so the Stop hook and future edits have numbered requirements and a Status table to reference.
- **2026-07-21** — Phase 2 status corrected from "being wired" to **code-complete but not green**: `approval_tier` stamping (`safety.py:160-164`) and consumption (`handlers.py:344-365,463-467`; `cli.py:1200-1256`) are fully wired and 16 `policy.py` unit tests pass, **but** the AUTO auto-apply behavior change regressed 9 pre-Phase-2 handler/CLI/bulk tests. Landing Phase 2 requires updating those tests (or excluding high-blast tools from AUTO). Changes are uncommitted; no version bump.
- **2026-07-21** — Phase 2 landed green after an adversarial code review, which caught two MAJORs now fixed: (1) `never_auto_tools`/`sensitive_properties` UNION-merge the shipped defaults so a per-portal edit can only ADD, never silently drop the workflow gate; (2) AUTO auto-apply now catches a mid-execute `ExecuteError` and returns a recoverable message naming the pending `action_id` (no invisible staged write / raw traceback); plus the sensitive-field check now also reads `original_values` keys. `SKILL.md` updated to describe the three write outcomes (applied / CONFIRM / FULL_GATE). `docs/PRD.md` added to `check-artifact-allowlist.sh` (it is now tracked, so the CI allowlist gate would otherwise fail on it). Full suite 1143 passed / 1 skipped on Python 3.12.
- **2026-07-22** — Phase 3 PR-B shipped (v0.2.11): back-pressure — `_drive_loop` retries transient read/preview errors (`RateLimitError` / HTTP 5xx / transport faults / retryable handler+execute errors) up to 3 attempts with exponential backoff honoring `Retry-After` (cap 60s), and paces before a step when `X-HubSpot-RateLimit-*` headers show low remaining (parsed in `client.py`, persisted in `LoopState`). Writes are NEVER auto-retried — retry wraps read/preview execution only; the write still pauses at `awaiting_approval`. Injectable `_sleep` keeps tests wait-free. Full suite 1168 passed on Python 3.12.
- **2026-07-22** — Phase 3 PR-A shipped (v0.2.10): cost governance as a **proxy budget** — plan-configurable `max_steps` (50) / `max_api_calls` (1000), surfaced `error_budget`/`verification_plateau`, all enforced **per-step in `_drive_loop`** (`LoopController` + persisted `LoopState` counters); retired the dead `HUBSPOT_LOOP_COST`/`$0.50` ceiling. `api_call_count` is +1/step (approximation — the loop makes no LLM calls). Full suite 1151 passed on Python 3.12.
- **2026-07-22** — **Un-killed pattern-approval mode** (removed from §2 Non-goals; new R14). The roadmap killed it for divergence risk (*"high risk if the rest diverges; never unless replaced with statistical confidence checks"*). Resolved not by inference but by exact per-record **compare-and-set** (apply only if the current value still equals the approved pre-image; drift → skip), plus destructive/sensitive exclusion and an over-threshold typed count. Spec: `docs/superpowers/specs/2026-07-22-pattern-approval-divergence-safe-design.md`.
- **2026-07-22** — Phase 3 (loop hardening) designed: cost governance ships as a **proxy budget** (steps / iterations / API-calls, plan-configurable, enforced per-step in `_drive_loop`), NOT a dollar ceiling — the loop makes no LLM calls and no usage crosses the CLI boundary, so dollars aren't observable inside it (real $ cap deferred to an R12 follow-up needing parent usage injection). Back-pressure (R13) = per-step retry+backoff for transient read/preview errors (writes never auto-retried) + proactive pacing off HubSpot rate-limit headers. Spec: `docs/superpowers/specs/2026-07-22-loop-hardening-cost-backpressure-design.md`. Ships as two PRs.
- **2026-07-22** — Phase 2 §5 hardening (v0.2.9): closed the partial-capture AUTO edge — `classify_write` downgrades an update capturing fewer originals than targeted records to CONFIRM (only a fully-captured, fully-undoable update auto-applies). `auto_apply_max_records` default reaffirmed at 100 (bounded by undo/audit/partial-capture). Full suite 1145 passed on Python 3.12.
- **2026-07-21** — Phase 2 side-effect carve-out (resolves the §5 "Phase 2 landing" question): workflow writes (`create/update/toggle/enroll_workflow`, `create_workflow_from_blueprint`) added to a new config `never_auto_tools` so they ALWAYS keep the human gate (CONFIRM) — "deletable" ≠ "side-effect-free": a workflow enrolls and acts on contacts the moment it exists, and deleting it later doesn't undo that. Benign single- and multi-record (≤threshold) reversible object creates/updates DO auto-apply. The 9 regressed tests were migrated to the new contract (count-gate coverage repointed to a destructive delete; capture-for-undo asserted on the snapshot), not weakened. Full suite green on Python 3.12 (1140 passed, 1 skipped). Still uncommitted; no version bump yet.

- **2026-07-22** — Accepting external contributions. The repo is open-source under a **benevolent-maintainer** model (PromptMetrics / Izzy Aly): added community-health files (`SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`) and a README "Going further" docs index. Product scope stays tracked here (numbered requirements + Status table) and architecture in `docs/adr/`. Resolves the contribution posture of the §5 "Business model" question; commercial vs. community-supported remains open. Docs/meta only — no code change, no version bump.

## 5. Open questions

Unresolved items blocking or shaping the work. Move to §4 once answered.

- [x] **Phase 2 landing** *(resolved 2026-07-21, see §4)* — migrated the 9 regressed tests to the new contract AND added `never_auto_tools` so side-effectful workflow writes always gate; benign object creates/updates auto-apply.
- [ ] **BUG 6 — OAuth scope rejection on fresh portals.** Authorize URL requests 23 `REQUIRED_SCOPES`; a fresh install was rejected. Root cause not confirmed; deferred to live investigation on portal `148895050` (`bug-report...:102`).
- [ ] **BUG 11 — Count-gate regression (0.2.4).** Wrong count reportedly executed anyway; not explicitly resolved in any release summary (`bug-report...:150-160`). *(Note: earlier flagged as a possible stale-venv artifact — confirm live before treating as real.)*
- [ ] **BUG 12 — Bulk-undo rollback path.** After 0.2.5's honest "not undoable" refusal, there's still no live rollback path for bulk updates that lost their snapshot (`bug-report...:162-169`).
- [x] **Phase 2 — partial-capture AUTO** *(resolved 2026-07-22, v0.2.9)* — `classify_write` now downgrades an update with `len(original_values) < impact_count` to CONFIRM, so a partially-undoable bulk update keeps a human checkpoint.
- [x] **Phase 2 — AUTO ceiling risk appetite** *(resolved 2026-07-22)* — kept at 100 (informed choice; bounded by undo, audit, and the partial-capture guard). Per-portal `auto_apply_max_records` stays the tuning knob.
- [ ] **Solo vs. team user.** Drives RBAC, conversation memory, PII redaction, tour mode (`research/2026-05-07...:766`).
- [ ] **Business model.** *(Contribution posture resolved 2026-07-22 — see §4: open-source, accepting external contributions under a benevolent-maintainer model.)* Commercial vs. purely community-supported is still open; affects packaging and support posture.
- [ ] **Token economics / cost ceiling.** No per-session/portal cost ceiling on sub-agent tool use; Phase 3 must define hard-stop vs. warn-and-continue + per-agent attribution (R12).
- [ ] **Market validation.** No pilot data or user interviews exist; PMF unvalidated. Freeze features pending problem interviews?
- [ ] **HubSpot API churn vs. blueprint maintenance.** Unknown API stability rate drives long-term maintenance burden of the 19 blueprints.
- [ ] **16 LOW review findings open** (`review-findings-2026-07-14.md:355-399`): atomic writes, parent-dir fsync, destructive-count re-check vs. stored preview, error-budget gate, corrupt `loop_state` handling, call-path error divergence, API-token redaction, daemon stdout perms, blueprint-parameterize dropped flags, `param_name` grammar, `_walk` cyclic graphs, `validate_blueprint` nested `true_branch`, `SchemaCache._save` bare write, `report_id` quoting, `detect_default_portal` raw string; plus `review-notes.md:266-280` minor residuals.
- [ ] **Release hygiene.** `v0.2.2` is the only genuinely missing git tag; no `CHANGELOG.md` at repo root (release history lives only in `pyproject.toml` / `plugin.json` / `marketplace.json`).

## 6. Status

Current truth of built-vs-promised. Reconcile against code at the end of each session.

| Requirement | State | Notes |
|-------------|-------|-------|
| R1 Deterministic routing → 44 agents | Done | Shipped; routing corpus gate. Full-coverage keyword routing landed 0.2.6 (`da7dead`). |
| R2 HITL preview→approve→execute→undo→audit | Done | Shared `handlers.py` across 3 call paths. |
| R3 Count gate re-checked at execute | Done | `handlers.py`; Phase 2 (R11) re-keys the gate off `approval_tier`, retaining the legacy predicate as a fallback. |
| R4 Scope emission via `scope_registry` | Done | No `.delete` at authorize time. |
| R5 Durable deferred-approval loops | Done | Verbatim tool path (0.2.3); resumable from shared artifacts. |
| R6 Blueprint learning loop | Done | 19 blueprints; extract→parameterize→promote→create (0.2.0/0.2.1). |
| R7 Multi-portal isolation + auto-detect | Done | `~/.claude/hubspot/<portal>/`; `--portal` honored by all HITL handlers (0.2.1). |
| R8 Warm-client daemon | Done | Unix-socket JSON-RPC; schema cache. |
| R9 Quiet/terse mode + HITL carve-out | Done | Shipped 0.2.7 (`23a1616`); previews never suppressed. |
| R10 CI Evaluation Gate | In progress | `.github/workflows/ci.yml` committed on `ci/pr-evaluation-gate` (`f94595a`) + test-isolation fix (`a3180a5`); PR #19 open; **branch protection not yet enabled**. Would go red if Phase 2 lands before its regressed tests are fixed. |
| R11 Bounded Autonomy tiers | Done | Shipped **v0.2.8** (PR #20 merged); §5 partial-capture hardening in **v0.2.9**. `policy.py` `classify_write`/`load_approval_policy`; wired in `safety.py`/`handlers.py`/`cli.py`; `never_auto_tools` workflow gate; union-merged safety lists; recoverable AUTO failures; partial-capture→CONFIRM. Full suite green on Python 3.12 (1145 passed). |
| R12 Loop cost governance (proxy) | Done (v0.2.10) | Proxy budget shipped: plan-configurable `max_steps`/`max_api_calls` + surfaced `error_budget`/`verification_plateau`, enforced per-step in `_drive_loop`; inert `$0.50`/`HUBSPOT_LOOP_COST` hook retired. Real dollar cap still deferred (needs parent usage injection). |
| R13 Back-pressure / retry-backoff | Done (v0.2.11) | Per-step retry+backoff for transient read/preview errors (honors `Retry-After`, cap 60s, budget 3) + proactive pacing off `X-HubSpot-RateLimit-*` (rate state parsed in `client.py`, persisted in `LoopState`, paced between steps); writes never auto-retried. Full suite 1168 passed on 3.12. |
| R14 Pattern approval (divergence-safe) | Done (v0.2.12) | `--pattern`: approve a rule, per-record compare-and-set scale (drift→skip), reversible non-sensitive only, over-threshold typed count, continue-through report; per-record undo + audit. `handlers.py`/`safety.py`/`policy.py` (`pattern_confirm_threshold`). Full suite 1182 passed on 3.12. |

---

## Retained narrative (context, evidence, architecture)

### Problem statement

HubSpot CRM administration is fragmented, time-consuming, and error-prone. A single business
request — "reorganize our deal properties and build a follow-up workflow" — requires navigating
dozens of screens, understanding object schemas, and manually translating business logic into
HubSpot's automation language. There is no persistent, conversational layer that lets an
administrator describe intent and delegate execution **safely**. Because HubSpot exposes **no
dry-run API for most writes**, every bulk operation carries real blast-radius risk with no
preview and no undo in the native UI.

### Evidence

- **Real bugs found in live use.** A demo-rehearsal session on 2026-07-14 against portals `148408595` / `148895050` surfaced 8 bugs (3 P1): a `loop start` crash, fuzzy-payload loop writes landing on the wrong record, a duplicate-finder returning 0 groups (`bug-report-2026-07-14-demo-rehearsal.md`). Two further P1 bugs hit 0.2.3: a bulk-update silent no-op and an undo that "restored" without restoring then destroyed its snapshot. Direct evidence that bulk/loop writes are the high-risk surface.
- **Independent validation confirmed the safety gap.** A six-domain-expert review on 2026-05-10 found 12 Blockers, 22 Warnings, 14 Suggestions (`validation-report.md:12-16`); most blockers were resolved across the 0.2.x arc (PRs #4–#9).
- **Pattern audit (2026-07-21)** against the Encyclopedia of Agentic Coding Patterns found 4 real gaps — Evaluation Gate, Bounded Autonomy, Cost Governance, Back-Pressure/Retry (→ R10–R13) — and confirmed 2 patterns already sound (Action-Selector routing; Progressive Disclosure / no Tool Sprawl).
- **Competitive landscape.** HubSpot Breeze AI / ChatSpot and third-party repos offer conversational CRM admin, but none gate writes behind preview + typed count confirmation + undo + audit.
- **Assumption — needs validation:** no user research, pilot data, or usage telemetry exists. Demand signals are indirect (author's own CRM work + demo-rehearsal dogfooding). PMF is unvalidated.

### Users & context

- **Primary — "Alex", RevOps Manager.** Manages a 50–200-person portal daily; CLI-comfortable; risk-averse. Success: describe intent → preview → approve → done and undoable.
- **Secondary — "Jordan", Technical Founder / Consultant.** Manages 5–20 client portals; lives in the terminal. Success: fast portal switching, schema-aware validation, raw API fallback, reusable blueprints.
- **Tertiary — "Taylor", Sales Ops Lead.** Pipeline hygiene, assignments, reports; relies on previews/confirmations. Success: hygiene loops run safely with human approval at each write.
- **Non-users:** non-technical users wanting a HubSpot UI replacement; teams needing multi-user collaboration or a shared dashboard.

**Job to be done:** *When my CRM data is messy or my team asks for a new automation, I want to
describe what I want in plain English and have a safe, previewable, undoable assistant do it,
so I can stop hand-clicking through HubSpot and stop worrying about a bad bulk write.*

### Solution detail & technical approach

**Feasibility: HIGH** — the product is built, shipping, and tested. Full suite is **1129 passed
/ 1 skipped** with Phase 2 in the tree (9 failing on the uncommitted Phase 2 behavior change);
1121 passed at 0.2.6 on committed history.

**Architecture notes**
- **Orchestrator-Workers + Action-Selector.** Claude parent routes NL → deterministic keyword router → stateless sub-agents → CLI. No custom orchestration framework; native `Agent` tool.
- **Three call paths, one handler set.** Daemon (warm client, Unix-socket JSON-RPC) ↔ in-process fallback ↔ CLI sync, all sharing `handlers.py` so the approve→execute safety contract is identical everywhere.
- **Registries, not hardcoded lists.** Agents in `_AGENT_REGISTRY` (`agents/__init__.py:51`); tools pkgutil-walked at import so the daemon subprocess sees a populated `@tool` registry. A new agent must be registered in `agents/__init__.py` **and** `dispatch.py` tables.
- **Durable loops pause at every write.** `LoopState` persists under `~/.claude/hubspot/<portal>/loop-state.json` (atomic, flock); `_drive_loop` parks at `awaiting_approval`; resume reads only shared artifacts (pending record + audit `approve:<id>` + undo snapshot). Verbatim tool path so writes land on named records, not fuzzy `records[0]`.
- **Blueprint learning loop.** Extract (read-only) → parameterize (local disk) → promote → create (HITL-gated). Pydantic v2 validation; `{{param:name}}` substitution.
- **Bounded Autonomy (Phase 2, in the tree).** `policy.classify_write` first-match order: destructive → `FULL_GATE`; not-undoable → `FULL_GATE`; touches sensitive property → `sensitive_tier`; above `auto_apply_max_records` → `CONFIRM`; else `AUTO`. Config precedence: shipped default → global `approval_policy.json` → per-portal override (shallow last-wins, fail-safe to default). `snapshot.is_undoable` is the single source of truth shared by snapshot-save and classify. `safety.apply_write` stamps `approval_tier`; `handle_tool`/`cli._tool_write` auto-apply `AUTO`; `execute_pending_write` count gate keys off `approval_tier == FULL_GATE`. Loop-originated writes (`loop_step_number` set) are excluded from auto-apply.
- **State on disk.** Per-portal under `~/.claude/hubspot/<portal>/`: config, token, schema cache, pending previews (0600, reaped after 24h), undo snapshots, audit log (redacted NDJSON), loop state, loop log, blueprint learning log, and (Phase 2) `approval_policy.json`.
- **Packaging.** v0.2.7 across three files that must stay in sync: `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`. Python ≥ 3.12; hatchling; wheel packages `src/hubspot_agent` so JSON blueprint data ships inside.

**User flow (critical path)**
1. `/hubspot setup <portal> oauth|token <pat>` once → `SessionStart` hook provisions venv → auth under `~/.claude/hubspot/<portal>/`.
2. `/hubspot reassign all deals owned by Leah to Marcus`.
3. Deterministic router → `objects` + `users` agents → plan → `hubspot_bulk_update_objects` preview (count + per-record diff + undo snapshot fetch).
4. `apply_write` returns a preview with `action_id` and `approval_tier`.
5. `hubspot approve <id> <count>` → count gate re-checks → execute → undo snapshot → audit entry. *(Phase 2: a single-record reversible write classified `AUTO` applies immediately without the count step.)*
6. If wrong: `hubspot undo <id>` replays writable originals (fail-closed).
7. For multi-step goals: `/hubspot --loop '...'` → pauses at each write; approve out-of-band; `loop continue` resumes.

### Success metrics

| Metric | Target | How measured |
|--------|--------|--------------|
| Routing accuracy | ≥ 95% (CI-gated) | `tests/routing_corpus.yaml` + gate in CI |
| Preview latency | p95 < 3s | End-to-end `apply_write` preview timing |
| Blast radius (unapproved writes) | 0 | Audit log; no `approve:<id>` without a human `approve` |
| Client-caused 429s | 0 / 1,000 req | Rate-limit handling + 429 read-retry |
| Schema cache hit | > 80% | Daemon `SchemaCache` counter |
| Plugin load | 100% | `SessionStart` install success |
| Undo availability | 100% of undoable writes | Snapshot presence check at execute time |
| Open security blockers | 0 | HIGHs fixed; LOWs tracked (§5) |
| Time-to-first-write | < 3 min | Setup wizard + first approved write |
| Auto-apply adoption (R11) | TBD once shipped | Share of writes classified `AUTO` proceeding without full count gate |
| Cost-ceiling trips (R12) | TBD once shipped | Loop halts on spend ceiling with per-agent attribution |
| Back-pressure survival (R13) | Bulk loop survives rate limiting unattended | Pacing + backoff retry budget |

### Technical risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Phase 2 does not land clean — AUTO auto-apply regressed 9 pre-Phase-2 tests; `pytest -x` (CI) fails fast | H | Update the 9 handler/CLI/bulk tests to expect `"applied"`, or exclude high-blast tools from AUTO (open question §5) before committing |
| Phase 2 `AUTO` envelope conflicts with 0.2.7 quiet-mode narration suppression | M | Verify `status="applied"` bypass against `output-styles/hubspot-terse.md` + `_base.py` |
| Hidden OAuth scopes for `notes/calls/tasks/emails.*` 403 at call time on OAuth portals | M | Documented; deliberately not requested at authorize time (`scope_registry.py:130-137`) |
| `hubspot_raw_api` write gate relies on HTTP verb classification | L | `RAW_API_WRITE_METHODS` set; a misformed verb could sneak through as read |
| HubSpot creates are not idempotent — loop retry on `create` escalates rather than retries | M | By design; `_artifact_from_snapshot` recovery depends on create response carrying `id` |
| Daemon JSON-RPC socket has no auth (chmod 0600 only) | L | Local single-user; socket dir 0700; unrestrictable socket tears down daemon |
| Cross-process blueprint reload requires daemon restart | L | Documented; file-watcher/IPC refresh out of scope |
| CI dev-interpreter can mask clean-env failures (Phase 1 lesson) | M | `uv venv --python 3.12` verification before push; CI gate (R10) |
| Loop staleness reaper could reap a crashed `running` loop | L | `_drive_loop_guarded` fail-safes to `failed`; `awaiting_*` states staleness-exempt |

### Research summary

**Market context.** Breeze AI / ChatSpot and third-party repos (TomGranot/hubspot-admin-skills,
andrewm621/hubspot-context-pack) offer conversational CRM admin or knowledge injection, but none
combine preview + typed count gate + undo + audit + deterministic routing. TomGranot's skills use
a `SAFETY_THRESHOLD=500` abort gate, hybrid automation labels, A–F audit grading, and per-skill
API gotcha docs — patterns worth adopting. No market sizing or user-research data exists.

**Technical context.** The architecture is built and tested: 3 call paths sharing one HITL handler
set, scope-registry classification, durable deferred-approval loops, the blueprint learning loop,
and the warm-client daemon. ADR-0003 codifies the deterministic-routing security property. The
pattern audit confirmed Progressive Disclosure / no Tool Sprawl (parent sees only the agent index;
sub-agents see only their ~6-tool subset). The four real gaps map directly to R10–R13.

### Implementation phases

| # | Phase | Requirements | Status |
|---|-------|--------------|--------|
| 0 | Action-Selector ADR (deterministic routing as a security property) | R1 | Complete (ADR-0003) |
| 1 | CI Evaluation Gate | R10 | In progress (PR #19; branch protection pending) |
| 2 | Bounded Autonomy (risk-tiered approval) | R11 | In progress (code-complete; 9 tests regressed; uncommitted) |
| 3 | Loop Hardening (cost governance + back-pressure) | R12, R13 | Not started |

Phases are strictly sequential by design: **gate first (Phase 1), then the risky HITL redesign it
protects (Phase 2), then production-only loop hardening (Phase 3).** Phase 0 is complete and
independent. No phases run in parallel.

---

*Status: In progress — reflects v0.2.7 as-built + Phase 1–2 work in the tree; needs live validation
of market/hypothesis metrics (no telemetry pipeline exists yet).*
