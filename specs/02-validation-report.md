# 02-Validation Report: Self-Improving Claude Code Plugin

---
name: "Self-Improving Plugin Validation Report"
description: "User personas, pain points, assumption tests, and validation experiments for self-modifying plugin concept"
type: "project"
---

## User Personas

### Primary

**1. The Polyrepo Power User**
- Uses Claude Code across 5-15+ repositories daily
- Maintains custom `CLAUDE.md` and `SKILL.md` files in multiple repos
- Frustrated by repeating the same corrections (e.g., "we use `pytest` not `unittest`", "don't use `print()`, use the logger")
- Wants their AI assistant to learn codebase conventions permanently, not just within a single conversation

**2. The Skill Developer / Platform Engineer**
- Builds and maintains internal Claude Code skills for their engineering team
- Struggles with skill rot: skills work for a while, then break as APIs or conventions change
- Currently manually updates skill files when errors are reported
- Wants skills that self-heal from real usage patterns rather than requiring manual patches

**3. The Team DevEx Lead**
- Responsible for onboarding and tooling standards across 20-200 engineers
- Wants consistent AI behavior across the org without forcing everyone to maintain local config
- Needs guardrails: autonomous editing is acceptable only with approval gates and audit trails

### Secondary

**4. The Solo Full-Stack Developer**
- Uses Claude Code as a primary coding assistant
- Encounters recurring domain-specific errors (e.g., specific framework patterns)
- Would benefit from automatic adaptation but may not have the expertise to review code patches safely

**5. The AI Tooling Researcher**
- Experiments with autonomous agent architectures
- Interested in the novelty of self-modifying code
- Less concerned with immediate productivity, more with pushing boundaries of agentic behavior

## Pain Points

1. **Groundhog Day Corrections**: Users report correcting Claude Code on the same conventions repeatedly across sessions and repos. The current memory system is too transient.
2. **Skill Maintenance Burden**: Custom skills require manual updates. When underlying APIs change, skills silently fail or produce outdated code. No feedback loop exists to propagate fixes.
3. **Memory-Action Gap**: Existing tools (Claude Coach, etc.) capture insights but leave the user to manually edit files. The cognitive load of curating without applying reduces adoption.
4. **Context Window Pressure**: Large `CLAUDE.md` files stuffed with every learned rule eventually hit token limits. Users need selective, intelligent promotion of rules, not just accumulation.
5. **Trust and Safety Anxiety**: The prospect of an AI editing its own source code triggers legitimate fears about breaking functionality, introducing security issues, or creating irreversible changes.
6. **Cross-Repo Inconsistency**: Learnings in one repo don't transfer to others. A user teaching Claude their preferences in Repo A has to re-teach in Repo B.

## Evidence Strength Assessment

**Moderate-to-Strong, with important caveats**

- **Validated demand**: The existence of Claude Coach, Self-Improving Agent, and active community discussions about "memory curation" confirms that power users want Claude Code to learn and persist knowledge.
- **Validated pain point**: The repeated-correction problem is one of the most common complaints in Claude Code forums and Discord. Users explicitly ask for "memory that actually works."
- **Unvalidated leap**: The jump from *curating memory* to *autonomously editing source code* is large. Existing solutions deliberately stop at human review queues for good reason — self-modifying code is high-risk.
- **Unvalidated willingness to trust**: We don't yet know if users would approve autonomous patches even with gating. The target audience (developers) is technically sophisticated and may be *more* cautious about AI editing code, not less.
- **Unvalidated frequency**: For the "Capture → Curate → Promote → Rebuild" loop to be valuable, users must encounter the same error class frequently enough that automation beats manual fixing.

## Riskiest Assumptions (Ranked)

| Rank | Assumption | Risk |
|------|-----------|------|
| 1 | **Hook context is sufficient** to distinguish plugin bugs from user-project bugs | Hard platform constraint; cannot workaround |
| 2 | **Users trust AI self-edits** even with approval gates and rollback | Concept dies if users reject the premise |
| 3 | **Error patterns are stable and plugin-caused** (not transient or user errors) | Self-improvement requires a clean signal |
| 4 | **Cost/effort is justified** vs. manual fixes | Resume-driven development trap risk |
| 5 | **Self-modification safety** (git + tests + gates sufficient) | Solvable engineering problem if 1-4 pass |

## Validation Experiments

