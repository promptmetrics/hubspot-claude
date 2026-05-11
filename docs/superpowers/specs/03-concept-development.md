# Concept Development: HubSpot Admin Agent

**Date:** 2026-05-10
**Status:** As-built documentation
**Companion docs:** [Concept Brief](01-concept-brief.md) · [PRD](05-prd.md) · [Technical Spec](06-technical-spec.md)

---

## 1. User Personas

### Primary: RevOps Manager (Alex)
- **Role:** Manages HubSpot instance for a 50-200 person company
- **Technical level:** Comfortable with CLI, basic Python, understands CRM concepts
- **Goals:** Keep data clean, automate workflows, onboard users, generate reports
- **Pain points:** HubSpot UI is slow for bulk ops, property management is tedious, no undo for mistakes
- **Frequency:** Uses HubSpot daily for 30-60 min of admin work

### Secondary: Technical Founder (Jordan)
- **Role:** Early-stage startup, wears multiple hats including CRM admin
- **Technical level:** Engineer, lives in terminal/IDE
- **Goals:** Quick setup, minimal configuration, get CRM operational fast
- **Pain points:** Doesn't want to learn HubSpot's UI paradigms, needs to script bulk imports
- **Frequency:** Sporadic bursts of CRM admin (setup, then occasional cleanup)

### Tertiary: Sales Ops Lead (Taylor)
- **Role:** Manages pipeline hygiene, user assignments, deal tracking
- **Technical level:** Power user of HubSpot UI, not a programmer
- **Goals:** Pipeline cleanliness, accurate reporting, user onboarding
- **Pain points:** Duplicate records, stale pipeline stages, missing property values
- **Frequency:** Weekly data hygiene sessions

## 2. Jobs-to-be-Done

### JTBD 1: "Find and clean up messy data"
- **Current state:** Exports to Excel, manipulates, re-imports
- **Desired state:** Natural language request like "find duplicate contacts and merge them"
- **Frequency:** Weekly
- **Agents:** HygieneAgent, ObjectsAgent

### JTBD 2: "Set up automation without learning workflow builder"
- **Current state:** Clicks through HubSpot workflow UI, tests manually
- **Desired state:** "Build a workflow that alerts the deal owner 30 days before renewal"
- **Frequency:** Monthly
- **Agents:** WorkflowsAgent, PropertiesAgent

### JTBD 3: "Bulk update records safely"
- **Current state:** Exports list, updates in spreadsheet, re-imports with risk of overwriting
- **Desired state:** "Update all contacts where region is west, set timezone to PST" with preview and approval
- **Frequency:** Weekly
- **Agents:** ObjectsAgent, HygieneAgent

### JTBD 4: "Get quick answers about CRM state"
- **Current state:** Builds reports in HubSpot or asks a colleague
- **Desired state:** "How many deals closed last month" with instant answer
- **Frequency:** Daily
- **Agents:** AnalyticsAgent, ObjectsAgent

### JTBD 5: "Onboard a new team member"
- **Current state:** Manual user creation, role assignment, team addition in HubSpot settings
- **Desired state:** "Onboard dana@example.com as a sales rep" with automated provisioning
- **Frequency:** Monthly
- **Agents:** UsersAgent

## 3. User Journeys

### Journey 1: First-Time Setup (Private App Token)

```
Awareness: User learns about /hubspot skill from documentation or colleague
Consideration: Checks if their portal has API access
Adoption:
  1. Runs /hubspot setup <portal_id> token <pat>
  2. Sees capability report (what works, what's missing)
  3. Runs /hubspot status to verify connection
  4. Runs /hubspot tour for walkthrough
Retention:
  - Uses /hubspot for daily queries
  - Builds confidence with read-only operations first
  - Gradually uses write operations with approval gates
```

**Friction points:**
- Creating Private App requires navigating HubSpot Settings (non-obvious path)
- Selecting correct scopes is error-prone
- OAuth path is even more complex (developer app creation)
- Tour is blocked until portal is configured

### Journey 2: Daily Read Query

```
1. User: /hubspot show me deals closing this quarter
2. System: routes to AnalyticsAgent
3. Agent: fetches report data via hubspot_get_analytics_report
4. System: presents markdown table with results
5. User: follow-up query or new request
```

**Delight:** Instant answer without navigating HubSpot reports UI.

### Journey 3: Write with Approval

```
1. User: /hubspot update contact 12345, set lifecyclestage to customer
2. System: routes to ObjectsAgent
3. Agent (preview mode): fetches current values, builds diff
4. System: presents inline diff + "Approve? (y/n/details)"
5. User: y
6. System: saves undo snapshot, dispatches execute mode
7. Agent (execute mode): sends PATCH to HubSpot API
8. System: presents success + undo option
```

**Friction points (as built):**
- The execute path is not fully wired in cli.py (blocker-level gap)
- User may not see the preview or be able to approve

### Journey 4: Bulk Update with Checkpointing

