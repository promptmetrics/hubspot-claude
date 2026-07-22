# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Claude Code plugin (`/hubspot`, package `hubspot-agent`, currently 0.2.13) for natural-language HubSpot CRM administration. Claude orchestrates ~44 specialist sub-agents that each call the `hubspot` CLI over Bash, with mandatory human-in-the-loop approval for every write. Implementation is complete and actively maintained — this is no longer a greenfield project.

## Commands

```bash
pip install -e ".[dev]"                  # editable install with test deps
pytest -x                                # full suite (~960+ passed, 3 skipped)
pytest tests/test_cli_hitl.py -v         # one module
pytest tests/test_safety.py::test_name   # one test
claude plugin validate ./                # schema-check plugin.json + marketplace.json + hooks
bash scripts/check-artifact-allowlist.sh # shipping-artifact allowlist gate (run before release)
claude --plugin-dir ./                   # load the plugin locally for a session
```

Tests use `pytest-asyncio`, `respx`/`pytest-httpx` (no live HubSpot calls), and `hypothesis` (`tests/property_based/`). `tests/conftest.py` isolates `Path.home()` so tests never touch real `~/.claude/hubspot/` state.

## Architecture

**Claude is the orchestrator; the CLI is the source of truth.** There is no custom orchestration framework — Claude Code's native `Agent` tool spawns stateless sub-agents whose prompts come from `hubspot agent-prompt <name>`. Sub-agents call `${CLAUDE_PLUGIN_ROOT}/bin/hubspot tool <name> --input '<json>' --portal <id> --working-dir <dir>`. `--portal`/`--working-dir` are top-level flags and must precede `--input`.

**Three call paths, one handler set.** `bin/hubspot` (POSIX sh venv resolver) → `router.py`, which prefers the warm-client daemon (`daemon.py`, Unix-socket JSON-RPC reusing one `HubSpotClient` + schema cache), falls back to in-process execution, and `cli.py` also runs sync. All three share `handlers.py`, so the approve→execute safety contract (destructive-count gate, undo snapshot, created-id capture, audit entry, clear-pending) is identical everywhere. When changing write behavior, change `handlers.py`/`safety.py` — never one path.

**HITL write flow.** HubSpot has no dry-run API, so `safety.py:apply_write` builds a read-based preview, persists it with an `action_id` (`persistence.py`, flock + atomic writes), and returns without mutating. `hubspot approve <id> [count]` executes; destructive ops require the expected record count, re-checked at execute time. Every approved write records an undo snapshot (`snapshot.py`) and audit entry (`audit.py`). `scope_registry.py` classifies operations and emits required scopes (including `.delete`) — do not classify writes by tool-name heuristics. The `WRITE_TOOLS` set and `apply_write`'s `proposed_payload` are load-bearing; sub-agents are stateless, so the parent embeds `proposed_payload` in the re-dispatch prompt. Writes are risk-tiered (`policy.py:classify_write` → AUTO / CONFIRM / FULL_GATE: provably-safe reversible writes auto-apply; destructive, bulk, non-undoable, or sensitive-property writes keep the gate). `--pattern` approves one transformation rule and scales it via per-record compare-and-set (drift → skip); `pattern_confirm_threshold` requires the typed count on oversized matched sets.

