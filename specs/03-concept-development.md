# 03-Concept Development: Self-Improving Claude Code Plugin

---
name: "Self-Improving Plugin Concept Development"
description: "User journeys, technical concept, AI feasibility, and refined solution narrative"
type: "project"
---

## User Journeys & Jobs-to-be-Done

### Primary Personas

**1. Alex — Polyrepo Power User**
- Senior/Staff Engineer touching 10-15 repos daily
- Frustrated by Groundhog Day corrections (same fix, every session)
- Copies working patterns repo-to-repo but skills rot quickly
- Success = a week without typing the same correction twice

**2. Jordan — Skill Developer / Platform Engineer**
- Maintains internal Claude Code skills for 20-80 engineers
- Skill rot erodes trust in the platform team
- Reactive maintenance is a treadmill; wants prevention
- Success = error reports trend downward without manual patches

**3. Morgan — Team DevEx Lead**
- Director/VP accountable for productivity and incidents
- Needs governance, audit trails, rollback capability
- "Autonomy without guardrails is a liability"
- Success = measurable reduction in repeated errors; zero unapproved AI code changes in production paths

### Jobs-to-be-Done

| Persona | Functional Job | Emotional Job |
|---------|---------------|---------------|
| Alex | "Help me avoid repeating the same corrections so I can maintain flow state" | "Help me feel like Claude Code actually knows my repos" |
| Jordan | "Help me detect failure patterns and propose fixes automatically" | "Help me feel like the skills I build are living systems, not static documents that decay" |
| Morgan | "Help me enforce approval gates and audit trails so I can answer compliance questions" | "Help me feel confident that a self-improving plugin won't introduce a subtle bug that propagates across 100 repos" |

### Journey Map: Alex (Polyrepo Power User)

1. **Awareness**: Alex opens a familiar repo; Claude makes the same mistake as last week.
   - *Friction*: Emotional tax of repetition; prior effort feels wasted.
   - *Opportunity*: Subtle notification — "You've corrected this 3 times. Want me to suggest a permanent fix?"

2. **Consideration**: Plugin surfaces a proposed diff after the third similar correction.
   - *Friction*: Diff review takes Alex out of flow; unclear scoping (repo-local vs global).
   - *Delight*: Diff is exactly what Alex would have written; plugin explains *why* with data.
   - *Opportunity*: Clear scoping language + one-click rollback info.

3. **Adoption**: Alex approves the first self-edit. Next session, Claude gets it right immediately.
   - *Friction*: Incomplete fixes or too many proposals = approval fatigue.
   - *Delight*: First session with zero corrections needed.
   - *Opportunity*: "Teach me" mode for proactive pattern teaching without waiting for repetition.

4. **Retention**: Alex sees 3-4 auto-suggested fixes per month across repos.
   - *Friction*: Plugin proposes fix in rarely-used repo; bad auto-edit causes 10-min debug.
   - *Delight*: Cross-repo learning — "You fixed this in repo A; apply to repo B?"
   - *Opportunity*: Confidence threshold setting — only auto-propose when signal is very clean.

### Critical Friction Points

1. **Transient Error Trap**: Network timeout causes false signal. Plugin proposes incorrect fix. *Mitigation*: Error classification must distinguish transient from persistent; minimum frequency threshold before proposing.
2. **Approval Fatigue at Scale**: 15 repos × 3-5 proposals/week = blanket approval. *Mitigation*: Configurable confidence thresholds, batch reviews, smart suppression.
3. **Ownership Ambiguity**: User-project code changed, not the skill. Plugin wrongly proposes editing the skill. *Mitigation*: Hook context includes git diff; plugin asks "skill issue or project issue?"
4. **Cascading Self-Edit Failure**: Bad hook edit causes more errors → more bad self-edits. *Mitigation*: Immutable audit log, rate-limits per file per day, broader review for recently-edited files.

---

## Technical Concept

### Proposed Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Runtime** | Python 3.12+ | Matches existing project; hooks and skills are Python-native |
| **Persistence** | SQLite (`sqlite3`, WAL mode) | Zero-config, local, ACID. No external infrastructure |
| **Patch Handling** | `unidiff` + `difflib` | Reliable unified-diff parsing and application |
| **Validation** | `ast.parse`, `ruff`, `pytest` | Syntactic and behavioral validation before commit |
| **AI/ML** | Anthropic Claude API | Re-use existing credentials; best-in-class code generation |
| **Version Control** | Git CLI via `subprocess` | Rollback is first-class requirement |
| **Config** | Pydantic | Type-safe settings (mutable file allowlist, approval thresholds) |

### Core System Components