```
1. User: /hubspot update all contacts where region is west, set timezone to PST
2. System: routes to ObjectsAgent + HygieneAgent
3. Agent: searches matching contacts (e.g., 1,247 records)
4. System: presents plan preview (affected count, before/after samples)
5. User: approve
6. System: checkpoints to in_flight/<action_id>.jsonl
7. Agent: chunks into 100-record batches
8. System: emits progress per chunk
9. Completion: moves checkpoint to completed/
```

**Delight:** Safe bulk ops with progress visibility and resumability.

### Journey 5: Compound Request with DAG

```
1. User: /hubspot create a renewal date property, build a workflow that uses it, and add affected contacts to a list
2. System: DAGPlanner detects compound request
3. Plan:
   - Node 1: PropertiesAgent (create property)
   - Node 2: WorkflowsAgent (create workflow, depends on N1)
   - Node 3: ListsAgent (create list, depends on N1)
4. System: presents DAG table for approval
5. User: approve (or "skip n3" / "edit n2")
6. System: executes topologically, passing outputs between nodes
7. Results: synthesized summary
```

**Friction points:**
- DAG planner can hallucinate dependencies (phantom nodes)
- Interactive modification regex is brittle
- Over-engineered for MVP

## 4. Technical Concept

### Architecture (As Built)

```
User (Claude Code session)
    |
    v
/hubspot <request>
    |
    v
cli.py — portal detection, auth, command parsing
    |
    v
orchestrator.py — routing, validation, HITL, dispatch
    |
    +---> DAGPlanner (for compound requests)
    |         |
    |         v
    |    Plan nodes with dependencies
    |
    +---> Fast-path keyword routing
    |         |
    |         v
    |    Single agent dispatch
    |
    +---> LLM fallback routing (if fast-path ambiguous)
    |
    +---> Scope/capability validation
    |
    +---> HITL approval flow (preview → approval → execute)
    |
    v
Agent (15 specialist agents)
    |
    v
Tools (async Python functions with @tool decorator)
    |
    v
HubSpotClient (async httpx with rate limiting, retry)
    |
    v
HubSpot API (CRM v3, Automation v4, etc.)
    |
    v
Disk state (~/.claude/hubspot/<portal_id>/)
    +-- Schema cache, query cache, capabilities
    +-- Action ledger, checkpoints, snapshots
    +-- Traces, audit log, session memory
    +-- Roles, hooks, routing overrides
```

### Data Flow

1. **Request received** — natural language via `/hubspot` command
2. **Portal resolution** — `.hubspot-portal` file or explicit `--portal`
3. **Auth check** — token validity, refresh if needed
4. **Routing** — fast-path keywords or LLM fallback
5. **Validation** — scope check, capability probe, role check
6. **Planning** — simple dispatch or DAG construction
7. **Execution** — agent runs tools, returns results
8. **Observability** — traces, ledger, audit written

### AI/ML Components

- **Intent routing:** Keyword heuristics + LLM fallback (non-deterministic)
- **Self-correction:** Agent prompts include error-handling guidance keyed by ErrorCategory
- **Schema validation:** Fuzzy property name matching (difflib.get_close_matches)
- **DAG planning:** Regex-based compound request segmentation and dependency inference
- **Reflection:** Post-write verification by re-fetching and comparing

### Technical Risks

1. **Custom orchestrator cannot run as Claude Code skill** — the spec mandated native `Agent` tool usage
2. **DAG planner hallucination risk** — regex-based NLP can misclassify requests
3. **LLM routing cost** — no budget ceiling, unlimited WebSearch calls
4. **File I/O bottlenecks** — O(n) append on every trace/ledger write
5. **Plugin security** — trivially bypassable sandbox

## 5. AI Feasibility Assessment

### What's Working
- Keyword routing is fast and deterministic for common requests
- Schema-aware validation catches typos before API calls
- Error taxonomy enables structured self-correction
- Workflow blueprints parameterize common patterns

### What's Risky
- LLM fallback routing has no measured accuracy (no false positive/negative rates)
- DAG planner's regex heuristics are brittle against natural language variation
- Reflection normalization can mask real mismatches
- No prompt versioning or regression isolation

### Cost Implications
- Fast-path routing: ~0 tokens (free)
- LLM fallback routing: ~500-1000 tokens per request
- Sub-agent dispatch: ~2000-5000 tokens per agent
- WebSearch research: ~1000-3000 tokens per search
- Compound requests with DAG: 2-3x multiplier
- **No budget ceiling exists.** A power user could rack up $50-100/month.

## 6. Refined Solution Narrative

The HubSpot Admin Agent is a CLI-first natural language interface for HubSpot CRM administration. It reduces the time and expertise required for routine admin tasks by:

1. **Understanding intent** via keyword heuristics and LLM routing
2. **Validating safety** via schema-aware pre-checks and scope validation
3. **Preventing accidents** via mandatory HITL approval with previews and destructive count gates
4. **Enabling bulk operations** with checkpointing, progress streaming, and undo
5. **Extending functionality** via plugins and hooks for power users

**Current reality:** The core value proposition is sound, but the implementation over-engineered the orchestration layer, shipped 4 extra agents and 10+ speculative subsystems without validation, and left the critical HITL execute path unwired.
