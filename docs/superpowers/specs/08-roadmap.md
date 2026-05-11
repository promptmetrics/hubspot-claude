# Roadmap: HubSpot Admin Agent — As-Is to MVP

**Status:** Draft  
**Date:** 2026-05-10  
**Author:** Product Manager  
**Decision needed by:** 2026-05-13

---

## 1. As-Is State: Honest Inventory

The codebase at `/src/hubspot_agent/` contains approximately **6,946 lines of Python across 40+ modules**, representing roughly 3 phases of implementation work. However, the implementation diverged sharply from the approved spec:

**What exists but does not work as a product:**
- A 1,017-line custom orchestrator that returns prompt objects instead of dispatching via Claude Code's native `Agent` tool. The skill cannot run as a Claude Code skill.
- A 931-line DAG planner that hallucinates compound-request structure with regex heuristics.
- HITL previews are generated but the execute path is not wired in `cli.py` — writes cannot actually complete.
- 13 agents implemented vs. the spec's 11 (added `custom_objects`, `service`; `marketing` and `cms` will be archived).
- 10+ subsystems built that were explicitly marked out of scope or speculative: webhooks, plugins, hooks, RBAC, sandbox, replay, anomaly detection, reflection, memory, custom routing.

**Security blockers introduced by scope creep:**
- OAuth `state` is predictable (`portal_id`), PKCE is missing, credential files are world-readable.
- Plugin sandbox is trivially bypassable via Python introspection.
- Webhook server binds to `0.0.0.0` with no rate limiting or IP allowlisting.
- Hook registry is a global singleton without portal isolation.
- `portal_id` is not validated before filesystem path construction (path traversal risk).

**Performance and reliability issues:**
- `trace.py` and `ledger.py` implement "atomic append" by reading the entire file into memory, appending one line, and writing back. At scale this is O(n) per write.
- No cost budget ceiling or token throttling exists.
- Prompt regression suite has 13 cases covering roughly 7 of 15 agents.

**What this means:** The codebase is not "almost ready." It is a feature-heavy, integration-light prototype that cannot ship in its current form. Before any release, we must prune speculative scope, fix blockers, and rebuild the dispatch layer to match the approved architecture.

---

## 2. Guiding Principles

1. **Defer architecture until you have data.** The research doc (2026-05-07) stated this explicitly. The implementation ignored it. We will not ship speculative subsystems without validated demand.
2. **Every "yes" is a "no" to something else.** Scope is not free. Each module added is a module maintained, tested, and secured.
3. **The spec is the ceiling for MVP, not the floor.** The approved spec defined 11 agents and 6 explicitly out-of-scope items. We are shipping 13 agents because custom objects and service hub have validated demand. MVP still means shipping the minimum, not more.
4. **If it doesn't work end-to-end, it doesn't count.** A DAG planner with 931 lines that hallucinates dependencies is not progress — it is negative progress because it obscures the fact that simple conjunction detection was never wired.
5. **Ship is a habit.** The fastest path to a working product is a small, working product. Momentum comes from releases, not lines of code.

---

## 3. Prioritization Framework

### MoSCoW (per phase)

| Category | Definition |
|----------|------------|
| **Must** | Blocks release. Non-negotiable. |
| **Should** | Important but can ship without it if time-constrained. |
| **Could** | Nice to have; included only if remaining capacity permits. |
| **Won't** | Explicitly out of scope for this phase. |

### RICE Scoring (for ordering within a phase)

| Factor | How we score it |
|--------|---------------|
| **Reach** | Number of requests/users affected per month |
| **Impact** | 3 = transformative, 2 = major improvement, 1 = modest, 0.5 = minor, 0.25 = negligible |
| **Confidence** | % based on evidence (interviews, analogous features, direct testing) |
| **Effort** | Person-months (S = <1 week, M = 1-2 weeks, L = 3-4 weeks) |

**RICE = (Reach x Impact x Confidence) / Effort**

---

## 4. Phase 0: Blockers — "Stop the Bleeding"

**Goal:** Fix critical failures and prune speculative scope so the codebase can ship as an MVP.  
**Time horizon:** 3-4 weeks  
**Exit criteria:** Security blockers resolved, dispatch layer rebuilt, HITL execute path works, codebase reduced to spec-aligned 11-agent scope.

### Must

