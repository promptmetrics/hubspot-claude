# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is a greenfield project. No implementation code exists yet. The repository currently contains:

- `docs/superpowers/specs/2026-05-06-hubspot-agent-design.md` — Approved design spec
- `docs/superpowers/plans/2026-05-06-hubspot-agent-plan.md` — Implementation plan (38 tasks, 7 phases)

## What This Builds

A Claude Code skill (`/hubspot`) that administers HubSpot CRM via natural language. It dispatches 11 specialist sub-agents (Objects, Properties, Workflows, Lists, Pipelines, Users, Hygiene, Analytics, Associations, Engagements, RawAPI) to perform CRUD operations, with mandatory human-in-the-loop approval for all writes.

## Key Design Decisions

- **No custom orchestration framework** — uses Claude Code's native `Agent` tool for sub-agent dispatch
- **No LangGraph** — state lives in conversation context + disk cache
- **Reuses `HubSpotClient`** from the existing `agent2` project (`/Users/izzy/Documents/agent2/src/hive/hubspot/client.py`)
- **Auth:** OAuth 2.0 or Private App tokens only (no API keys)
- **Portal auto-detection:** reads `.hubspot-portal` file in working directory
- **HITL approval:** read-based previews (HubSpot has no dry-run), count-based confirmation for destructive ops
- **State passing:** parent embeds `proposed_payload` in re-dispatch prompt since sub-agents are stateless

## Planned Tech Stack

- Python 3.12+, `httpx`, `pydantic`
- Tests: `pytest`, `pytest-asyncio`, `respx`
- Build: `hatchling`

## Source of Truth

Before implementing anything, read:
1. The design spec (`docs/superpowers/specs/...`) for architecture and behavior
2. The implementation plan (`docs/superpowers/plans/...`) for task order and file structure

## Related Project

The existing `agent2` project at `/Users/izzy/Documents/agent2` contains reusable components:
- `src/hive/hubspot/client.py` — async HTTP client with rate limiting
- `src/hive/tools/hubspot/objects.py` — object CRUD tools (pattern to follow)
- `src/hive/agent/coordinator.py` — intent parsing logic (to be replaced, not reused)

## Skills
  - Load skill from `~/.claude/skills/autolog`