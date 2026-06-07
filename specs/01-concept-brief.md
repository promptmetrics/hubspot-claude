# 01-Concept Brief: Self-Improving Claude Code Plugin

---
name: "Self-Improving Claude Code Plugin"
description: "A Claude Code plugin that learns from errors and rebuilds itself using the Capture → Curate → Promote loop"
type: "project"
---

## Problem Statement

Developers using Claude Code repeatedly hit the same friction: the agent forgets project-specific conventions, repeats corrected mistakes, and fails to accumulate operational knowledge across sessions. Existing memory mechanisms (`CLAUDE.md`, `.claude/rules/`) are static — they must be manually maintained and quickly drift out of sync with evolving codebases. The result is wasted cycles re-explaining context, re-fixing the same errors, and manually curating rules that should emerge organically from actual work.

## Proposed Solution

A lightweight plugin implementing the **Capture → Curate → Promote** feedback loop directly within Claude Code's plugin architecture:

- **Capture**: `PostToolUse` and `SessionEnd` hooks observe outcomes. On errors, corrections, or explicit user feedback, the plugin appends structured observations (error signature, correction applied, root cause, lesson) to a scratchpad `MEMORY.md`. Zero overhead on success — hooks are no-ops for successful, unmodified tool calls.
- **Curate**: A slash command (e.g., `/reflect`) or dedicated agent reviews `MEMORY.md` on demand or on schedule, clusters recurring patterns, and flags candidates for promotion based on frequency and impact.
- **Promote**: High-signal patterns graduate from `MEMORY.md` to durable, human-approved rules in `CLAUDE.md` or `.claude/rules/*.md`. Alternatively, complex multi-step lessons become standalone `SKILL.md` files invocable via `/skill`. Every promotion requires explicit user approval — the system suggests, the human decides.

## Core Value Proposition

**Claude Code that gets smarter the more you use it — without manual upkeep.** Users spend less time correcting repetitive mistakes and updating static docs. Institutional knowledge accumulates automatically, turning individual fixes into permanent team leverage. The system respects user control: it captures silently, surfaces patterns proactively, but never enforces new rules without explicit consent.

## Key Assumptions

| # | Assumption | Validation Approach |
|---|-----------|-------------------|
| 1 | **Error signal is rich enough to learn from.** Most corrections are inferable from tool output deltas (before/after) and user follow-up messages. If errors are too ambiguous (e.g., "no, do it better"), the capture step yields noise. | Spike: log 50 sessions and measure what % of corrections produce a clean, reusable rule. |
| 2 | **Users will actually curate and approve promotions.** If the `/reflect` command is ignored or promotion approvals feel burdensome, `MEMORY.md` bloats and value decays. | Build friction audit: time-to-approve for a suggested rule should be <10 seconds; measure weekly active curators. |
| 3 | **Claude Code hooks fire with sufficient granularity and stability.** `PostToolUse` must expose error state and corrected output; `SessionEnd` must fire reliably. If hook contracts change or lack context, the pipeline breaks. | Prototype: implement a passive capture hook for one tool class and verify data fidelity across 20 sessions. |
| 4 | **Promoted rules improve outcomes rather than conflict.** As `CLAUDE.md` and `.claude/rules/` grow, overlapping or stale rules can degrade performance. The system must avoid "rule rot." | Establish a deprecation cadence: every promoted rule gets a timestamp and confidence score; auto-suggest review if a rule is triggered but overridden >3 times. |
| 5 | **Zero overhead on success is achievable.** The plugin must not perceptibly slow normal operations. If hooks add latency or disk I/O on every call, users will disable it. | Benchmark: hook execution time <5ms for no-op path; `MEMORY.md` append-only writes batched or async where possible. |

## Market Landscape

### Market Snapshot
The AI coding assistant market is growing at 15–48% CAGR depending on scope, with the broader tools market reaching ~$12.8B in 2026 (up from $5.1B in 2024). The dominant shift is from autocomplete/chat to **agentic coding**: multi-agent architectures, background PR generation, and persistent memory. 57% of organizations now have agents in production, and ~42–51% of committed code is AI-assisted. Memory and context are the primary 2026 battlegrounds for differentiation.

### Competitor / Adjacent Solution Profiles

#### 1. Self-Improving Agent (alirezarezvani/claude-skills)
A Claude Code skill that curates Claude's built-in `MEMORY.md` into durable project rules.
- **Strengths**: Simple, elegant promotion lifecycle. Detects recurring patterns, graduates them to `CLAUDE.md` or `.claude/rules/`, and cleans up stale entries. Works across 12+ AI coding tools.
- **Weaknesses**: Entirely manual curation. You must run `/si:review`, then `/si:promote`, then `/si:extract` — it does not detect failures automatically or propose improvements proactively. It is a *librarian*, not a *learner*.

