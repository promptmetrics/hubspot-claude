# AGENTS.md

This file provides guidance to coding agents (Claude Code, Codex, etc.) when working with code in this repository.

## What This Is

A Claude Code plugin (`/hubspot`, package `hubspot-agent`, currently 0.2.12) for natural-language HubSpot CRM administration. Claude orchestrates ~44 specialist sub-agents that each call the `hubspot` CLI over Bash, with mandatory human-in-the-loop approval for every write. Implementation is complete and actively maintained — this is no longer a greenfield project.

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

**Workflow blueprints.** `blueprints/workflows/` ships JSON blueprint templates plus a learning loop: extract an existing portal workflow → parameterize → promote → create new workflows from it. User blueprints live in `~/.claude/hubspot/blueprints/` and override shipped ones on name collision. See `docs/BLUEPRINTS.md`.

**State on disk.** Per-portal state (config, tokens, schema cache, undo snapshots, audit log, pending previews, loop state) lives under `~/.claude/hubspot/<portal>/`. Portal auto-detection reads a `.hubspot-portal` file in the working directory. Auth is OAuth 2.0 or Private App tokens only — never API keys.

## Plugin Packaging

`.claude-plugin/` holds `plugin.json` + `marketplace.json`; `SKILL.md` is the `/hubspot` skill prompt; `hooks/install.sh` (SessionStart) provisions the plugin venv under `${CLAUDE_PLUGIN_DATA}/venv` and always exits 0 (a failed provision is silent — check `install.log`). `bin/hubspot` self-heals a version-drifted venv on every invocation. When bumping the version, keep `pyproject.toml` and `.claude-plugin/plugin.json` in sync.

## Source of Truth

- `README.md` — user-facing behavior, command table, state layout
- `docs/superpowers/specs/` — design specs (original agent design, blueprint learning loop)
- `docs/adr/` — architectural decision records
- `docs/BLUEPRINTS.md` — blueprint format spec and review checklist
- `CLAUDE.md` — mirror of this guidance; keep the two consistent when editing

## Skills

- Load skill from `~/.claude/skills/autolog`
