# HubSpot Plugin

A Claude Code plugin (`/hubspot`) for natural-language administration of HubSpot CRM. Claude orchestrates specialist sub-agents that each call the `hubspot` CLI over Bash to perform CRUD across contacts, companies, deals, workflows, lists, pipelines, properties, analytics, engagements, associations, and more — with mandatory human-in-the-loop approval for every write.

This is a **local-execution** plugin: a `SessionStart` hook provisions an isolated Python venv on your machine and the CLI runs against your local filesystem (portal tokens, `.hubspot-portal`, undo snapshots, audit log). It is designed for Claude Code (CLI, desktop, IDE) — see [Notes & Limitations](#notes--limitations) for why it is not a fit for Claude Cowork.

> **Important**: Every write is gated behind a preview + explicit `approve`. Destructive operations require the expected record count, re-checked at execute time. The plugin authenticates with OAuth 2.0 or Private App tokens only — never API keys. HubSpot credentials are stored locally under `~/.claude/hubspot/`; review your org's secret-handling policy before use.

The agent and tool catalogs live in code. As of this release the registry holds **44 specialist sub-agents** and **79 tools**; discover the current set with `hubspot agents list` and `hubspot tools list` rather than trusting this number.

## Features

- **Natural-language CRM admin** — route a request to one or more specialist sub-agents, each scoped to a HubSpot domain (contacts, deals, workflows, lists, pipelines, properties, analytics, engagements, associations, audit, hygiene, …).
- **Human-in-the-loop writes** — writes return a preview + `action_id`, never a mutation; nothing happens until you `approve` (with a mandatory count for destructive ops).
- **Warm-client daemon** — reads and write-previews reuse one `HubSpotClient` + schema cache for speed; everything else runs in-process with identical results.
- **Durable loops** — `/hubspot --loop '<goal>'` runs triage → sequential step execution → verify → checkpoint, resumable across sessions.
- **Undo + audit** — every approved create/update/delete records an undo snapshot and an audit entry (FR-17/FR-18).
- **Multi-portal** — isolated state per portal; auto-detection via a `.hubspot-portal` file in the working directory.
- **Workflow blueprints + learning loop** — 19 JSON blueprint templates ship with the plugin; extract an existing portal workflow into a reviewable blueprint, parameterize it, promote it, and create new workflows from it. All workflow writes now gate behind preview + approval. See [docs/BLUEPRINTS.md](docs/BLUEPRINTS.md).

## Prerequisites

- **Claude Code** installed and logged in.
- **Python ≥ 3.12** on `PATH` (`python3 --version`). The hook builds the venv from this interpreter; older versions fail to install the package.
- `uv` is optional but recommended — the provisioning hook prefers it and falls back to `python3 -m venv` + `pip`.
- A HubSpot portal with either a **Private App token** or an **OAuth 2.0** app.

## Installation

### From the marketplace (recommended)

In Claude Code:

```
/plugin marketplace add promptmetrics/hubspot-claude
/plugin install hubspot@hubspot-claude
```

Or via the CLI:

```bash
claude plugin marketplace add promptmetrics/hubspot-claude
claude plugin install hubspot@hubspot-claude
```

On the first session after install, the `SessionStart` hook (`hooks/install.sh`) provisions an isolated venv under `${CLAUDE_PLUGIN_DATA}/venv` (preferring `uv`, else `python3 -m venv` + `pip install`), writes `venv.path` so the `bin/hubspot` resolver can find it, and records a hash of `pyproject.toml` so it only rebuilds when the manifest changes. The hook never blocks the session and does **not** start the daemon.

### Local development

```bash
git clone https://github.com/promptmetrics/hubspot-claude.git
cd hubspot-claude
pip install -e ".[dev]"          # editable install with test deps
claude plugin validate ./        # schema-check plugin.json + marketplace.json + hooks
claude --plugin-dir ./           # load the plugin for this session
```

Then invoke `/hubspot` in that session. If the plugin is also installed from the marketplace, uninstall it first so the two copies don't collide.

## Commands

The plugin ships a single entrypoint at `${CLAUDE_PLUGIN_ROOT}/bin/hubspot` (a POSIX sh resolver that finds the plugin venv python and runs the daemon router). Sub-agents always pass `--portal` and `--working-dir` so they hit the same portal as the originating request.

| Command | Purpose |
|---------|---------|
| `/hubspot <request>` | Natural-language request routed to specialist sub-agents |
| `/hubspot --loop '<goal>'` | Durable closed loop (triage → execute → verify → checkpoint) |
| `/hubspot --pattern '<sample>'` | Sample-verify-scale batch approval |
| `hubspot status` | Portal, agent readiness, pending approvals |
| `hubspot route '<request>'` | JSON `{agents, rationale}` showing which agents a request maps to |
| `hubspot tool <name> --input '<json>'` | Read → JSON result; write → preview + `action_id` |
| `hubspot agents list` / `tools list` | Enumerate the registry (single source of truth for counts) |
| `hubspot agent-prompt <name>` | Full prompt for one specialist agent |
| `hubspot approve <id> [<count>]` | Execute a previewed write (count required + re-checked for destructive) |
| `hubspot reject <id>` | Discard a pending write |
| `hubspot loop status\|log\|continue\|abandon` | Inspect or steer a running loop |
| `hubspot serve` / `serve stop` | Warm-client daemon lifecycle |
| `hubspot portal auth\|token\|list\|switch` | Portal + auth management |
| `hubspot setup <id> oauth\|token <pat>` | Full portal setup |
| `hubspot refresh` | Refresh the schema cache |

`--portal` and `--working-dir` are top-level flags and must precede any JSON `--input` value.

### Date / datetime filters (epoch-milliseconds)

HubSpot stores date and datetime property values (`createdate`, `closedate`,
`hs_lastmodifieddate`, `lastmodifieddate`, etc.) as **epoch-milliseconds**.
When a search filter targets a date/datetime property, the comparison `value`
must be epoch-milliseconds — not an ISO-8601 string and not seconds-epoch. An
ISO string or seconds value mis-compares and silently returns wrong or empty
results. The agent charters carry this caveat; if you build filters by hand
(via `hubspot tool hubspot_search_objects --input '{...}'`), convert the date
to epoch-ms (milliseconds since 1970-01-01 UTC) before sending.

## Skills (specialist agents)

The 44 specialist sub-agents live in `src/hubspot_agent/agents/` and are surfaced by the registry. Discover them at runtime rather than hardcoding:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/hubspot" agents list        # 44 agents (from the registry)
"${CLAUDE_PLUGIN_ROOT}/bin/hubspot" agent-prompt <name>  # full prompt for one agent
```

Categories include Core CRM (contacts, companies, deals, associations), Analytics & Data, Content & Projects, System & Audit, Hygiene, and more. If you need to state a count in prose, run `agents list` first and count the entries — the registry is the single source of truth.

## Example workflows

### Find and merge duplicate contacts

1. `/hubspot find duplicate contacts and merge them`
2. Claude routes to the `hygiene` agent, which calls `hubspot tool hubspot_find_duplicates --input '{...}'` (a read → JSON result).
3. Claude presents a **preview + `action_id`** (the merge does not happen yet).
4. `/hubspot approve <action_id> 3` — you confirm with the expected count (mandatory for destructive ops).
5. `/hubspot tool hubspot_get_contact --input '{...}'` — verify the merge landed.

### Create a deal

1. `/hubspot create a deal for Acme Corp worth $50,000`
2. Claude presents a preview + `action_id`.
3. `/hubspot approve <action_id>` — executes; an undo snapshot + audit entry are written.

### Reconcile stale deals in a loop

1. `/hubspot --loop 'reconcile stale deals older than 90 days'`
2. Inspect progress: `/hubspot loop status` and `/hubspot loop log`.
3. Resume after an interruption: `/hubspot loop continue`. Stop early: `/hubspot loop abandon`.

## Workflow blueprints

The plugin ships 19 JSON workflow blueprint templates and a **learning loop** that turns an existing portal workflow into a reusable blueprint: extract → parameterize → promote → create.

```bash
hubspot tool hubspot_extract_workflow_blueprint       --input '{"workflow_id":"777","name":"My Workflow"}'
# review the returned flags, then parameterize portal-specific values:
hubspot tool hubspot_parameterize_blueprint_draft     --input '{"name":"My Workflow","edits":[{"path":"spec.actions[0].fields.content_id","param_name":"email_content_id"}]}'
hubspot tool hubspot_promote_blueprint_draft          --input '{"name":"My Workflow"}'
hubspot tool hubspot_create_workflow_from_blueprint    --input '{"blueprint_name":"My Workflow","params":{"email_content_id":"123"}}'
```

All five workflow write tools (create/update/enroll/toggle/create_from_blueprint) gate behind a preview + `approve`. Extraction is read-only (no gate); parameterize and promote touch local disk only. See [docs/BLUEPRINTS.md](docs/BLUEPRINTS.md) for the format spec, the draft review checklist, and on-disk layout.

## How it works

```
User (Claude Code session)
    │  /hubspot "find duplicate contacts and merge them"
    ▼
Claude orchestrates  ── route ──▶ {"agents": ["hygiene"], ...}
    │
    ├── spawn sub-agent(hygiene)  ──▶  hubspot tool hubspot_find_duplicates --input '{...}'
    │                                   ▼  read → JSON result
    ├── present preview + action_id      (write returns a preview, NOT a mutation)
    ├── hubspot approve <action_id> <count>   ← user confirms (count mandatory for destructive)
    └── hubspot tool hubspot_get_contact --input '{...}'   ← verify the change landed
```

- **Claude is the orchestrator** — it routes, spawns sub-agents with `hubspot agent-prompt <name>`, and approves writes. No custom orchestration framework; Claude Code's native `Agent` tool does the spawning.
- **The CLI is the single source of truth** — every sub-agent calls `${CLAUDE_PLUGIN_ROOT}/bin/hubspot tool <name> --input '<json>' --portal <id> --working-dir <dir>`.
- **Warm-client daemon** — read and write-preview tool calls route through one reused `HubSpotClient` + schema cache for speed; `approve`/`reject`/`loop *`/`route`/`agents` run in-process. The daemon is lazy-started on the first tool call, self-exits after idle, and `bin/hubspot` falls back to the in-process CLI if it's ever unreachable (same correct result, only slower).
- **Three call paths, one handler set** — daemon (warm), in-process fallback (fresh client), and CLI sync all share `src/hubspot_agent/handlers.py`, so the approve→execute safety contract (destructive-count gate, undo snapshot, created-id capture, audit, clear-pending) is identical everywhere.
- **Read-based previews** — HubSpot has no dry-run API, so writes preview the affected records and return an `action_id`; nothing mutates until `approve`.

## Configuration

### Authentication

**Private App token (simplest for personal use):**

```
/hubspot setup <portal_id> token <pat-na1-...>
```

**OAuth 2.0 (for team setups):**

```
/hubspot setup <portal_id> oauth
```

Auth is OAuth 2.0 or Private App tokens only — never API keys. Portal auto-detection reads a `.hubspot-portal` file in the working directory; multi-portal setups keep isolated state per portal.

**Verify everything is wired:**

```
/hubspot status
```

### Where state lives

| Path | Contents |
|------|----------|
| `${CLAUDE_PLUGIN_DATA}/venv` | Provisioned plugin venv (written by the SessionStart hook) |
| `${CLAUDE_PLUGIN_DATA}/install.log` | Venv provisioning log (check this if the CLI won't load) |
| `~/.claude/hubspot/<portal>/` | Portal config, schema cache, undo snapshots, audit log, pending previews, loop state |
| `~/.claude/hubspot/blueprints/` | Promoted user workflow blueprints (override shipped on name collision) |
| `~/.claude/hubspot/blueprints/drafts/` | Extracted blueprint drafts awaiting review |
| `~/.claude/hubspot/<portal>/blueprint_learning.jsonl` | Per-portal unknown-action log (delete to clear) |

## Project structure

```
src/hubspot_agent/
├── cli.py                # /hubspot entry point, sub-commands, HITL approve/reject
├── orchestrator.py       # routing, dispatch, durable loop
├── router.py             # bin/hubspot daemon router + in-process fallback
├── daemon.py             # warm-client Unix-socket JSON-RPC server
├── handlers.py           # shared tool/approve/loop handlers (daemon + CLI)
├── safety.py             # apply_write: scope validation + preview + HITL persist
├── client.py             # async httpx client with rate limiting
├── persistence.py        # preview / action-id storage (flock + atomic)
├── loop_state.py / loop_log.py  # durable loop state + NDJSON event log
├── agents/               # specialist sub-agents (registry: 44)
├── tools/                # tool modules (registry: 75)
└── blueprints/workflows/ # JSON workflow blueprints + extract/parameterize/promote learning loop
bin/hubspot               # plugin entrypoint (venv resolver → router)
hooks/                    # SessionStart venv provisioning
.claude-plugin/           # plugin.json + marketplace.json
tests/                    # pytest suite
```

## Development

```bash
pip install -e ".[dev]"                      # test deps (pytest, pytest-asyncio, respx, hypothesis, pyyaml)
pytest -x                                    # full suite (962 passed, 3 skipped)
pytest tests/test_install_hook.py -v         # SessionStart venv contract
bash scripts/check-artifact-allowlist.sh     # shipping-artifact allowlist gate
claude plugin validate ./                    # schema-check manifests + hooks
```

## Key design decisions

1. **Claude orchestrates; the CLI is the source of truth** — sub-agents are stateless and call `hubspot tool` over Bash; proposed payloads are embedded in their prompts.
2. **Read-based previews** — HubSpot has no dry-run, so writes preview the affected records and return an `action_id`; nothing mutates until `approve`.
3. **Count-based confirmation** — destructive operations require the expected count, re-checked at execute time.
4. **One warm client** — the daemon reuses a single `HubSpotClient` + schema cache; every other path runs in-process with identical results.
5. **Three call paths, one handler set** — daemon (warm), in-process fallback (fresh client), and CLI sync all share `handlers.py`.

## Notes & Limitations

- **Not for Claude Cowork.** Cowork runs in a cloud Linux sandbox, not on your local machine, and currently ignores `SessionStart` hooks ([anthropics/claude-code#40495](https://github.com/anthropics/claude-code/issues/40495), [#47993](https://github.com/anthropics/claude-code/issues/47993)). The plugin's venv-provisioning hook, local-CLI exec, local token storage, and warm-client daemon all assume local execution. The `hubspot` skill would register in Cowork but no action would run. Bringing HubSpot into Cowork would mean repackaging it as an MCP connector — a separate project.
- **Python ≥ 3.12 required.** The venv is built from the `python3` on `PATH`; older interpreters fail the `requires-python>=3.12` constraint and `bin/hubspot` falls back to a system python that can't import the package (exit 127).
- **Venv provisioning is silent on failure.** The hook always `exit 0` so it never blocks the session — a failed provision looks fine until `/hubspot` returns a router import error. After a fresh install, check `${CLAUDE_PLUGIN_DATA}/install.log` and `venv.path`.
- **Stale venv after a `/plugin update` or editing `pyproject.toml`** — `bin/hubspot` self-heals on every invocation: it compares the venv's installed `hubspot-agent` version against the bundled `pyproject.toml` and reinstalls on drift, so a within-session update takes effect without a restart. The SessionStart hash-gate still handles the full rebuild on the next session start. To force an immediate full rebuild, delete `${CLAUDE_PLUGIN_DATA}/.pyproject.sha` (or `rm -rf "${CLAUDE_PLUGIN_DATA}/venv"`) and restart.
- **Secrets are stored locally** — portal tokens live under `~/.claude/hubspot/`. Ensure that directory is appropriately protected and excluded from backups/sync as your policy requires.

## Questions or Issues?

Open an issue at [github.com/promptmetrics/hubspot-claude/issues](https://github.com/promptmetrics/hubspot-claude/issues).

## License

MIT — see [LICENSE](LICENSE).