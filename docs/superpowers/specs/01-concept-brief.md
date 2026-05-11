# Concept Brief: HubSpot Admin Agent

**Date:** 2026-05-10
**Status:** As-built documentation
**Companion docs:** [PRD](05-prd.md) · [Technical Spec](06-technical-spec.md) · [UX Spec](07-ux-spec.md) · [Roadmap](08-roadmap.md)

---

## 1. Problem Statement

HubSpot administration is fragmented, time-consuming, and error-prone. A single request like "reorganize our deal properties and build a follow-up workflow" requires navigating dozens of screens, understanding object schemas, and manually translating business logic into HubSpot's native automation language. There is no persistent, conversational layer that lets an administrator simply describe intent and delegate execution.

## 2. Proposed Solution

A Claude Code skill (`/hubspot`) that acts as a persistent HubSpot admin assistant. Users interact via natural language chat within Claude Code. The system routes requests to specialized domain agents, each with focused tools and prompts. Results are synthesized back into the main conversation. All write operations require human-in-the-loop approval.

**Key characteristics (as built):**
- Runs inside Claude Code via custom orchestrator (not native `Agent` tool — a known gap)
- Natural language input, structured output (markdown tables, diffs, previews)
- Inline HITL approval for all write operations
- Persistent conversation context across requests
- Multi-portal support with isolated state
- 15 specialist agents covering CRM, automation, analytics, and content
- DAG planning for compound requests
- Extensibility via plugins and hooks

## 3. Core Value Proposition

**For HubSpot admins (primary persona):**
- Reduce time spent navigating HubSpot UI for routine admin tasks
- Natural language interface eliminates need to learn HubSpot API details
- Mandatory approval gates prevent accidental destructive changes
- Bulk operations with preview and checkpointing reduce risk

**For RevOps managers:**
- Consistent, auditable admin operations
- Undo snapshots and action ledger for accountability
- Schema-aware validation catches errors before API calls

## 4. Key Assumptions

1. **Users are already Claude Code users.** The skill requires Claude Code context. Users must be comfortable with CLI-style interaction.
2. **HubSpot API access is available.** The user must have a HubSpot portal with API scopes granted. Private App or OAuth setup is required.
3. **Natural language routing is sufficient.** The system uses keyword heuristics + LLM fallback for routing. Assumes HubSpot vocabulary is consistent enough for pattern matching.
4. **HITL approval is acceptable friction.** The assumption is that admins prefer safety over speed for writes.
5. **File-based state is adequate.** All state lives in `~/.claude/hubspot/` JSON/JSONL files. Assumes single-user, low-concurrency usage.

## 5. Domain

- **Industry:** SaaS / CRM administration
- **Primary users:** HubSpot admins, RevOps managers, sales operations leads
- **Secondary users:** Technical founders, developers who manage HubSpot portals
- **Anti-persona:** Non-technical sales reps (no Streamlit dashboard or GUI fallback)

## 6. Constraints

- **Tech stack:** Python 3.12+, httpx, pydantic, aiohttp
- **Auth:** OAuth 2.0 or Private App tokens only (HubSpot deprecated API keys)
- **No database:** All state is file-based under `~/.claude/hubspot/`
- **Rate limits:** HubSpot's 100 req/10s standard limit, 4 concurrent batch ops max
- **No dry-run:** HubSpot API does not support dry-run for most writes; previews are read-based
- **Claude Code dependency:** Must run inside Claude Code session (though orchestrator is custom, not native)

## 7. Out of Scope (Current Reality)

The original spec defined these as out of scope for MVP. The implementation expanded beyond this list:

| Item | Original Verdict | Implementation Status |
|------|------------------|----------------------|
| Custom object support | Out of scope (MVP) | Built (CustomObjectsAgent) |
| HubSpot CMS/file manager | Out of scope (MVP) | Built (CMSAgent) |
| Marketing campaigns | Out of scope (MVP) | Built (MarketingAgent) |
| Service hub (tickets, KB) | Out of scope (MVP) | Built (ServiceAgent) |
| Real-time sync / webhooks | Out of scope (MVP) | Built (webhooks.py + server.py) |
| External dashboard or UI | Out of scope (MVP) | Not built |
| Team collaboration / shared sessions | Out of scope (MVP) | Partial (RBAC exists but no real multi-user) |
| Multi-step workflow complex branching | Out of scope (MVP) | Partial (blueprints exist, complex branching not built) |

## 8. Open Questions

1. Is the target user a solo admin or a team? This affects whether RBAC, plugins, and shared sessions are justified.
2. What is the business model? Personal tool, open-source project, or commercial product?
3. Should the implementation be pruned to match the original 11-agent MVP, or should the spec expand to match the 15-agent reality?
