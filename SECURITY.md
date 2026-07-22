# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security problems.** Report privately via GitHub's
[private vulnerability reporting](https://github.com/promptmetrics/hubspot-claude/security/advisories/new),
or email izzy@promptmetrics.dev.

Include the affected version, reproduction steps, and impact. Expect an
acknowledgement within 3 business days and, for confirmed issues, a fix or
mitigation plan within 30 days.

## Supported versions

Only the latest released version receives security fixes. Check the current version
via the badge in the README or `git tag`.

## How this plugin handles your data

- **Tokens stay local.** HubSpot OAuth / Private-App tokens are stored under
  `~/.claude/hubspot/<portal>/` and are sent only to HubSpot's API. The plugin never
  uses HubSpot API keys.
- **Nothing sensitive is committed.** Tokens, portal config, and audit logs live
  outside the repo. Never commit the contents of `~/.claude/hubspot/`, and never paste
  a token into an issue or PR.
- **Audit logs are redacted.** The NDJSON audit log redacts token material.
- **Writes are gated.** Every write requires a human `approve`; there is no code path
  that mutates your portal without an explicit approval (see the README safety note and
  the shared contract in `handlers.py` / `safety.py`).
- **Local daemon only.** The warm-client daemon listens on a Unix socket (0600) inside a
  0700 directory — it has no network listener.

## Hardening recommendations

- Restrict `~/.claude/hubspot/` and exclude it from backups/sync per your policy.
- Grant Private-App / OAuth scopes at least privilege. The plugin never requests
  `.delete` scopes at authorize time (`scope_registry`).