**Registries, not hardcoded lists.** Agents live in `src/hubspot_agent/agents/` (`_AGENT_REGISTRY` in `agents/__init__.py`); tools in `src/hubspot_agent/tools/` (`tools/__init__.py` pkgutil-walks its submodules so the daemon subprocess sees a populated `@tool` registry — don't break this). A new agent must be registered in `agents/__init__.py` **and** the dispatch tables in `dispatch.py` (`_EXECUTE_DISPATCH`, `_RECONCILE_DISPATCH`). Never hardcode agent/tool counts in docs or prompts — derive them from `hubspot agents list` / `tools list`.

**Durable loops (deferred approval).** `/hubspot --loop '<goal>'` runs a Claude-planned, deferred-approval loop: **Claude produces the `LoopPlan` and the `VerificationResult`s** (no Python triage — the old `spawn_agent`/`claude_code` seam is retired) and feeds them to the deterministic executor via `hubspot loop start --plan` / `loop verify --result`. `orchestrator.run_loop` + `_drive_loop` execute read steps inline and **pause at every write** (`status="awaiting_approval"`, `pending_action_id` on `LoopState`); the write is applied out-of-band by the unchanged `hubspot approve` path, `loop continue` captures the artifact (resume disambiguates via the pending record + audit `approve:<id>` + undo snapshot), and `loop_controller.py` decides proceed/retry/escalate on each verdict. Resumable state in `loop_state.py` (paused states are staleness-exempt), NDJSON event log in `loop_log.py`.

**Scheduled tasks (R15).** `hubspot schedule add|list|remove|run-due|install-timer` registers a recurring job — a concrete (verbatim-tool) `LoopPlan` plus a cron expression, stored per-portal in `schedule_store.py` (`~/.claude/hubspot/<portal>/schedules/`, flock + atomic like `persistence.py`). An external OS timer invokes `run-due`; there is no daemon. `run_scheduled_due`/`_run_one_schedule` (in `orchestrator.py`) drive each due schedule through `_drive_loop` in **`run_mode="scheduled"`** (a new `LoopState` mode with its own `state_key` → `schedules/runs/<id>.json`, never the interactive `loop-state.json`): reads run inline, every write is **staged** as a pending preview and the loop continues (stage-and-continue) instead of pausing — **nothing mutates unattended**. Free-text (non-`tool_name`) steps are refused (they could mutate via the agent-execute branch). The operator approves the queued batch later via the normal `approve` path (compare-and-set re-checks each record at approval). The overlap gate re-derives "pending" from whether staged previews still exist on disk (so a resolved batch un-freezes the schedule); unreviewed batches expire after `schedule_queue_ttl_days` (default 7) and staged previews are exempt from the 24h reaper. In-house 5-field cron evaluator in `cron.py`.

**Workflow blueprints.** `blueprints/workflows/` ships JSON blueprint templates plus a learning loop: extract an existing portal workflow → parameterize → promote → create new workflows from it. User blueprints live in `~/.claude/hubspot/blueprints/` and override shipped ones on name collision. See `docs/BLUEPRINTS.md`.

**State on disk.** Per-portal state (config, tokens, schema cache, undo snapshots, audit log, pending previews, loop state) lives under `~/.claude/hubspot/<portal>/`. Portal auto-detection reads a `.hubspot-portal` file in the working directory. Auth is OAuth 2.0 or Private App tokens only — never API keys.

## Plugin Packaging

`.claude-plugin/` holds `plugin.json` + `marketplace.json`; `SKILL.md` is the `/hubspot` skill prompt; `hooks/install.sh` (SessionStart) provisions the plugin venv under `${CLAUDE_PLUGIN_DATA}/venv` and always exits 0 (a failed provision is silent — check `install.log`). `bin/hubspot` self-heals a version-drifted venv on every invocation. When bumping the version, keep `pyproject.toml` and `.claude-plugin/plugin.json` in sync.

## Product spec (source of truth)

The product spec lives in `docs/PRD.md`. Read it at the start of any implementation work.

Keep it current as part of the job — not as a separate task:

- When you make a non-trivial decision, append a dated line to the Decisions log.
- When scope changes, edit the affected numbered requirement in place (don't just append a note).
- When a requirement's behavior changes, update its acceptance criteria.
- At the end of a work session, reconcile Status against what the code actually does.

If a change genuinely doesn't affect the spec, say so explicitly rather than skipping silently. Reference requirements by number (e.g. "R4") in commits and explanations.

Run `/sync-prd` to reconcile the PRD against recent commits and current code.

## Source of Truth

- `docs/PRD.md` — product spec (source of truth); see "Product spec" above
- `README.md` — user-facing behavior, command table, state layout
- `docs/superpowers/specs/` — design specs (original agent design, blueprint learning loop)
- `docs/adr/` — architectural decision records
- `docs/BLUEPRINTS.md` — blueprint format spec and review checklist
- `AGENTS.md` — mirror of this guidance; keep the two consistent when editing

## Skills

- Load skill from `~/.claude/skills/autolog`
