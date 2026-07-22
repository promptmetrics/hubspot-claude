<div align="center">

# HubSpot Agent

**Run your HubSpot CRM from the Claude Code prompt — every write previewed and approved before it touches your portal.**

[![CI](https://github.com/promptmetrics/hubspot-claude/actions/workflows/ci.yml/badge.svg)](https://github.com/promptmetrics/hubspot-claude/actions/workflows/ci.yml)
[![Version](https://img.shields.io/github/v/tag/promptmetrics/hubspot-claude?label=version)](https://github.com/promptmetrics/hubspot-claude/tags)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

<!-- DEMO: record per the recipe in readme-analysis-2026-07-22.md and drop the file at docs/media/demo.gif, then uncomment:
![demo: find duplicate contacts → preview → approve](docs/media/demo.gif)
-->

> **Every write is gated.** A write returns a read-based preview and an `action_id` — it never mutates. Nothing happens until you `approve`. Destructive operations require the expected record count, re-checked at execute time. Auth is OAuth 2.0 or Private App tokens only — never API keys. Credentials stay local under `~/.claude/hubspot/`.

## What it does

Describe what you want done to your HubSpot portal in plain English; a coding agent routes the request to a specialist, builds a preview from live data, and waits for your approval before writing. The business outcome: finish in **under 60 seconds** what takes ~5 minutes of hand-clicking in the HubSpot UI, with **zero unapproved writes**.

It runs as a Claude Code plugin (`/hubspot`). Claude orchestrates ~44 stateless specialist sub-agents that each call the `hubspot` CLI over Bash — one deterministic router, one shared safety contract, one source of truth. HubSpot exposes no dry-run API, so this is the preview-and-undo layer the native UI doesn't give you.

## What you do with it

- **Clean up the CRM without leaving the prompt** — dedupe contacts, fix properties, reassign owners, reconcile stale deals in plain English instead of clicking through screens.
- **Never fear a bad bulk write** — every change previews first and needs your approval; destructive ops require the exact record count. Any approved create/update is undoable (deletes and merges are flagged non-undoable *at preview time*, honestly).
- **Run multi-step cleanups as a durable loop** — `/hubspot --loop '<goal>'` executes reads inline and pauses at every write for approval; resumable across sessions.
- **Work across every portal you manage** — state is isolated per portal and auto-detected from a `.hubspot-portal` file. No cross-portal accidents.
- **Turn one portal workflow into a reusable template** — extract an existing workflow into a reviewable JSON blueprint, parameterize it, and create new workflows from it.
- **Let trivial writes flow, gate the risky ones** — risk-tiered approval auto-applies provably-safe, reversible writes (up to a configurable record ceiling) while still gating destructive, over-ceiling, non-undoable, sensitive-field, and side-effectful workflow writes.

The exact agent, tool, and blueprint counts live in code — run `hubspot agents list` / `hubspot tools list` rather than trusting a number in prose.

## See it

```
/hubspot find duplicate contacts and merge them
```

Claude routes to the `hygiene` agent, which runs a read-only scan and hands back a **preview with an `action_id`** — nothing has changed yet. You confirm with the expected count (mandatory for destructive ops):

```
/hubspot approve <action_id> 3
```

The merge executes, an undo snapshot and audit entry are written, and a follow-up read verifies it landed. Get the count wrong and the write is refused at execute time.

## Why this over the alternatives

The HubSpot UI turns bulk cleanup into a clicking marathon, and raw API scripts have no safety net — one mistyped filter can rewrite thousands of records with no preview and no undo. Comparable Claude tools ship as static `SKILL.md` script-packs; this is a dynamic multi-agent orchestration layer with a hard human-in-the-loop gate on every write, undo snapshots, and an audit trail. You get conversational speed with a mistyped filter caught before it fires, not after.

## Status

Requirement IDs (R1–R13) map to `docs/PRD.md`, the source of truth. Don't plan around 🚧/💭 rows — they aren't done.

| ✅ Shipping | 🚧 In progress | 💭 Planned |
|-------------|----------------|-----------|
| HITL preview → approve → execute → undo → audit on every write (R2) | — | Real-dollar loop cost ceiling (needs parent-usage injection; today's budget is a proxy) |
| CI evaluation gate — `pytest` + `plugin validate` + artifact allowlist, enforced on every PR via branch protection (R10) | | Model tiering (no plugin-side seam today) |
| Deterministic keyword routing to ~44 specialist agents (R1) | | |
| Count gate re-checked at execute time (R3) | | |
| Risk-tiered approval — AUTO / CONFIRM / FULL_GATE (R11) | | |
| Durable deferred-approval loops, resumable (R5) | | |
| Loop cost governance via proxy budget — step/API-call ceilings (R12) | | |
| Back-pressure — retry+backoff + rate-limit pacing; writes never auto-retried (R13) | | |
| Workflow blueprint learning loop (R6) | | |
| Warm-client daemon + schema cache (R8) | | |
| Multi-portal isolation + auto-detect (R7) | | |
| Quiet/terse output with a hardened HITL carve-out (R9) | | |

## Quick start

**Prerequisites:** Python ≥ 3.12 on `PATH`, Claude Code installed and logged in, and a HubSpot portal with either a Private App token or an OAuth 2.0 app. `uv` is optional but preferred by the provisioning hook.

**Install (from the marketplace):**

```
/plugin marketplace add promptmetrics/hubspot-claude
/plugin install hubspot@hubspot-claude
```

On the first session, a `SessionStart` hook provisions an isolated venv under `${CLAUDE_PLUGIN_DATA}/venv` (preferring `uv`, else `python3 -m venv` + `pip`). It never blocks the session — if the CLI won't load, check `${CLAUDE_PLUGIN_DATA}/install.log`.

**Authenticate** (Private App token is fastest — create one under **Settings → Integrations → Private Apps**, grant the CRM + automation scopes, then):

```
/hubspot setup <portal_id> token pat-na1-...
```

For team setups requiring refreshable tokens, use `/hubspot setup <portal_id> oauth`. Then verify:

```
/hubspot status
```

**First read (no approval needed):**

```
/hubspot find contacts
```

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

> **Date/datetime filters use epoch-milliseconds.** HubSpot stores `createdate`, `closedate`, `hs_lastmodifieddate`, etc. as epoch-ms. A search filter on a date property must send epoch-ms — an ISO string or seconds value silently mis-compares and returns wrong or empty results. The agent charters carry this caveat; convert before sending if you build filters by hand.

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
- **Routing is deterministic, by design** — a keyword Action-Selector scores requests against a fixed agent allowlist; CRM content never re-enters agent selection, which closes prompt-injection-via-CRM-data by construction (see ADR-0003).
- **Three call paths, one handler set** — daemon (warm client), in-process fallback (fresh client), and CLI sync all share `handlers.py`, so the approve→execute safety contract (count gate, undo snapshot, created-id capture, audit, clear-pending) is identical everywhere.
- **Read-based previews** — HubSpot has no dry-run API, so writes preview the affected records and return an `action_id`; nothing mutates until `approve`.

<details>
<summary><b>Configuration &amp; authentication</b></summary>

**Private App token (simplest for personal use):**

```
/hubspot setup <portal_id> token <pat-na1-...>
```

**OAuth 2.0 (for team setups):**

```
/hubspot setup <portal_id> oauth
```

Auth is OAuth 2.0 or Private App tokens only — never API keys. Portal auto-detection reads a `.hubspot-portal` file in the working directory; multi-portal setups keep isolated state per portal. Verify with `/hubspot status`.

**Where state lives:**

| Path | Contents |
|------|----------|
| `${CLAUDE_PLUGIN_DATA}/venv` | Provisioned plugin venv (written by the SessionStart hook) |
| `${CLAUDE_PLUGIN_DATA}/install.log` | Venv provisioning log (check this if the CLI won't load) |
| `~/.claude/hubspot/<portal>/` | Portal config, schema cache, undo snapshots, audit log, pending previews, loop state, `approval_policy.json` |
| `~/.claude/hubspot/blueprints/` | Promoted user workflow blueprints (override shipped on name collision) |
| `~/.claude/hubspot/blueprints/drafts/` | Extracted blueprint drafts awaiting review |
| `~/.claude/hubspot/<portal>/blueprint_learning.jsonl` | Per-portal unknown-action log (delete to clear) |

</details>

<details>
<summary><b>Workflow blueprints</b></summary>

The plugin ships JSON workflow blueprint templates and a **learning loop** that turns an existing portal workflow into a reusable blueprint: extract → parameterize → promote → create.

```bash
hubspot tool hubspot_extract_workflow_blueprint    --input '{"workflow_id":"777","name":"My Workflow"}'
# review the returned flags, then parameterize portal-specific values:
hubspot tool hubspot_parameterize_blueprint_draft  --input '{"name":"My Workflow","edits":[{"path":"spec.actions[0].fields.content_id","param_name":"email_content_id"}]}'
hubspot tool hubspot_promote_blueprint_draft        --input '{"name":"My Workflow"}'
hubspot tool hubspot_create_workflow_from_blueprint --input '{"blueprint_name":"My Workflow","params":{"email_content_id":"123"}}'
```

All workflow write tools (create/update/enroll/toggle/create_from_blueprint) gate behind a preview + `approve` — a workflow acts on contacts the moment it exists, so these always keep the human gate even under risk-tiered approval. Extraction is read-only; parameterize and promote touch local disk only. See [docs/BLUEPRINTS.md](docs/BLUEPRINTS.md) for the format spec and review checklist.

</details>

<details>
<summary><b>Project structure, development &amp; design decisions</b></summary>

```
src/hubspot_agent/
├── cli.py                # /hubspot entry point, sub-commands, HITL approve/reject
├── orchestrator.py       # routing, dispatch, durable loop
├── router.py             # bin/hubspot daemon router + in-process fallback
├── daemon.py             # warm-client Unix-socket JSON-RPC server
├── handlers.py           # shared tool/approve/loop handlers (daemon + CLI)
├── safety.py             # apply_write: scope validation + preview + HITL persist
├── policy.py             # risk-tiered approval (classify_write / load_approval_policy)
├── client.py             # async httpx client with rate limiting
├── persistence.py        # preview / action-id storage (flock + atomic)
├── loop_state.py / loop_log.py  # durable loop state + NDJSON event log
├── agents/               # specialist sub-agents (registry)
├── tools/                # tool modules (registry)
└── blueprints/workflows/ # JSON workflow blueprints + extract/parameterize/promote loop
bin/hubspot               # plugin entrypoint (venv resolver → router)
hooks/                    # SessionStart venv provisioning
.claude-plugin/           # plugin.json + marketplace.json
tests/                    # pytest suite
```

**Development:**

```bash
pip install -e ".[dev]"                      # test deps (pytest, pytest-asyncio, respx, hypothesis, pyyaml)
pytest -x                                    # full suite
bash scripts/check-artifact-allowlist.sh     # shipping-artifact allowlist gate
claude plugin validate ./                    # schema-check manifests + hooks
claude --plugin-dir ./                       # load the plugin for this session
```

**Key design decisions:**
1. **Claude orchestrates; the CLI is the source of truth** — sub-agents are stateless and call `hubspot tool` over Bash; proposed payloads are embedded in their prompts.
2. **Deterministic routing as a security property** — the model is never the router; CRM content can't hijack agent selection (ADR-0003).
3. **Read-based previews** — HubSpot has no dry-run, so writes preview the affected records and return an `action_id`; nothing mutates until `approve`.
4. **Count-based confirmation** — destructive operations require the expected count, re-checked at execute time.
5. **Risk-tiered approval** — provably-safe reversible writes (within a record ceiling) auto-apply; destructive, over-ceiling, non-undoable, sensitive-field, and side-effectful workflow writes keep the human gate.
6. **Three call paths, one handler set** — daemon, in-process fallback, and CLI sync all share `handlers.py`.

</details>

## Notes &amp; limitations

- **Not for Claude Cowork.** Cowork runs in a cloud Linux sandbox, ignores `SessionStart` hooks, and breaks the local-execution assumptions (venv provisioning, local CLI exec, local token storage, warm-client daemon). Bringing HubSpot into Cowork would mean repackaging it as an MCP connector — a separate project. ([claude-code#40495](https://github.com/anthropics/claude-code/issues/40495), [#47993](https://github.com/anthropics/claude-code/issues/47993))
- **Deletes and merges are not undoable.** HubSpot exposes no un-delete/un-merge API. These are classified non-undoable and say so at preview time rather than promising a rollback that can't happen.
- **Python ≥ 3.12 required.** The venv is built from the `python3` on `PATH`; older interpreters fail the `requires-python` constraint.
- **Venv provisioning is silent on failure.** The hook always exits 0 so it never blocks the session. After a fresh install, check `${CLAUDE_PLUGIN_DATA}/install.log` and `venv.path` if `/hubspot` returns a router import error. `bin/hubspot` self-heals a version-drifted venv on every invocation.
- **Secrets are stored locally** — portal tokens live under `~/.claude/hubspot/`. Protect that directory and exclude it from backups/sync per your policy.
- **Some HubSpot objects can't be created via API** — reports and dashboards have no public POST endpoint; those are handed off to the UI honestly rather than faked.

## Questions or issues?

Open an issue at [github.com/promptmetrics/hubspot-claude/issues](https://github.com/promptmetrics/hubspot-claude/issues).

## License

MIT — see [LICENSE](LICENSE).