| # | Initiative | Effort | Dependencies | Rationale |
|---|------------|--------|--------------|-----------|
| B1 | **Rebuild dispatch to use Claude Code native `Agent` tool** | L | None | The spec's #1 architectural mandate. A custom orchestrator that returns prompt objects is not a Claude Code skill. This is the single largest blocker to the product functioning at all. |
| B2 | **Wire HITL execute path end-to-end** | M | B1 | The spec's core safety mechanism (mandatory human-in-the-loop approval) does not work. `cli.py` generates previews but cannot capture approval or re-dispatch for execution. Without this, all writes are dead code. |
| B3 | **Remove out-of-scope agents** (marketing, CMS) | S | None | The spec explicitly limits MVP to 11 agents. Marketing and CMS agents are deferred to Phase 3 pending validated demand. Custom objects and service hub are validated and will be re-integrated in Phase 1. |
| B4 | **Remove webhook server and webhook infrastructure** | S | None | Explicitly out of scope per spec. Binds `0.0.0.0` with no rate limiting. Adds network attack surface for zero validated user value. |
| B5 | **Remove plugin architecture** | S | None | Speculative, no validated demand. The sandbox is trivially bypassable via `__import__` and `getattr`. Fixing this properly requires subprocess isolation or WASM — a Large effort for an unvalidated feature. Kill it for MVP. |
| B6 | **Replace DAG planner with spec's simple conjunction detection** | M | B1 | The 931-line DAG planner hallucinates phantom dependencies and adds brittle regex complexity. The spec's keyword + static dependency graph is sufficient for MVP and can be deterministic. |
| B7 | **Fix OAuth security vulnerabilities** | S | None | CSRF (predictable `state`), missing PKCE, world-readable credential files (`0o644`), and path traversal via unvalidated `portal_id`. These are production blockers. |
| B8 | **Remove speculative subsystems** (RBAC, hooks, sandbox, replay, anomaly detection, reflection, conversation memory) | S | None | All were rated "Speculative" or "Defer" in the research doc. All were built anyway. They add complexity, security surface area, and maintenance burden without evidence of need. Archive the code; do not ship it. |
| B9 | **Fix file I/O O(n) append in trace.py and ledger.py** | S | None | Current "atomic append" reads the entire file, modifies in memory, and renames. At 50,000 traces this is a multi-millisecond full rewrite on every operation. Replace with true append mode or per-day files. |
| B10 | **Add per-session token budget ceiling** | S | None | `trace.py` tracks estimated cost but has no circuit breaker. A runaway compound request + WebSearch loop could exceed $50-100/month with no hard stop. Add a default $1.00/session ceiling. |
| B11 | **Validate portal_id before path construction** | XS | None | Unvalidated `portal_id` interpolation enables path traversal (`../../../etc/passwd`). |

### Should

| # | Initiative | Effort | Dependencies |
|---|------------|--------|--------------|
| B12 | **Add 50-case keyword routing regression suite** | S | B6 | Keyword heuristics are deterministic and testable. 50 cases covering the 13 agents is achievable in a day. |
| B13 | **Fix hook registry portal isolation** | S | B8 (if hooks kept) | If we decide to keep hooks (not recommended), they must not be global singletons. Otherwise, this is moot. |
| B14 | **Consolidate trace/ledger/checkpoint atomic-write logic** | S | B9 | Three JSONL appenders with nearly identical read-modify-write logic. Extract one helper. |

### Won't (Phase 0)

- No new agents.
- No new UX features (tour mode, conversation memory, interactive plan modification).
- No marketing/service/CMS/domain expansion of any kind.

---

## 5. Phase 1: True MVP

**Goal:** Ship the approved spec as a working Claude Code skill.  
**Time horizon:** 4-6 weeks  
**Entry criteria:** Phase 0 exit criteria met.  
**Exit criteria:** A user can complete the full HITL flow for reads, creates, updates, and destructive operations across all 13 agents without hitting spec deviations or security warnings.

### Must

