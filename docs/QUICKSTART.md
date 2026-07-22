# Quick Start

Get the HubSpot Admin Agent running in under 10 minutes.

---

## Prerequisites

- Python 3.12+
- Claude Code (the agent runs as a Claude Code skill)
- A HubSpot portal ID

---

## Installation

```bash
git clone https://github.com/promptmetrics/hubspot-claude.git
cd hubspot-claude
pip install -e ".[dev]"
```

Ensure `PYTHONPATH` includes `src` so Claude Code can load the skill:

```bash
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"
```

Or add it to your shell profile.

---

## Authentication

Pick one method. Private App Token is fastest.

### Private App Token (3 steps)

**1. Create the token in HubSpot**

Go to **Settings > Integrations > Private Apps** in your HubSpot portal.
Create a private app named `Claude Code Agent` and grant at least these scopes:

- `crm.objects.contacts.read`, `crm.objects.contacts.write`
- `crm.objects.companies.read`, `crm.objects.companies.write`
- `crm.objects.deals.read`, `crm.objects.deals.write`
- `automation.workflows.read`, `automation.workflows.write`
- `crm.lists.read`, `crm.lists.write`
- `crm.pipelines.read`, `crm.pipelines.write`

Copy the token (starts with `pat-na1-`).

**2. Configure the agent**

```
/hubspot setup <portal_id> token <pat>
```

**3. Verify**

```
/hubspot status
```

You should see the portal ID, tier, and last 24 hours of stats.

### OAuth 2.0 (4 steps)

Use this for team setups or when your security policy requires refreshable tokens.

**1. Create a public app**

Go to [https://developers.hubspot.com](https://developers.hubspot.com) and create a new public app.
Note the **App ID**, **Client ID**, and **Client Secret**.
Set the redirect URL to `http://localhost:3000/oauth/callback`.
Request the same scopes listed in the Private App section above.

**2. Save app credentials**

Run this inside Claude Code:

```python
from hubspot_agent.app_credentials import save_app_credentials
save_app_credentials(
    client_id='your-client-id',
    client_secret='your-client-secret',
    app_id='your-app-id'
)
```

**3. Start the OAuth flow**

```
/hubspot setup <portal_id> oauth
```

A browser window opens. Log into HubSpot and authorize the app.
The skill stores the access and refresh tokens automatically.

**4. Verify**

```
/hubspot status
```

---

## Portal Auto-Detection

Create a `.hubspot-portal` file in your working directory so you never have to type the portal ID again:

```bash
echo "1234567" > .hubspot-portal
```

Switch portals at any time:

```
/hubspot portal switch <portal_id>
```

List all configured portals:

```
/hubspot portal list
```

---

## First Command

Confirm the connection with a read-only search:

```
/hubspot find contacts
```

The agent routes the request to the **Objects** agent, searches your HubSpot contacts, and returns the results. No approval needed.

---

## First Write

Create a contact to see the human-in-the-loop approval flow:

```
/hubspot create a contact named Dana Smith with email dana@example.com
```

The agent shows a preview:

```
⚠️  Preview (action: a1b2c3d4)
Risk: MEDIUM
Impact: 1 records
Will create a new contacts record

Approve with `y` or `approve <id>`, reject with `n`.
```

Approve it:

```
y
```

The agent executes the create and returns the new record ID.

Reject it:

```
n
```

Or approve a specific action by ID:

```
approve a1b2c3d4
```

---

## Common Workflows

| What you want | Command |
| --- | --- |
| Find deals closing this quarter | `/hubspot show me deals closing this quarter` |
| Create a deal | `/hubspot create a deal called "Acme Renewal" worth $50,000` |
| Update a record | `/hubspot update contact 12345, set lifecyclestage to customer` |
| Build a workflow | `/hubspot build a workflow that alerts the deal owner 30 days before renewal date` |
| Find duplicates | `/hubspot find duplicate contacts with the same email` |
| Associate records | `/hubspot associate contact 12345 with company 67890` |
| Flush stale cache | `/hubspot refresh` |
| Bulk-fix many records with one approval | `/hubspot --pattern 'set lifecyclestage to customer for contacts in the "Closed Won Q3" list'` |

The agent routes each request to the correct specialist sub-agent — objects, properties, workflows, lists, pipelines, users, hygiene, analytics, associations, engagements, custom objects, service, raw API, and more. Run `hubspot agents list` for the full, current set.

---

## Scheduled / recurring tasks

Run hygiene on a cadence without keeping a session open. A schedule stores a
concrete plan plus a cron expression; an OS timer replays it, running the reads
unattended and **staging every write for you to approve later** — nothing
mutates on its own.

```bash
# 1. Register a schedule (Claude builds the concrete plan; you supply the cron).
hubspot schedule add --plan '<LoopPlan JSON>' --cron '0 9 * * 1' --name 'Weekly stale-deal sweep'

# 2. Install the OS timer that polls for due schedules (prints a launchd/cron snippet).
hubspot schedule install-timer

# 3. Inspect / manage.
hubspot schedule list
hubspot schedule remove <id>
```

When a schedule fires, its writes appear under **Pending approvals** in
`hubspot status`, grouped by schedule. Approve them as usual — each write
re-checks the record with compare-and-set, so anything that drifted since the
run is skipped, never overwritten. A schedule won't re-run while its last batch
is still unreviewed; an unreviewed batch expires after `schedule_queue_ttl_days`
(default 7). Plans must be concrete (every step a specific tool call) so the
timer can replay them deterministically with no model in the loop.

---

## Next Steps

- **Full feature reference:** See [docs/superpowers/USER_MANUAL.md](docs/superpowers/USER_MANUAL.md)
- **Guided walkthrough:** See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)
