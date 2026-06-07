# HubSpot Agent User Manual

A Claude Code skill that lets you administer HubSpot CRM with natural language. Create records, update pipelines, build workflows, run analytics, and keep your data clean — all with mandatory human-in-the-loop approval for every write.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication Methods](#authentication-methods)
3. [Portal Management](#portal-management)
4. [HITL Approval Flow](#hitl-approval-flow)
5. [Agent Examples](#agent-examples)
6. [Advanced Features](#advanced-features)
7. [Troubleshooting](#troubleshooting)
8. [Reference](#reference)

---

## Quick Start

### Step 1 — Get a Private App Token

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

### Step 2 — Save the Token

```
/hubspot setup <portal_id> token <pat>
```

Replace `<portal_id>` with your HubSpot portal ID (found in your HubSpot account settings) and `<pat>` with the token you copied.

### Step 3 — Verify

```
/hubspot status
```

You should see last 24 hours of stats: requests, latency, error rate, and estimated cost.

### Step 4 — Auto-detect Your Portal (optional)

Create a `.hubspot-portal` file in your working directory with just the portal ID inside:

```bash
echo "1234567" > .hubspot-portal
```

From then on, `/hubspot` commands default to that portal unless you override them.

---

## Authentication Methods

| Method | Best For | Needs Developer App? | Token Lifespan |
| --- | --- | --- | --- |
| **Private App Token** | Personal use, single user, scripts | No | Never expires |
| **OAuth 2.0** | Teams, shared access, multi-user | Yes — create a public app in the HubSpot developer portal | ~6 hours (auto-refreshed) |

### Private App Token

Tokens start with `pat-na1-` and never expire. Store them with:

```
/hubspot setup <portal_id> token <pat>
```

### OAuth 2.0

The skill uses PKCE (S256 code challenge, random state nonce, 10-minute expiry).

**Step 1 — Create a HubSpot Developer Public App**

1. Go to [https://developers.hubspot.com](https://developers.hubspot.com) and log in.
2. Create a new app. Note the **App ID**, **Client ID**, and **Client Secret**.
3. Set the redirect URL to `http://localhost:3000/oauth/callback`.
4. Request the scopes your team needs.

**Step 2 — Save app credentials**

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

## Portal Management

Switch the active portal for subsequent commands:

```
/hubspot portal switch <portal_id>
```

List all configured portals:

```
/hubspot portal list
```

Show token setup helper:

```
/hubspot portal token <portal_id>
```

Run OAuth browser flow for a portal:

```
/hubspot portal auth <portal_id>
```

---

## HITL Approval Flow

Every write operation requires your explicit approval. The flow works like this:

1. **Preview**: You send a write request. The agent runs in PREVIEW mode, making a read-only API call to find matching records.
2. **Storage**: The action is stored on disk at `~/.claude/hubspot/<portal_id>/pending_previews/<action_id>.json`.
3. **Review**: You see the action ID, risk level (low/medium/high/destructive), and impact count.
4. **Approve or Reject**:
   - Type `y` or `yes` to approve the last pending action.
   - Type `approve <action_id>` to approve a specific action.
   - Type `n`, `no`, or `reject` to reject the last pending action. The preview is cleared and no write occurs.
5. **Execute**: Once approved, the agent runs in execute mode and performs the write.

### Risk Levels

| Risk Level | Trigger | Approval UI |
| --- | --- | --- |
| **LOW** | Search, get, list, analytics | None — no approval needed |
| **MEDIUM** | Create, update single record | Preview payload + `y` confirm |
| **HIGH** | Bulk updates (>10 records) | Full plan preview + explicit confirm |
| **DESTRUCTIVE** | Delete | Exact count gate — type the number of affected records |

---

## Agent Examples

The following commands are organized by the agent that handles them. All write operations ask for your approval before touching live data.

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

## Advanced Features

### Batch Mode

Append `--batch` to any bulk write to approve the entire plan up front instead of confirming every sub-step:

```
/hubspot update all contacts where region is west, set timezone to PST --batch
```

You can also say "approve all" to enable batch approval for bulk operations.

### Conjunction Detection

The router detects conjunctions such as "and", "then", and "followed by" to dispatch multiple agents in dependency order.

For example:

```
/hubspot create a contact named Dana Smith and then create a deal for her
```

The router runs the objects agent first, then passes the created contact ID to the deals step.

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

This flushes the local schema cache. The next request fetches fresh metadata from HubSpot.

---

### Approval Prompt Does Not Appear

**Symptom:** A write ran without asking you.

**Fix:**

- Verify the request was not a read-only operation (search, get, list, analytics) — these do not require approval.
- If a write ran silently, file a bug — writes should never run without explicit approval.

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

| Command | Description |
| --- | --- |
| `/hubspot <request>` | Main entry point. Routes natural language to the appropriate agent. |
| `/hubspot setup <portal_id> token <pat>` | Save a Private App token for a portal. |
| `/hubspot setup <portal_id> oauth` | Start OAuth credential setup for a portal. |
| `/hubspot portal auth <portal_id>` | Run the OAuth browser flow for a portal. |
| `/hubspot portal token <portal_id>` | Show token setup helper. |
| `/hubspot portal switch <portal_id>` | Change the active portal for subsequent commands. |
| `/hubspot portal list` | List all portals with stored credentials. |
| `/hubspot status` | Show last 24 hours of stats: requests, latency, error rate, estimated cost. |
| `/hubspot refresh` | Flush the schema cache. |
| `y` / `yes` | Approve the last pending action. |
| `n` / `no` / `reject` | Reject the last pending action. |
| `approve <action_id>` | Approve a specific action by ID. |

### Disk File Reference

```
~/.claude/hubspot/
  <portal_id>.json              # PortalConfig: token, tier, auth_type, expires_at
  app_credentials.json            # OAuth app credentials (client_id, client_secret, app_id)
  <portal_id>/
    pending_previews/             # Stored preview actions (JSON, chmod 600)
    schema_cache.json             # Cached object and property schemas
    capabilities.json             # Feature matrix for this portal
```

Credentials are stored in JSON files under your home directory with `chmod(0o600)`. Tokens are never logged, printed in output, or returned in error messages.

Old `.token` plain-text files are automatically migrated into the JSON format and then deleted.

### Risk Levels and Approval Gates

| Risk Level | Trigger | Approval UI |
| --- | --- | --- |
| LOW | Search, get, list, analytics | None |
| MEDIUM | Create, update single record | Preview + `y` confirm |
| HIGH | Bulk updates (>10 records) | Full plan preview + explicit confirm |
| DESTRUCTIVE | Delete | Exact count gate |

### Environment Variables

| Variable | Purpose |
| --- | --- |
| `HUBSPOT_TOKEN_<portal_id>` | Fallback Private App token if not in `~/.claude/hubspot/<portal_id>.json` |
| `HUBSPOT_OAUTH_CALLBACK_PORT` | Override the default `3000` port for the OAuth redirect listener |

---

*Last updated: 2026-05-11*
