# HubSpot Agent User Manual

A Claude Code skill that lets you administer HubSpot CRM with natural language. Create records, update pipelines, build workflows, run analytics, and keep your data clean — all with mandatory human-in-the-loop approval for every write.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Security & Credential Storage](#security--credential-storage)
3. [Feature Tour by Example](#feature-tour-by-example)
4. [Advanced Features](#advanced-features)
5. [Troubleshooting](#troubleshooting)
6. [Reference](#reference)

---

## Quick Start

### Choose Your Authentication Method

The HubSpot Agent supports two ways to connect. Pick the one that matches your situation.


| Method                | Best For                           | Needs Developer App?                                      | Token Lifespan            |
| --------------------- | ---------------------------------- | --------------------------------------------------------- | ------------------------- |
| **Private App Token** | Personal use, single user, scripts | No                                                        | Never expires             |
| **OAuth 2.0**         | Teams, shared access, multi-user   | Yes — create a public app in the HubSpot developer portal | ~6 hours (auto-refreshed) |


---

### Option A: Private App Token (Fastest)

Use this if you want to get moving in under five minutes.

**Step 1 — Create the token in HubSpot**

1. Log into your HubSpot portal.
2. Go to **Settings > Integrations > Private Apps**.
3. Click **Create private app**.
4. Give it a name (for example, `Claude Code Agent`).
5. On the **Scopes** tab, grant the scopes you need. At minimum:
  - `crm.objects.contacts.read`, `crm.objects.contacts.write`
  - `crm.objects.companies.read`, `crm.objects.companies.write`
  - `crm.objects.deals.read`, `crm.objects.deals.write`
  - `crm.schemas.deals.read`, `crm.schemas.contacts.read`
  - `automation` (for workflows)
6. Click **Create app**, then copy the token. It starts with `pat-na1-`.

**Step 2 — Save the token in Claude Code**

```
/hubspot setup <portal_id> token <pat>
```

Replace `<portal_id>` with your HubSpot portal ID (found in your HubSpot account settings) and `<pat>` with the token you copied.

**Step 3 — Verify**

```
/hubspot status
```

You should see connection health and the last 24 hours of activity.

---

### Option B: OAuth 2.0 (Team Setup)

Use this when multiple people need to use the same integration, or when your security policy requires refreshable tokens.

**Step 1 — Create a HubSpot Developer Public App**

1. Go to [https://developers.hubspot.com](https://developers.hubspot.com) and log in.
2. Create a new app. Note the **App ID**, **Client ID**, and **Client Secret**.
3. Set the redirect URL to `http://localhost:3000/oauth/callback`.
4. Request the scopes your team needs (the same list shown in the Private App section above).

**Step 2 — Save app credentials in Claude Code**

Run this Python snippet inside Claude Code (or in a Python shell in the project):

```python
from hubspot_agent.app_credentials import save_app_credentials
save_app_credentials(
    client_id='your-client-id',
    client_secret='your-client-secret',
    app_id='your-app-id'
)
```

These are stored separately from portal tokens at `~/.claude/hubspot/app_credentials.json`.

**Step 3 — Run the OAuth flow**

```
/hubspot setup <portal_id> oauth
```

This opens your browser, asks you to log into HubSpot, and authorizes the app. The redirect lands back at `http://localhost:3000/oauth/callback`. The skill stores the access token and refresh token automatically.

**Step 4 — Verify**

```
/hubspot status
```

---

### Portal Auto-Detection

Tired of typing your portal ID? Create a `.hubspot-portal` file in your working directory with just the portal ID inside:

```bash
echo "1234567" > .hubspot-portal
```

From then on, `/hubspot` commands default to that portal unless you override them.

---

### Switching Portals

```
/hubspot portal switch <portal_id>
```

List all configured portals:

```
/hubspot portal list
```

---

## Security & Credential Storage

### Where Tokens Live

Credentials are stored in JSON files under your home directory:

```
~/.claude/hubspot/
  <portal_id>.json          # Auth config (token or OAuth pair)
```

Old `.token` plain-text files are automatically migrated into the JSON format and then deleted.

### Token Redaction

Tokens are **never** logged, printed in output, or returned in error messages. If you ever see a token in a log file, report it as a bug.

### PII Handling

Emails, phone numbers, and full names are redacted in internal logs and traces via an active redaction layer. The skill still sends the real data to HubSpot's API, but what lands on your local disk is scrubbed.

### Audit Trail

Every approved write operation is appended to:

```
~/.claude/hubspot/<portal_id>/audit.log
```

This is a plain-text, append-only log you can grep, tail, or ship to your SIEM.

### Action Ledger

An idempotency ledger lives at:

```
~/.claude/hubspot/<portal_id>/action_log.jsonl
```

It records the intent hash and result of every mutating operation so the agent can detect duplicates and support safe retries.

---

## Feature Tour by Example

The following commands are copy-pasteable. They are organized by the agent that handles them. All write operations will ask for your approval before touching live data.

### Objects Agent — Contacts, Companies, Deals, Tickets, Products, Quotes

**Find records**

```
/hubspot find all contacts in the northeast
/hubspot show me deals closing this quarter
/hubspot get the last 10 companies created
```

**Create a record**

```
/hubspot create a contact named Dana Smith with email dana@example.com
/hubspot create a deal called "Acme Renewal" worth $50,000
```

You will see a preview of the payload and be asked to confirm with `y`.

**Update a single record**

```
/hubspot update contact 12345, set lifecyclestage to customer
```

You will see an inline diff (old vs new values) before the change is sent.

**Bulk update**

```
/hubspot update all contacts where region is west, set timezone to PST
```

Because this touches more than 10 records, the agent renders a full plan preview: affected count, before/after samples, and the API calls it intends to make. You confirm once for the entire batch.

**Delete**

```
/hubspot delete contact 12345
```

Destructive operations show the exact count of affected records and ask you to type that number to proceed.

---

### Properties Agent — Custom Fields

```
/hubspot create a custom deal property called "Renewal Date" of type date
/hubspot create a contact property called "NPS Score" of type number
/hubspot update property group "dealinformation" to add description "Core deal fields"
```

The agent validates property types, checks for naming collisions, and shows you the full schema before creating anything.

---

### Workflows Agent — Automation

```
/hubspot build a workflow that alerts the deal owner 30 days before renewal date
/hubspot create a welcome email workflow for new contacts
/hubspot enable the workflow named "Lead Nurture - Week 1"
/hubspot disable the workflow "Old Offboarding Sequence"
```

Workflows are built from blueprints stored in the skill's `blueprints/workflows/` directory. The agent maps your natural language request to the closest blueprint, then customizes enrollment triggers and actions.

---

### Lists Agent — Static and Dynamic

```
/hubspot create a dynamic list of contacts with lifecyclestage = customer
/hubspot add contact 12345 to the list "VIP Customers"
/hubspot remove contact 67890 from "Newsletter Subscribers"
/hubspot show me the members of list "Q2 Targets"
```

---

### Pipelines Agent — Deal and Ticket Stages

```
/hubspot get pipeline stages for deals
/hubspot create a new deal pipeline called "Enterprise Sales"
/hubspot rename stage "appointmentscheduled" to "Discovery Call"
/hubspot reorder deal stages to: Discovery, Demo, Negotiation, Closed Won, Closed Lost
```

---

### Users Agent — Teams and Permissions

```
/hubspot onboard a new user dana@example.com as a sales rep
/hubspot assign the role super_admin to user 98765
/hubspot deactivate user 54321
/hubspot show me the team "Inbound Sales"
```

---

### Hygiene Agent — Deduplication and Cleanup

```
/hubspot find duplicate contacts with the same email
/hubspot merge duplicate contacts with same email
/hubspot standardize all phone numbers to E.164 format
/hubspot bulk update contacts where industry is blank, set industry to "Unknown"
/hubspot preview the segment of deals with no close date
```

Merge and bulk update are destructive. The agent shows a preview segment first, then asks for explicit confirmation.

---

### Analytics Agent — Reports and Metrics

```
/hubspot how many deals closed last month
/hubspot show me pipeline velocity for Q2
/hubspot calculate conversion rate from lead to customer this quarter
/hubspot fetch the report named "Monthly Revenue"
```

Read-only. No approval required.

---

### Associations Agent — Linking Records

```
/hubspot associate contact 12345 with company 67890
/hubspot disassociate deal 11111 from contact 12345
/hubspot show association types between contacts and deals
/hubspot create an association between ticket 55555 and contact 12345 with type "support"
```

---

### Engagements Agent — Notes, Tasks, Calls, Meetings

```
/hubspot create a note on contact 12345: "Spoke on the phone, interested in Enterprise plan"
/hubspot create a task for deal owner of deal 11111: "Send contract by Friday"
/hubspot log a call to contact 12345 lasting 15 minutes
/hubspot schedule a meeting with contact 12345 next Tuesday at 2pm
```

---

### Custom Objects Agent

```
/hubspot list custom object schemas
/hubspot create a custom object called "Fleet Vehicle" with fields VIN, Make, Model, Year
/hubspot find all Fleet Vehicle records where Make is Toyota
```

---

### Service Agent — Knowledge Base and Tickets

```
/hubspot create a ticket for contact 12345 with subject "Login issue" and priority high
/hubspot show open tickets in the "Technical Support" pipeline
/hubspot list knowledge base articles about billing
/hubspot create a feedback survey for resolved tickets
```

---

### Marketing Agent — Email and Campaigns

```
/hubspot create a marketing email named "June Newsletter"
/hubspot create a campaign called "Product Launch 2024"
/hubspot build a suppression list for unsubscribed contacts
/hubspot show me A/B test results for email "Welcome Sequence - Variant A"
```

---

### CMS Agent — Pages and Assets

```
/hubspot list recent blog posts
/hubspot upload file logo.png to the file manager
/hubspot publish a social media post to LinkedIn about our new feature
/hubspot show me the page "Pricing" details
```

---

### Raw API Agent — Escape Hatch

When the specialized agents do not cover an endpoint, you can call the HubSpot API directly:

```
/hubspot call GET /crm/v3/objects/contacts/12345
/hubspot call PATCH /crm/v3/objects/deals/11111 with body {"properties":{"amount":60000}}
```

This still routes through the skill's client, so rate limiting and token refresh are handled automatically. Writes still require approval.

---

### Batch Mode

Append `--batch` to any bulk write to approve the entire plan up front instead of confirming every sub-step:

```
/hubspot update all contacts where region is west, set timezone to PST --batch
```

For very large batches, the agent may offer **pattern mode**: it executes a small sample, shows you the result, and then auto-runs the remainder if you approve the pattern.

---

## Advanced Features

### Plugins (Custom Tools)

Drop Python files into:

```
~/.claude/hubspot/plugins/*.py
```

Inside a plugin file, register tools with the `@tool` decorator and augment agent prompts via the `AGENT_AUGMENTATIONS` dictionary. The skill restricts builtins: `open`, `exec`, and `eval` are blocked. Only imports from the `hubspot_agent.*` namespace are allowed.

After adding a plugin, restart the Claude Code session or run `/hubspot refresh`.

---

### Webhooks

The skill can run a long-running webhook listener that reacts to HubSpot events without a user prompt.

1. Configure your HubSpot app to send subscription events to your listener URL.
2. Start the listener (internal command; check your deployment docs for the exact wrapper).
3. The listener validates the `X-HubSpot-Signature` header on every request.
4. An event routing table maps subscription types (for example, `contact.creation`, `deal.propertyChange`) to agents.

Events are written to the trace log and may trigger agent reactions automatically.

---

### Sandbox Preview

High-risk operations (bulk updates, merges, pipeline changes) offer a sandbox preview before touching production. The agent:

1. Replicates the intended change on a test workload or read-only dry-run.
2. Reports a behavior diff.
3. Only applies the change to production after you confirm the diff looks correct.

If a sandbox is not available for a specific operation, the agent falls back to the standard preview + count-based confirmation gate.

---

### Roles and RBAC

Create `~/.claude/hubspot/<portal_id>/roles.json` to restrict what individual users can do.

Example:

```json
[
  {
    "user_id": "alice@example.com",
    "allowed_agents": ["analytics", "objects"],
    "max_risk_level": "MEDIUM",
    "denied_tools": ["hubspot_delete_object"]
  },
  {
    "user_id": "bob@example.com",
    "allowed_agents": ["objects", "pipelines", "lists"],
    "max_risk_level": "HIGH",
    "denied_tools": []
  }
]
```

The skill checks every request against the user's `max_risk_level` and `denied_tools` before routing to an agent.

---

### Conversation Memory

Session summaries are persisted to:

```
~/.claude/hubspot/<portal_id>/sessions/<session_id>.json
```

When a new session starts, the skill loads the most recent summary as context to reduce prompt bloat. The summary includes which agents were used and any custom objects discovered, so follow-up sessions start with relevant context already loaded.

---

### Hooks

Hooks let you mirror events to external systems or inject custom gates.

Supported events:

- `pre_write` — fired before any mutating API call; can block the operation.
- `post_write` — fired after a successful write; useful for Slack notifications or secondary logging.
- `pre_approval` — fired before the approval prompt is shown; can auto-approve or auto-deny based on custom logic.
- `post_approval` — fired after the user responds; useful for audit mirroring.

Hook configurations are loaded from the portal config. They can call external HTTP endpoints or local shell commands.

---

### Replay Tooling

Trace files capture every request and response. You can replay them against a mock HubSpot client for regression testing.

Traces live at:

```
~/.claude/hubspot/<portal_id>/traces.jsonl
```

Replay is typically run via CI or a local test script. It verifies that a refactoring did not change the shape of API calls or the sequence of agent dispatches.

---

### DAG Planner

Complex compound requests are automatically decomposed into a JSON DAG (directed acyclic graph) with nodes, inputs, outputs, and dependencies.

For example:

```
/hubspot find unassigned deals and create follow-up tasks for each
```

The planner generates:

- Node 1: `search_deals` (filter: no owner)
- Node 2: `create_task` (depends on Node 1 outputs, one task per deal)

You can inspect the plan before execution. Interactive modifications are supported:

- `skip n3` — remove a node
- `edit n2 param priority to high` — change a parameter

The planner also coalesces serial writes to the same object type into a single batched API call when safe.

---

### Anomaly Detection

Per-portal baselines track failure rate and request duration. If a sudden spike exceeds three standard deviations — for example, a workflow enrollment API starts returning 500s at 10x the normal rate — the skill pauses and warns you before continuing. You can override the pause with an explicit confirmation.

---

### Query Cache

Read tool results are cached in an LRU cache for five minutes. If you run the same read twice in a row, the second call returns instantly. Writes automatically invalidate the affected domains, so you never see stale data after an update.

Flush the cache manually:

```
/hubspot refresh
```

---

## Troubleshooting

### No Portal Configured

**Symptom:** Every command returns `No portal configured`.

**Fix:**

1. Check if `.hubspot-portal` exists in your working directory.
2. Run `/hubspot portal list` to see configured portals.
3. If the list is empty, follow the [Quick Start](#quick-start) to authenticate.

---

### Missing Scopes

**Symptom:** A write fails with `403 Forbidden` or `Scope missing`.

**Fix:**

1. Log into HubSpot and go to your Private App or OAuth app settings.
2. Add the missing scope. Common forgotten scopes:
  - `automation` (for workflows)
  - `crm.schemas.deals.read` (for pipeline or property changes)
  - `crm.objects.owners.read` (for user/assignment operations)
3. If using OAuth, re-run `/hubspot portal auth <portal_id>` to refresh the token with the new scopes.

---

### Rate Limiting

**Symptom:** Requests start returning `429 Too Many Requests`.

**Fix:**

- The skill's client already implements exponential backoff and retry. If you still see 429s, your portal may be on a lower HubSpot tier.
- Spread bulk operations across a longer time window, or use `--batch` so the agent can coalesce writes into fewer API calls.
- Check `/hubspot status` to see recent request volume and latency.

---

### Cache Stale

**Symptom:** You updated a property or pipeline in HubSpot directly, but the agent still references the old name or old stage list.

**Fix:**

```
/hubspot refresh
```

This flushes the local schema cache and query cache. The next request fetches fresh metadata from HubSpot.

---

### Approval Prompt Does Not Appear

**Symptom:** A write ran without asking you.

**Fix:**

- Check if you are in a role with `auto_approve` enabled in `roles.json`.
- Check if a `pre_approval` hook is configured that suppresses prompts.
- If neither applies, file a bug — writes should never run silently.

---

### OAuth Token Expired and Not Auto-Refreshing

**Symptom:** Commands fail with `401 Unauthorized` even though OAuth was set up.

**Fix:**

1. Check that `client_secret` is still correct in `~/.claude/hubspot/<portal_id>.json`.
2. Re-run `/hubspot portal auth <portal_id>` to generate a new refresh token.
3. If the HubSpot app was deleted or secret rotated, recreate the app and save new credentials.

---

## Reference

### CLI Commands


| Command                                  | Description                                                                 |
| ---------------------------------------- | --------------------------------------------------------------------------- |
| `/hubspot <request>`                     | Main entry point. Routes natural language to the appropriate agent.         |
| `/hubspot setup <portal_id> oauth`       | Start OAuth credential setup for a portal.                                  |
| `/hubspot setup <portal_id> token <pat>` | Save a Private App token for a portal.                                      |
| `/hubspot portal auth <portal_id>`       | Run the OAuth browser flow for a portal.                                    |
| `/hubspot portal token <portal_id>`      | Show token setup instructions (no-op helper).                               |
| `/hubspot portal switch <portal_id>`     | Change the active portal for subsequent commands.                           |
| `/hubspot portal list`                   | List all portals with stored credentials.                                   |
| `/hubspot status`                        | Show last 24 hours of stats: requests, latency, error rate, estimated cost. |
| `/hubspot refresh`                       | Flush the schema cache and query cache.                                     |
| `/hubspot tour`                          | Run an interactive 7-step tour demonstrating reads, writes, and approvals.  |


### Disk File Reference

```
~/.claude/hubspot/
  <portal_id>.json                  # PortalConfig: auth, tier, scopes
  <portal_id>/
    schema_cache.json               # Cached object and property schemas
    audit.log                       # Append-only log of approved writes
    action_log.jsonl                # Idempotency ledger (one line per action)
    capabilities.json                 # Feature matrix for this portal
    traces.jsonl                    # Observability: requests, routing, tools, approvals
    query_cache.json                # Short-lived read cache (LRU, 5 min TTL)
    sessions/                         # Conversation summaries
      <session_id>.json
    in_flight/                        # Bulk operation checkpoints (resumable)
      <action_id>.jsonl
    completed/                        # Archived checkpoints
      <action_id>.jsonl
    undo_snapshots/                   # Rollback data for destructive operations
      <action_id>.json
    roles.json                        # RBAC rules (optional)
    routing_overrides.json            # Per-portal vocabulary aliases (optional)
  plugins/
    *.py                              # Custom tool extensions
```

### Risk Levels and Approval Gates


| Risk Level               | Trigger                       | Approval UI                                            |
| ------------------------ | ----------------------------- | ------------------------------------------------------ |
| Read-only                | Any search, get, list, report | None                                                   |
| Create                   | Any POST                      | Preview of the payload + `y` confirm                   |
| Update single            | One record                    | Inline diff (old vs new) + `y` confirm                 |
| Update bulk              | More than 10 records          | Full plan preview + explicit confirm                   |
| Delete / Merge / Archive | Any destructive operation     | Exact count gate — type the number of affected records |


### Environment Variables


| Variable                      | Purpose                                                                   |
| ----------------------------- | ------------------------------------------------------------------------- |
| `HUBSPOT_TOKEN_<portal_id>`   | Fallback Private App token if not in `~/.claude/hubspot/<portal_id>.json` |
| `HUBSPOT_OAUTH_CALLBACK_PORT` | Override the default `3000` port for the OAuth redirect listener          |


---

*Last updated: 2026-05-08*