#### 1. Capture Layer — Hook Interceptor
A `post_tool_execution` hook registered in Claude Code's hook system.
- **Success path**: Single boolean check. Sub-millisecond overhead.
- **Failure path**: Serializes minimal error envelope (tool name, args, error type, message, stack trace, active SKILL.md path, CWD) → async SQLite write.

#### 2. Event Store
SQLite at `.claude/self-improve/events.db`:
- **`raw_events`**: Immutable error instances
- **`clusters`**: Deduplicated error signatures (fingerprint = `tool_name + normalized_message_hash`)
- **`candidates`**: LLM-generated patches (unified diff + rationale + target file paths)
- **`promotions`**: Human approval decisions + linked git branch names

#### 3. Curator Engine
Triggered by `/improve-scan` slash command or on session start.
1. **Clustering**: Groups unclustered `raw_events` using deterministic fingerprints (regex normalization + SHA-256). Fast, local, offline.
2. **Fix Synthesis**: For each new cluster, constructs prompt: current source + error message + frequency. LLM generates unified diff + rationale.
3. **Candidate Storage**: Stores diff. Does **not** touch disk yet.

#### 4. Approval Gate
Slash command: `/improve-review`.
- Lists pending candidates with error context, inline diff preview, and LLM rationale.
- User approves or rejects per candidate. Rejected candidates archived to prevent regeneration.

#### 5. Applicator Engine
Executes **only on human approval**:
1. Checks git working tree is clean (or auto-stashes).
2. Creates branch: `self-improve/YYYYMMDD/<candidate-id>`.
3. Applies unified diff to working tree.
4. **Validation gate**: `ast.parse` → `ruff check` → `pytest` for affected modules.
   - If validation fails: abort, leave branch empty, notify user.
5. Commits with structured message:
   ```
   fix(self-improve): <rationale>
   Error signature: <fingerprint>
   Approved-by: human
   ```
6. Notifies user: "Branch `self-improve/...` created. Rollback: `git switch -` or `git reset --hard`".

#### 6. Meta-Skill (`SKILL.md`)
Defines slash commands:
- `/improve-scan` — Run curator
- `/improve-review` — Open approval gate
- `/improve-status` — Show cluster/candidate/promotion counts

### Data Flow

```
[User Tool Invocation]
         |
         v
[Hook: Post-Tool] --(error)--> [Event Store: raw_events]
         |                             |
    (success, no-op)            [Curator Trigger]
                                         |
                                         v
                              [Cluster & Synthesize]
                                         |
                                         v
                              [Candidate Store]
                                         |
                              [User: /improve-review]
                                         |
                                         v
                              [Approval Gate] --(reject)--> [Archive]
                                         |
                                    (approve)
                                         |
                                         v
                              [Git Branch + Diff Apply]
                                         |
                                         v
                              [Validation (AST/Tests)]
                                         |
                              (pass)     |     (fail)
                                 |       |
                                 v       v
                              [Commit] [Abort / Log]
```

### Scalability Considerations
- **Success-path overhead**: Target <1 ms (boolean check only).
- **Storage**: SQLite WAL + 90-day raw event retention.
- **LLM cost**: Bounded by cluster count, not error count. ~$1/month for moderate usage.
- **Concurrency**: Single-user tool; SQLite WAL is sufficient.

### Major Technical Risks

1. **Hook API Surface (High Risk)**: Claude Code hooks may not expose full exception objects or allow disk I/O. If hooks are sandboxed, Capture Layer cannot function.
2. **Hot-Reload (High Risk)**: Unknown whether Claude Code reloads `SKILL.md` or Python hooks without process restart. If restart required, the loop is "self-modifying" but not "self-improving in-session."
3. **Patch Correctness (Medium Risk)**: LLM diffs may be syntactically invalid or apply to wrong line numbers. AST + tests mitigate but don't eliminate.
4. **Escalation of Privilege (Medium Risk)**: Malicious error messages could prompt destructive patches. Mitigation: file-path allowlist, human diff review, git rollback.
5. **Feedback Loops (Low-Medium Risk)**: Bad fix → new errors → new bad patches. Mitigation: one-candidate-per-branch, mandatory human review.

---

## AI Feasibility Assessment

### Verdict: Technically feasible, architecturally dangerous

The concept can be built within constraints, but autonomous Python patch paths introduce compounding-error risk that approval gates alone cannot reliably contain.

### Core AI Tasks

