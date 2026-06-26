# HubSpot Agent

A Claude Code plugin (`/hubspot`) for natural-language administration of HubSpot CRM. Claude orchestrates specialist sub-agents that each call the `hubspot` CLI over Bash to perform CRUD across contacts, companies, deals, workflows, lists, pipelines, properties, analytics, engagements, associations, and more — with mandatory human-in-the-loop approval for every write.

The agent and tool catalogs live in code. As of this release the registry holds **44 specialist sub-agents** and **75 tools**; discover the current set with `hubspot agents list` and `hubspot tools list` rather than trusting this number.

## Install

### From the marketplace

```
/plugin marketplace add iiizzzyyy/hubspot-claude
/plugin install hubspot@hubspot-claude
```

On the first session after install, a `SessionStart` hook provisions an isolated venv under `${CLAUDE_PLUGIN_DATA}/venv` (preferring `uv`, else `python3 -m venv` + `pip install`) and writes `venv.path` so the `bin/hubspot` resolver can find it. The hook rebuilds the venv only when `pyproject.toml` changes, fails gracefully (never blocks the session), and does **not** start the daemon.

### Local development

```bash
git clone https://github.com/iiizzzyyy/hubspot-claude.git
cd hubspot-claude
pip install -e ".[dev]"          # editable install with test deps
claude plugin validate ./        # schema-check plugin.json + marketplace.json + hooks
claude --plugin-dir ./           # load the plugin for this session
```

Then invoke `/hubspot` in that session. (If the plugin is also installed from the marketplace, uninstall it first so both copies don't collide.) Confirm the exact invocation name Claude Code registers — it is `/hubspot` for a root `SKILL.md` with `name: hubspot`; update these docs if your local run shows otherwise.

## Authenticate

**Private App token (simplest for personal use):**

```
/hubspot setup <portal_id> token <pat-na1-...>
```

**OAuth 2.0 (for team setups):**

```
/hubspot setup <portal_id> oauth
```

Auth is OAuth 2.0 or Private App tokens only — never API keys. Portal auto-detection reads a `.hubspot-portal` file in the working directory; multi-portal setups keep isolated state per portal.

**Verify:**

```
/hubspot status
```

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
- **Warm-client daemon** — read and write-preview tool calls route through one reused `HubSpotClient` + schema cache for speed; `approve`/`reject`/`loop *`/`route`/`agents` run in-process. The daemon is lazy-started on the first tool call, self-exits after idle, and `bin/hubspot` falls back to the in-process CLI if it's ever unreachable (same correct result, only slower). Manage it with `hubspot serve` / `hubspot serve stop`.
- **Durable loops** — `/hubspot --loop '<goal>'` runs triage → sequential step execution → verify → checkpoint, with `loop status`/`log`/`continue`/`abandon`.

## Sub-commands

| Command | Purpose |
|---------|---------|
| `hubspot status` | Portal, agent readiness, pending approvals |
| `hubspot route '<request>'` | JSON `{agents, rationale}` |
| `hubspot tool <name> --input '<json>'` | Read → JSON; write → preview + `action_id` |
| `hubspot agents list` / `tools list` | Enumerate the registry |
| `hubspot agent-prompt <name>` | Full prompt for one agent |
| `hubspot approve <id> [<count>]` | Execute a previewed write (count required for destructive) |
| `hubspot reject <id>` | Discard a pending write |
| `hubspot --loop '<goal>'` / `loop status\|log\|continue\|abandon` | Durable closed loop |
| `hubspot --pattern '<sample>'` | Sample-verify-scale batch approval |
| `hubspot serve` / `serve stop` | Warm-client daemon lifecycle |
| `hubspot portal auth\|token\|list\|switch` / `setup` / `refresh` | Portal + auth management |

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
└── blueprints/workflows/ # pre-built workflow templates
bin/hubspot               # plugin entrypoint (venv resolver → router)
hooks/                    # SessionStart venv provisioning
.claude-plugin/           # plugin.json + marketplace.json
tests/                    # pytest suite
```

## Testing

```bash
pytest -x                 # full suite
pytest tests/test_install_hook.py -v   # SessionStart venv contract
```

## Key design decisions

1. **Claude orchestrates; the CLI is the source of truth** — sub-agents are stateless and call `hubspot tool` over Bash; proposed payloads are embedded in their prompts.
2. **Read-based previews** — HubSpot has no dry-run, so writes preview the affected records and return an `action_id`; nothing mutates until `approve`.
3. **Count-based confirmation** — destructive operations require the expected count, re-checked at execute time.
4. **One warm client** — the daemon reuses a single `HubSpotClient` + schema cache; every other path runs in-process with identical results.
5. **Three call paths, one handler set** — daemon (warm), in-process fallback (fresh client), and CLI sync all share `handlers.py`.

## License

MIT — see [LICENSE](LICENSE).