### Experiment 1: Hook Context Diagnostic (Feasibility)
Build a 10-line diagnostic hook that logs full context object to JSONL. Induce 5 distinct failure types and inspect whether the hook identifies the specific plugin source file as root cause.
- **Cost**: 2-4 hours
- **Pass**: Can identify plugin source file as root cause in >=4/5 cases
- **Fail**: Hooks blame user's project or emit generic "command failed" with no plugin traceback
- **Pivot if fail**: Error reporter that suggests fixes in chat but never edits files

### Experiment 2: Trust "Terror Test" (Adoption)
Show 5 Claude Code power users a simulated approval modal: "Claude hit this error 3x. It proposes editing `src/my_plugin/parser.py` with this 4-line diff. [Rollback: `git checkout ...`]. Approve / Reject?"
- **Cost**: 1 day
- **Pass**: >=3/5 approve with clear diff + rollback path; zero respond "never under any circumstances"
- **Fail**: Majority reject even with full transparency
- **Pivot if fail**: Claude Coach mode — plugin explains proposed fix, user copy-pastes it

### Experiment 3: Retrospective Error Audit (Value)
Scan last 30 days of Claude Code conversation history, `.claude/memory/`, or local logs. Tag every error: `plugin_bug`, `user_project_bug`, `transient`, `prompt_error`. Focus on repeated errors (>1 occurrence).
- **Cost**: 1 day
- **Pass**: >=40% of repeated errors are attributable to plugin code flaws
- **Fail**: <20% are plugin-caused; most are user-project state or one-off hallucinations
- **Pivot if fail**: Kill the feature; the problem isn't real

### Experiment 4: Wizard of Oz Cost Study (Viability)
For 1 week, do not build automation. Time every manual plugin fix. Count frequency. Compare total manual time to estimated 2-3 engineer-week build cost for v1.
- **Cost**: 1 week of passive observation
- **Pass**: Manual fixes take >15 min each AND occur >2x/week, or a single plugin bug caused >3 user interruptions
- **Fail**: Fixes are <5 min, <1x/week, and never block a user session
- **Pivot if fail**: Defer to hackathon; manual fixes are trivial

### Experiment 5: Canary Branch Safety Test (Execution)
In a disposable git branch, manually prompt Claude to perform 10 targeted edits on its own plugin files. After each edit, run test suite and verify plugin loads.
- **Cost**: 4 hours
- **Pass**: >=9/10 edits leave plugin functional
- **Fail**: <7/10 succeed, indicating codebase too fragile for automated surgical edits
- **Pivot if fail**: Build stricter guardrails or abandon self-modification

## Recommended Sequence

**Test 1 and 2 in parallel immediately.** They are independent, cheap, and either one failing kills the concept before writing self-modification logic.

- If **#1 fails** → Pivot to a simpler "error reporter"
- If **#2 fails** → Pivot to "Claude Coach" mode (explain fix, user copy-pastes)
- If both pass → proceed to **#3** (error audit)
- If **#3 passes** → run **#4** (cost study) while beginning scoping
- **#5** is a build-quality gate once conviction from 1-4 exists

## Suggested Validation Methods

1. **Structured User Interviews (n=10-12)** — Recruit Claude Code power users who have tried memory/skill tools. Probe specifically on willingness to let AI edit `SKILL.md` or Python files with approval gates.
2. **Quantitative Survey (n=100+)** — Distributed in Claude Code communities. Measure frequency of repeated corrections, trust in autonomous editing on a 1-7 Likert scale.
3. **Concierge / Wizard of Oz Prototype (n=5-8)** — Human monitors user's Claude Code sessions for 1 week. When user corrects Claude twice on same thing, human crafts patch and presents via simulated UI. Measure approval rates.
4. **Competitive Usability Benchmark** — Observe users of existing self-improving tools completing multi-session tasks. Measure time-to-fix and frustration.
5. **Risk-Perception Prototype Test** — Build mock UI showing proposed diff to user's own `SKILL.md` or Python file. Vary risk level (markdown edit vs. Python logic change). Measure approval rates by risk level.

## Key Research Questions to Answer

1. Do users encounter the *same* error class frequently enough that automation is preferable to manual editing?
2. Is an approval gate sufficient to overcome trust concerns, or does the mere possibility of a bad patch kill adoption?
3. Would users accept autonomous edits to markdown/config files but reject edits to executable Python code?
4. Does the proposed loop actually reduce toil, or does the curation overhead remain roughly equal to manual fixing?
5. What is the recovery path when an autonomous patch breaks something? Do users trust the rollback mechanism?

---

*Phase 2 Output — Awaiting user approval before proceeding to Phase 3.*