| # | Initiative | Effort | Dependencies | Rationale |
|---|------------|--------|--------------|-----------|
| M1 | **Re-integrate 13 core agents into native Agent dispatch** | M | B1, B3 | The agent tool implementations (Objects, Properties, Workflows, Lists, Pipelines, Users, Hygiene, Analytics, Associations, Engagements, RawAPI, CustomObjects, Service) are largely reusable. The work is re-wiring them into the native dispatch flow and ensuring each has a focused tool subset + domain prompt. |
| M2 | **Keyword heuristics routing (spec §5)** | S | B6 | Disable LLM routing for MVP. The spec mandates keyword heuristics. They are deterministic, testable, and fast. LLM routing requires a 100+ case regression corpus before it is safer than keyword matching. |
| M3 | **Simple conjunction detection for compound requests** | S | B6 | Spec §5: "and then"/"after that" triggers sequential dispatch; "and" linking distinct domains triggers dependency-order dispatch. No DAG construction, no topological sort, no interactive plan modification. |
| M4 | **Read-based previews + inline diff viewer** | S | B2, M1 | The diff viewer is already built and is high user value. Integrate it into the HITL preview flow for updates. |
| M5 | **Destructive gate (count-based confirmation)** | S | B2 | Spec §9: delete/merge/archive requires user to type exact count of affected records. Wire this into the execute path. |
| M6 | **Action ledger integration** | S | B1, M1 | Already built. Ensure it logs every approved write with payload hash for idempotency. |
| M7 | **Mid-execution checkpointing for bulk ops** | S | B1, M1 | Already built. Ensure checkpoint files resume correctly in the native dispatch flow. |
| M8 | **Schema-aware pre-validation** | S | M1 | Already built. Validates property names and types against cached schema before API calls. Saves rate limit budget. |
| M9 | **Error category taxonomy + agent self-correction prompts** | XS | M1 | Already built. Map status codes to `ErrorCategory` enum and include category-specific guidance in each agent's system prompt. |
| M10 | **Capability matrix probe-on-first-use** | S | M1 | Already built. Probe portal tier and feature flags on setup, cache results, gate routing. |
| M11 | **Guided setup wizard + capability report** | S | M10 | Already built. Ensure it works end-to-end with native dispatch and presents a clean "what works / what's missing" readout. |
| M12 | **Audit logging** | XS | B1 | Every approved write to `.claude/hubspot/<portal_id>/audit.log`. Already present; verify atomic append. |
| M13 | **Snapshot pruning + TTL** | S | M6, M7 | Already built. Ensure undo snapshots, traces, and checkpoints are pruned on schedule. |
| M14 | **Rate limit handling in HubSpotClient** | XS | M1 | Reuse from `agent2` project. Verify semaphore and retry logic work under native dispatch. |
| M15 | **End-to-end HITL flow tests** | M | B2, M1 | Simulate approval/rejection/details paths for each risk tier. Verify proposed payload matches executed payload exactly. |

### Should

| # | Initiative | Effort | Dependencies |
|---|------------|--------|--------------|
| S1 | **Progress streaming for bulk ops** | S | M1, B2 | Already built. Integrate into native dispatch so users see chunk progress during long operations. |
| S2 | **Batch approval mode (batch only, disable pattern)** | S | B2 | `default` = per-write approval; `batch` = one approval for the whole plan. Pattern mode is speculative and risky; defer. |
| S3 | **3 workflow blueprints** | M | M1 | The blueprint library is already started. Limit to 3 well-tested blueprints covering the most common requests (e.g., renewal alert, lead routing, lifecycle handoff). Each needs integration tests against a dev portal. |
| S4 | **Background schema cache warm** | S | M1 | Already built. Kick off on portal switch so next request hits warm cache. |
| S5 | **PII redaction in traces/logs** | S | M1 | Conditional on compliance needs. Default to `off` for solo use; enable `pii` level if needed. |

### Could

| # | Initiative | Effort | Dependencies |
|---|------------|--------|--------------|
| C1 | **Tour mode** | S | M11 | 5-7 guided examples. Only if we expect users beyond the immediate builder. |
| C2 | **Property-based testing for tools** | S | M1 | `hypothesis` tests for tool invariants. Dev-only, does not affect production code. |

### Won't (Phase 1)

- LLM routing (disable; keyword heuristics are sufficient for MVP).
- Pattern approval mode (too risky without more validation).
- DAG planner / interactive plan modification / compound request DAGs.
- Marketing, CMS agents.
- Webhooks, plugins, hooks, RBAC, sandbox, replay, anomaly detection, reflection, memory.
- Query-result cache (spec did not require it; schema cache is sufficient).
- Parallel sub-agent execution (adds HITL coordination complexity; serial is fine for MVP).