#### 2. Claude Coach (netresearch/claude-coach-plugin)
A self-improving learning system for Claude Code with real-time signal detection hooks.
- **Strengths**: The strongest **automatic signal detection** in the ecosystem. Hooks into `UserPromptSubmit`, `PostToolUse`, and `Stop` to capture command failures, user corrections, repeated instructions, and tone escalation. Stores events in SQLite, deduplicates them, and generates typed candidates (rules, checklists, snippets, antipatterns). Requires explicit user approval before any write.
- **Weaknesses**: Still fundamentally a manual approval queue (`/coach review` → `/coach approve`). The agent does not *act* on its own learnings — it only queues suggestions for human review. No cross-project memory sharing.

#### 3. GitHub Copilot Agentic Memory
GitHub's first-party memory system (public preview Jan 2026).
- **Strengths**: **Cross-agent memory** — memories created by the code review agent flow to the coding agent, CLI agent, etc. Uses just-in-time citation verification and auto-expires stale memories after 28 days. Delivers measurable impact: +7% PR merge rates, +2% positive review feedback.
- **Weaknesses**: Siloed to GitHub Copilot ecosystem. No portability to Claude Code, Cursor, or CLI agents. Enterprise-only roadmap feel; limited customization for individual power users.

#### 4. Cursor Rules + Memories
Cursor's hybrid system: static `.cursor/rules/*.mdc` files + dynamic "Memories" suggested by a Sidecar model.
- **Strengths**: Best-in-class **scoped rules** via glob patterns (`alwaysApply`, `Apply Intelligently`, file-specific triggers). Memories are user-approved per-project. Strong UX for enforcing conventions.
- **Weaknesses**: Memories are **per-project and per-individual** — they do not cross project boundaries or teammates. No automatic failure detection; the Sidecar observes conversations but does not hook into stderr, test failures, or CI.

#### 5. Letta Code
An open-source, memory-first coding agent (Dec 2025).
- **Strengths**: Treats memory as the primary primitive, not an add-on. Agents persist across sessions, learn skills from experience, and store them as versioned `.md` files. Supports vector, full-text, and hybrid search over past conversations. Model-agnostic and ranked #1 on TerminalBench.
- **Weaknesses**: Requires running the Letta server and API. The learning loop is session-driven, not event-driven — it does not specifically hook into tool failures or user corrections in real time.

### Emerging Technologies & Signals

| Technology | Relevance |
|---|---|
| **MCP (Model Context Protocol)** | Became the universal integration standard (Linux Foundation) in 2025. Enables cross-tool memory servers. Any self-improving plugin should expose its memory as an MCP server for interoperability. |
| **Hybrid retrieval (vector + BM25 + reranking)** | Used by `memory-lancedb-pro` and Letta. Essential for scaling memory beyond simple Markdown files. |
| **Weibull-based memory decay** | Configurable forgetting curves to prevent memory bloat. |
| **Self-modifying systems** | Aider now writes ~70–72% of its own codebase. Proof that agents maintaining their own code is viable. |
| **Structured commit-history memory** | MemCoder (research) distills git commits into intent-to-code mappings with root-cause analysis. A production version does not exist yet. |
| **Real-time signal hooks** | Claude Coach's `PostToolUse` / `UserPromptSubmit` hooks are the bleeding edge for detecting friction without human transcription. |

### Whitespace Opportunities

1. **Autonomous self-modification** — Existing tools curate *rules* or *memories*, but none automatically rewrite their own skill/plugin code based on encountered errors. A plugin that patches its own `SKILL.md` or Python hooks after repeated failures would be genuinely novel.
2. **Error-native learning** — Most systems learn from *conversation*. There is a gap for deep integration with stack traces, test failures, CI logs, and linter output as structured learning signals.
3. **Cross-project, cross-team memory** — Every major player silos memory per-project or per-user. A shared memory layer (via MCP or git-synced `.claude/rules/`) that propagates lessons across an org's repos is an open problem.
4. **Trust-tiered autopromotion** — Manual approval for every candidate creates friction. A "trust but verify" system that autopromotes low-risk conventions (naming, file paths) while requiring approval for risky changes (build commands, destructive ops) would outpace Claude Coach's all-or-nothing queue.
5. **Git-history distillation** — MemCoder proved commit history can be turned into structured memory, but no commercial tool does this. A plugin that retroactively analyzes past PRs, reverts, and bug fixes to seed initial memory would dramatically shorten the cold-start phase.

### Bottom Line

The self-improving Claude Code plugin space is crowded with *memory curators* but empty of *self-rebuilders*. The near-term opportunity is a system that bridges Claude Coach's real-time signal detection with Letta's persistent skill learning, adds cross-project MCP sharing, and — critically — closes the loop by auto-updating its own implementation when it encounters repeated failures.

## Next Step to Validate

Build a 1-day spike implementing passive Capture for a single tool class (e.g., `Edit`), then manually review whether the emitted observations are clean enough to support automated Curate/Promote.

---

*Phase 1 Output — Awaiting user approval before proceeding to Phase 2.*
