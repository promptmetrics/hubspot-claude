# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

**Active development.** All 14 implementation phases are complete. The codebase contains:

- **45+ domain sub-agents** across Objects, Properties, Workflows, Lists, Pipelines, Users, Hygiene, Analytics, Associations, Engagements, RawAPI, Commerce, Data, Leads, and more.
- **20+ tool modules** providing CRUD wrappers for the HubSpot v3 API.
- **70+ test modules** with 560+ passing tests.
- **Pre-built workflow blueprints** for real-estate and generic CRM use cases.

## What This Builds

A Claude Code skill (`/hubspot`) that administers HubSpot CRM via natural language. It dispatches specialist sub-agents to perform CRUD operations, with mandatory human-in-the-loop approval for all writes.

## Key Design Decisions

- **No custom orchestration framework** — uses Claude Code's native `Agent` tool for sub-agent dispatch
- **No LangGraph** — state lives in conversation context + disk cache
- **Auth:** OAuth 2.0 or Private App tokens only (no API keys)
- **Portal auto-detection:** reads `.hubspot-portal` file in working directory
- **HITL approval:** read-based previews (HubSpot has no dry-run), count-based confirmation for destructive ops
- **State passing:** parent embeds `proposed_payload` in re-dispatch prompt since sub-agents are stateless

## Tech Stack

- Python 3.12+, `httpx`, `pydantic`, `aiohttp`
- Tests: `pytest`, `pytest-asyncio`, `respx`, `hypothesis`
- Build: `hatchling`

## Source of Truth

Before implementing anything, read:
1. The design spec (`docs/superpowers/specs/...`) for architecture and behavior
2. The implementation plan (`docs/superpowers/plans/...`) for task order and file structure
3. The ADRs in `docs/adr/` for context on past architectural decisions

## Skills

- Load skill from `~/.claude/skills/autolog`