---

## 6. Phase 2: Hardening & Intelligence

**Goal:** Make the MVP robust, observable, and pleasant to use. Add intelligence layers only when data proves they are needed.  
**Time horizon:** 2-3 months after MVP GA  
**Entry criteria (ALL must be true):**
1. MVP has been live for **30+ days**.
2. **100+ unique requests** have been handled across at least 2 distinct portals.
3. **Keyword routing misprediction rate > 10%** (measured via trace analysis or user override feedback). If mispredictions are < 5%, skip LLM routing — keyword heuristics are good enough.
4. **Error rate from tool calls < 5%** (signals foundation is stable enough to add complexity).
5. **No critical security or reliability incidents** in the prior 30 days.

If these criteria are not met, **extend Phase 1** and fix the underlying problems before adding features.

### Must

| # | Initiative | Effort | Dependencies | Rationale |
|---|------------|--------|--------------|-----------|
| H1 | **LLM routing (re-enable + expand regression suite)** | M | M2 | Only if entry criterion #3 is met. Requires 100+ case regression corpus before production. Fast-path heuristics for top 5 request types remain to control token cost. |
| H2 | **Expand prompt regression suite to 100+ cases** | M | H1 | Non-negotiable prerequisite for LLM routing. Temperature=0, tolerate small variations. |
| H3 | **Self-correction loop enhancements** | S | M9, H1 | Give agents explicit error-handling guidance per category. Any self-correction that changes the proposed payload re-enters HITL preview. |
| H4 | **Cost & latency dashboards** | S | M1 | Surface `/hubspot status` and `/hubspot budget`. Already instrumented in `trace.py`; build the viewer. |

### Should

| # | Initiative | Effort | Dependencies |
|---|------------|--------|--------------|
| H5 | **Workflow blueprints expansion** (5-8 total) | M each | S3 | Add blueprints only for patterns observed in Phase 1 traces. |
| H6 | **Query-result cache (5-min TTL)** | S | M1 | Only if Phase 1 traces show repeated identical read queries. |
| H7 | **Parallel read-only sub-agent execution** | S | M1 | Only for independent read requests. Never parallelize writes — HITL coordination is not worth the complexity. |
| H8 | **Replace file-based trace/ledger with SQLite** | M | M6, M9 | Only if Phase 1 volume shows O(n) append is a real bottleneck. SQLite with WAL is safer and faster. |

### Could

| # | Initiative | Effort | Dependencies |
|---|------------|--------|--------------|
| H9 | **Tour mode** | S | M11 | If onboarding friction is observed in Phase 1. |
| H10 | **Chaos testing harness** | M | M1 | Inject faults (5% rate limits, 1% network errors) in CI. Only if we have bandwidth. |

### Won't (Phase 2)

- DAG planner / interactive plan modification (still speculative; need data on compound request frequency).
- Marketing / CMS (no expansion until Phase 3 criteria).
- Webhooks / plugins / hooks / RBAC / sandbox / replay / anomaly / reflection / memory.

---

## 7. Phase 3: Domain Expansion

**Goal:** Grow into adjacent HubSpot domains and advanced features **only where validated demand exists.**  
**Time horizon:** 6+ months after MVP  
**Entry criteria (ALL must be true):**
1. Phase 2 complete and stable for **60+ days**.
2. **500+ unique requests** handled.
3. Clear signal from **user interviews, support tickets, or trace analysis** requesting a specific domain:
   - Marketing: ≥ 3 distinct users requesting campaign/email tools.
   - CMS: ≥ 3 distinct users requesting CMS admin.
4. **Compound requests represent > 20% of traffic** (triggers DAG planner consideration).
5. A **design partner** has committed to co-develop and test the expansion.

If entry criteria are not met for a specific domain, **that domain stays in Later**. We do not build on speculation.

### Expansion Backlog (ordered by RICE, contingent on demand signal)

