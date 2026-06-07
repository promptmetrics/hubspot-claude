# HubSpot Agent

A Claude Code skill (`/hubspot`) for natural-language administration of HubSpot CRM. Dispatch 45+ specialist sub-agents to perform CRUD operations across contacts, companies, deals, workflows, lists, pipelines, properties, analytics, engagements, associations, and more — with mandatory human-in-the-loop approval for all writes.

## Quick Start

**Prerequisites:** Python 3.12+, Claude Code, a HubSpot portal ID.

```bash
git clone https://github.com/iiizzzyyy/hubspot-claude.git
cd hubspot-claude
pip install -e ".[dev]"
```

**Authenticate with a Private App Token:**

```
/hubspot setup <portal_id> token <pat-na1-...>
```

Or use OAuth 2.0 for team setups (see [`docs/QUICKSTART.md`](docs/QUICKSTART.md)).

**Verify:**

```
/hubspot status
```

## Architecture

```
User (Claude Code session)
    |
    v
/hubspot "find duplicate contacts and merge them"
    |
    v
Parent Orchestrator (routing + scope validation)
    |
    +---> HygieneAgent (find duplicates)
    |        +---> Returns: list of duplicate pairs
    |
    +---> [HITL Approval]
    |
    +---> HygieneAgent (merge contacts)
             +---> Returns: merged records
```

- **Parent Orchestrator** — routes requests, validates scope, handles HITL approval, dispatches sub-agents, reconciles results
- **45+ Sub-Agents** — each domain agent runs in isolation with focused tools and prompts
- **No custom orchestration framework** — uses Claude Code's native `Agent` tool
- **State lives in conversation context + disk cache** — no LangGraph required

## Agent Domains

| Domain | Agents | Key Operations |
|--------|--------|----------------|
| Objects | contacts, companies, deals, tickets, products, line_items, custom objects | CRUD, search, batch ops |
| Properties | standard & custom properties, groups | create, update, migrate |
| Workflows | flows, legacy workflows, blueprints | build, enroll, analyze |
| Lists | static & dynamic lists, memberships | create, update, segment |
| Pipelines | deals, tickets, custom pipelines & stages | CRUD, reorder |
| Users | owners, teams, permissions | assign, audit |
| Hygiene | duplicates, stale records, unassigned | merge, clean, alert |
| Analytics | reports, dashboards, funnels | build, schedule |
| Associations | contact↔company, deal↔contact, custom | create, delete, label |
| Engagements | calls, emails, meetings, notes, tasks | log, sync |
| Commerce | orders, carts, invoices, subscriptions, fees, taxes, discounts | manage, reconcile |
| Raw API | any HubSpot v3 endpoint | GET/POST/PATCH/DELETE |

## Project Structure

```
src/hubspot_agent/
├── orchestrator.py       # Parent router, HITL, dispatch
├── cli.py                # /hubspot skill entry point
├── client.py             # Async HTTP client with rate limiting
├── models.py             # Shared Pydantic models
├── dispatch.py           # Agent dispatch utilities
├── persistence.py        # Preview / checkpoint storage
├── agents/               # 45+ domain sub-agents
├── tools/                # 20+ tool modules (CRUD wrappers)
├── blueprints/workflows/ # Pre-built workflow templates
└── prompts/              # System prompt fragments

tests/                    # 70+ test modules
docs/                     # Design specs, ADRs, user manual
plans/                    # HTML design specs & task tracker
```

## Testing

```bash
pytest -x                    # run all tests
pytest tests/test_integration.py -v   # integration tests
```

## Authentication

- **OAuth 2.0** or **Private App tokens** only (no API keys)
- **Portal auto-detection:** reads `.hubspot-portal` file in working directory
- **Multi-portal support:** isolated state per portal

## Key Design Decisions

1. **Sub-agent isolation** — each agent runs with minimal tools to reduce error rates
2. **Read-based previews** — HubSpot has no dry-run; we preview reads before writes
3. **Count-based confirmation** — destructive ops require explicit user confirmation
4. **Reusable client** — async `httpx` client with built-in rate limiting and retries

See [`docs/adr/`](docs/adr/) for Architecture Decision Records.

## Documentation

- [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — 10-minute setup guide
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) — Tool and agent reference
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — Demo script for stakeholders
- [`docs/superpowers/USER_MANUAL.md`](docs/superpowers/USER_MANUAL.md) — Full user manual
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — Design specifications

## License

MIT