| Task | Approach | Accuracy | Latency | Cost |
|------|----------|----------|---------|------|
| **Error Classification** | Few-shot LLM (Haiku/GPT-4o-mini) + rule-based fallback | 80-90% clear cases; 60% ambiguous | 500-1200ms | ~$0.001/classification |
| **Root Cause Analysis** | RAG over codebase + stack trace extraction | 60-75% correct file; 80%+ with stack traces | 2-5s | $0.01-0.03/query |
| **Patch Generation** | LLM (Sonnet 4 / GPT-4o) with file + error context | 40-60% overall; 60-75% markdown; 30-45% Python | 10-25s | $0.02-0.10/patch |
| **Safety Verification** | Rule-based (85-95%) + LLM (70-80%) | 85-95% surface risk; 70-80% semantic | <100ms / 2-3s | Negligible / $0.005 |
| **Pattern Clustering** | Embedding + HDBSCAN or cosine threshold | 75-85% identical; 40-55% same-root-cause | 5-15s | ~$0.0001/error |

### Monthly Cost Estimate (Moderate Usage)
| Activity | Frequency | Cost |
|---|---|---|
| Passive capture | Every error | $0 |
| Error classification | ~100/week | ~$0.10 |
| Weekly curation | 1/week | ~$0.20 |
| **Total** | | **< $1/month** |

### The Compounding Risk Problem

Individual tasks are solvable, but autonomous self-modification creates failure modes approval gates cannot contain:

1. **Approval fatigue**: Weekly proposals → rubber-stamping. A "low-risk" prompt behavior change is more dangerous than an obviously risky Python change because it bypasses scrutiny.
2. **Silent regressions**: Patch fixing Error A introduces Error B under unseen conditions. No automated test suite in a Claude Code session catches this.
3. **Context window ceiling**: At ~7,000 lines, multi-file patch reasoning hits practical limits.
4. **No rollback guarantee**: If a patch corrupts dispatch logic, the plugin may be unable to propose further fixes or revert itself.

---

## Alternative Architecture: "Suggestion-Only Self-Improvement"

The AI Engineer recommends this safer alternative:

1. **Capture**: Log every error to local SQLite with embeddings (passive, <$0.01).
2. **Cluster**: Weekly HDBSCAN over error embeddings to find recurring patterns.
3. **Propose (prompt layer only)**: For recurring errors, generate proposed SKILL.md or prompt changes. Present as diff preview. **Never auto-apply.**
4. **Escalate (code layer)**: For Python-level fixes, generate a GitHub issue or PR description with reproduction steps and proposed patch. **Do not modify `.py` files autonomously.**
5. **Validate**: Before any code patch is proposed, require the system to generate a test case that reproduces the error. If the plugin cannot write a reproducer, the fix is too speculative.

**Trade-offs**:
- Keeps latency <5s for no-op, <30s for curation.
- Costs <$1/month.
- Preserves meaningful human agency (user implements code changes, not just approves).
- Avoids compounding-error trap.
- Limits genuinely novel "self-rebuilding" capability.

### If You Must Allow Code Self-Modification

Add these hard constraints:
- **Immutable core**: Hand-audited dispatch/safety core is read-only. Only prompts, tool descriptions, and heuristics are mutable.
- **Test mandate**: Every proposed patch must be accompanied by a generated test. Patch only presented if test fails before and passes after (simulated).
- **Shadow mode**: Patches run in "shadow" evaluation for N sessions before proposing application.
- **Git checkpoint**: Auto-commit before any patch. `git reset` must be one-command recovery.

Even with these, the risk/reward ratio is poor compared to suggestion-only.

---

## Refined Solution Narrative

### Two Paths Forward

**Path A: Full Self-Modification (User's original vision)**
- Plugin autonomously edits both markdown (SKILL.md, CLAUDE.md) and Python files.
- Human approval gate + validation (AST/tests) + git checkpoint.
- Risk: Compounding errors, approval fatigue, silent regressions.
- Reward: Genuine self-rebuilding; closest to "plugin fixing its own code."

**Path B: Suggestion-Only (AI Engineer's recommendation)**
- Plugin autonomously edits markdown/prompt files only.
- For Python fixes, generates issues/PRs with reproduction steps; human implements.
- Risk: Lower; human remains in the loop for all code changes.
- Reward: Safer; still eliminates memory-action gap for config/prompt layers.

### Recommended Hybrid

Given the validation risks (especially user trust in AI self-edits), start with **Path B for Python, Path A for markdown**:

1. **Phase 1 (MVP)**: Self-modify SKILL.md, CLAUDE.md, and prompt files only. These are low-risk, high-value, and where most "Groundhog Day corrections" live.
2. **Phase 2 (v1.1)**: If Phase 1 proves safe and users trust it, add Python self-modification with the hard constraints above (immutable core, test mandate, shadow mode).
3. **Phase 3 (v2.0)**: Cross-project memory sharing via MCP server.

This lets you ship value immediately while validating the riskiest assumption (user trust) before enabling the most dangerous capability (autonomous code editing).

---

*Phase 3 Output — Awaiting user decision: Proceed with full self-modification, suggestion-only, or the recommended hybrid?*