| # | Initiative | Effort | Demand Signal Required | Rationale |
|---|------------|--------|------------------------|-----------|
| E1 | **Custom objects agent** | — | *Already shipped in Phase 1* | Re-classified from expansion to core after validated demand. |
| E2 | **Service hub agent** | — | *Already shipped in Phase 1* | Re-classified from expansion to core after validated demand. |
| E3 | **Webhooks (event subscriptions)** | L | ≥ 5 users requesting real-time sync or reactive automation | Large effort: long-running listener, transport layer, security boundary. Needs its own design doc. |
| E4 | **DAG planner v2** | L | Criterion #4 (compound requests) | Rebuild only if compound requests are frequent AND the simple conjunction detection is clearly insufficient. Must be paired with explicit user confirmation of inferred steps. |
| E5 | **Sandbox preview** | M | ≥ 3 users confirm they have a HubSpot sandbox portal | High effort due to schema drift risk between sandbox and prod. |
| E6 | **Marketing agent** | L | Criterion #3 (marketing) | Large API surface (emails, campaigns, A/B testing, deliverability). Heavy domain knowledge. |
| E7 | **CMS agent** | L | Criterion #3 (CMS) | Separate API surface. Likely the lowest priority unless users explicitly use HubSpot as a content platform. |
| E8 | **Conversation memory** | M | Long sessions (> 20 turns) observed in traces | Only if chat history truncation is a real problem. Summaries are lossy; keep raw transcripts as source of truth. |
| E9 | **Anomaly detection** | M | 3+ months of trace data | Baselines require statistical significance. Current implementation measures user think time as "duration." Rebuild from scratch with proper metrics. |
| E10 | **Replay tooling** | M | Enough volume to justify regression corpus | Only valuable if we have historical request traces to replay against mock clients. |
| E11 | **Plugin architecture v2** | L | ≥ 5 users requesting custom tool support | Must use subprocess isolation or WASM. The current implementation is unfixable. |
| E12 | **Hooks system** | M | ≥ 3 users requesting Slack notifications or external SIEM mirroring | Must be per-portal, not global singleton. |
| E13 | **RBAC** | M | Multi-user deployment validated | Only if the tool moves from solo to team use. Requires authentication layer first. |

---

## 8. What We're NOT Building (and Why)

Saying no publicly prevents repeated requests and builds trust.

| Feature | Status | Reason | Revisit Condition |
|---------|--------|--------|-------------------|
| Plugin architecture | **Kill for MVP** | No validated demand + trivially bypassable sandbox. A secure version requires Large effort. | ≥ 5 users request custom tools AND commit to testing a v2. |
| Webhook server | **Kill for MVP** | Explicitly out of scope per spec. Adds network attack surface. | ≥ 5 users request real-time reactive automation. |
| RBAC | **Kill for MVP** | Built for multi-user but there's no auth layer or multi-user story validated. | Tool is explicitly deployed in a team setting. |
| Hooks | **Kill for MVP** | Speculative. No use cases validated. | ≥ 3 users request external notifications or custom approval policies. |
| Sandbox preview | **Kill for MVP** | Speculative. Requires second portal; no user research on sandbox availability. | ≥ 3 users confirm sandbox portal access AND request the feature. |
| Replay tooling | **Defer indefinitely** | Contingent on volume. No regression corpus exists. | 3+ months of trace data AND a prompt regression failure in production. |
| Anomaly detection | **Defer indefinitely** | Baselines are semantically meaningless without months of data. | 3+ months of clean trace data with proper latency metrics. |
| Conversation memory | **Defer indefinitely** | Chat history is sufficient for typical short sessions. | Evidence that long sessions (> 20 turns) are common AND chat truncation causes failure. |
| Custom routing rules | **Defer indefinitely** | Multi-tenant vocabulary override. No multi-tenant story. | Multi-portal agency use case is validated. |
| Batch coalescing | **Defer indefinitely** | Premature optimization. Simple batch tools already exist. | Trace data shows many small serial writes that could be coalesced. |
| Pattern approval mode | **Kill for MVP** | Auto-executes after 3-sample approval. High risk if the "rest" diverges. | Never, unless replaced with statistical confidence checks. |
| Reflection / post-action review | **Kill for MVP** | Adds latency to every write. Verify high-risk ops only (workflows, association schema). | High-risk operation failure rate justifies the overhead. |
| Marketing agent | **Kill for MVP** | Separate API surface, no validated demand. | ≥ 3 distinct users requesting campaign/email tools. |
| CMS agent | **Kill for MVP** | Separate API surface, no validated demand. | ≥ 3 distinct users requesting CMS admin. |
| Query-result cache | **Defer to Phase 2** | Spec did not require it. Add only if repeated identical reads are observed. | Phase 2 entry criteria. |
| Parallel write execution | **Skip** | HITL coordination for interleaved previews is not worth the complexity for MVP. | Never for writes; reads only. |

---

## 9. Dependency Map

```
B1 (Native Agent dispatch)
├── B2 (HITL execute path)
│   ├── M1 (Re-integrate 13 agents)
│   │   ├── M2 (Keyword routing)
│   │   ├── M3 (Conjunction detection)
│   │   ├── M4 (Previews + diff)
│   │   ├── M5 (Destructive gate)
│   │   ├── M6 (Action ledger)
│   │   ├── M7 (Checkpointing)
│   │   ├── M8 (Schema validation)
│   │   ├── M9 (Error taxonomy)
│   │   ├── M10 (Capability probe)
│   │   │   └── M11 (Setup wizard)
│   │   ├── M12 (Audit log)
│   │   ├── M13 (Snapshot pruning)
│   │   ├── M14 (Rate limits)
│   │   ├── S1 (Progress streaming)
│   │   ├── S2 (Batch approval)
│   │   ├── S3 (Workflow blueprints)
│   │   └── S4 (Cache warm)
│   └── M15 (E2E HITL tests)
├── B6 (Replace DAG planner)
│   └── M3 (Conjunction detection)
├── B9 (Fix file I/O)
│   ├── M6 (Action ledger)
│   └── M12 (Audit log)
└── B10 (Token budget)
    └── H4 (Cost dashboards)

B7 (OAuth security)
└── M11 (Setup wizard)

B3, B4, B5, B8 (Pruning)
└── Enables M1 by reducing surface area

Phase 2 (Hardening)
└── Entry criteria: 30 days, 100+ requests, >10% routing mispredictions
    ├── H1 (LLM routing)
    │   └── H2 (100+ regression cases)
    ├── H3 (Self-correction)
    └── H5-H8 (Optimizations)

Phase 3 (Expansion)
└── Entry criteria: 60 days, 500+ requests, validated domain demand
    └── E1-E13 (Domain-specific; each gated independently)
```

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| B1 (rebuild dispatch) takes longer than 4 weeks | Medium | Critical | Time-box to 4 weeks. If not complete, pivot to making the custom orchestrator invoke `Agent` tool as a shim rather than full rewrite. |
| Removing features causes rework if demand later appears | Low | Medium | Archive deleted code in a branch (`archive/speculative-features`). Do not delete git history. Custom objects and service hub are validated and kept. |
| Keyword heuristics prove insufficient even before 100 requests | Medium | High | Keep LLM routing code archived. If mispredictions spike early, fast-track H1 in a patch release. |
| HubSpot API changes break workflow blueprints | Medium | Medium | Integration tests against dev portal for each blueprint. Monitor HubSpot API changelog. Limit to 3 blueprints in MVP to minimize drift. |
| User expects Phase C features because they exist in codebase | Medium | Medium | Communicate scope clearly in release notes. The roadmap is public. Set expectations that MVP is intentionally small. |
| Security audit finds additional issues post-Phase 0 | Medium | High | Security review gate before Phase 1 start. No exceptions. |
| Token costs exceed budget even with ceiling | Low | Medium | Default $1.00/session. Make ceiling user-configurable. Track aggregate spend via `/hubspot budget`. |
| Phase 2 entry criteria never met (low adoption) | Medium | Critical | Define pivot triggers in Section 11. If criteria aren't met by [date], evaluate kill decision. |

---

## 11. Success Metrics & Pivot Triggers

### MVP Success Metrics (Phase 1)

| Metric | Current Baseline | Target | Measurement Window |
|--------|-----------------|--------|--------------------|
| End-to-end HITL write completion rate | 0% (execute path unwired) | 95% | 30 days post-MVP |
| Keyword routing accuracy | Unknown | > 90% | 30 days post-MVP |
| Setup wizard completion rate | Unknown | > 70% | 30 days post-MVP |
| Error rate (tool calls) | Unknown | < 5% | 30 days post-MVP |
| Time to first successful read request | Unknown | < 60 seconds after setup | 30 days post-MVP |
| Time to first successful write (with HITL) | Unknown | < 3 minutes after setup | 30 days post-MVP |
| Security audit findings | 12 blockers | 0 blockers, ≤ 3 warnings | Before GA |

### Pivot Triggers

**If any of the following are true 60 days after MVP launch, stop feature development and reassess:**

1. **Fewer than 50 total requests** have been issued across all users/portals.
   - *Interpretation:* There is no product-market fit for the natural-language interface. Evaluate whether the problem is discovery, onboarding, or value proposition.
2. **HITL approval rate < 50%** (users see previews but reject or abandon more than half the time).
   - *Interpretation:* Previews are not trustworthy or the agent is proposing the wrong changes. Investigate preview quality and routing accuracy.
3. **Keyword routing accuracy < 70%** after 100 requests.
   - *Interpretation:* The heuristic model is fundamentally insufficient for the user vocabulary. Fast-track LLM routing (H1) OR conclude that natural language routing is not viable and pivot to a command-based interface.
4. **A critical security incident** occurs (credential leak, unauthorized portal access, path traversal exploit).
   - *Interpretation:* Freeze all feature work. Full security audit and incident response.
5. **Monthly token cost per active user exceeds $20** with the $1.00/session ceiling in place.
   - *Interpretation:* The economics do not work. Evaluate cost-reduction measures (cheaper models, shorter prompts) or conclude the product is not viable at current pricing.

---

## 12. Recommended Immediate Actions (This Week)

1. **Decision meeting with stakeholders:** Approve Option B (prune to spec) vs. Option A (rewrite spec to match implementation). **Recommendation: Option B.**
2. **Freeze all new feature development.** No commits adding modules, agents, or subsystems until Phase 0 is complete.
3. **Create `archive/speculative-features` branch.** Move plugins, webhooks, RBAC, hooks, sandbox, replay, anomaly, reflection, memory, custom routing, and marketing/CMS agents to this branch. Keep them out of `main`. Custom objects and service hub agents stay in `main` for Phase 1 re-integration.
4. **Ticket B1 and B2** for engineering estimation and assignment. These are the critical path for everything else.
5. **Schedule security review** for end of Phase 0. Block Phase 1 start on 0 blockers.

---

## Appendix A: RICE Score Detail (Phase 0 + Phase 1 Must-Have)

| Initiative | Reach | Impact | Confidence | Effort | RICE Score |
|------------|-------|--------|------------|--------|------------|
| B1 Native Agent dispatch | 100% of users | 3 | 90% | L (4) | **67.5** |
| B2 HITL execute path | 100% of write ops | 3 | 95% | M (2) | **142.5** |
| B3 Prune out-of-scope agents | 100% of users | 2 | 100% | S (1) | **200** |
| B4 Remove webhooks | 100% of users | 2 | 100% | S (1) | **200** |
| B5 Remove plugins | 100% of users | 2 | 100% | S (1) | **200** |
| B6 Replace DAG planner | 100% of compound requests | 2 | 90% | M (2) | **90** |
| B7 Fix OAuth security | 100% of auth flows | 3 | 100% | S (1) | **300** |
| B8 Remove speculative subsystems | 100% of users | 2 | 100% | S (1) | **200** |
| M1 Re-integrate 13 agents | 100% of requests | 3 | 80% | M (2) | **120** |
| M2 Keyword routing | 100% of requests | 2 | 95% | S (1) | **190** |
| M4 Previews + diff | 100% of updates | 2 | 90% | S (1) | **180** |
| M5 Destructive gate | 100% of deletes | 3 | 95% | S (1) | **285** |
| M15 E2E HITL tests | Future reliability | 2 | 100% | M (2) | **100** |

*Effort scale: S = 1 person-week, M = 2 person-weeks, L = 4 person-weeks.*

---

## Appendix B: MoSCoW Summary by Phase

| Phase | Must | Should | Could | Won't |
|-------|------|--------|-------|-------|
| Phase 0 (Blockers) | 11 | 3 | 0 | New features |
| Phase 1 (MVP) | 17 | 5 | 2 | LLM routing, pattern mode, DAG planner, marketing/CMS agents |
| Phase 2 (Hardening) | 4 | 4 | 2 | Domain expansion, webhooks, plugins, RBAC |
| Phase 3 (Expansion) | 0 | 0 | 13 (gated) | Anything without validated demand signal |
