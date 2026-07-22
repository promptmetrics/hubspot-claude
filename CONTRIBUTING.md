# Contributing

Thanks for helping improve the HubSpot Agent plugin. This guide covers local setup, the
checks your change must pass, and the conventions we follow.

## Ground rules

- **`docs/PRD.md` is the source of truth.** Read it before non-trivial work and keep it
  current: reference requirements by number (e.g. "R11") in commits and PRs, and update the
  §6 Status table and §4 Decisions log when behavior or scope changes.
- **Every write stays human-gated.** Never add a code path that mutates a portal without
  going through the preview → `approve` contract. Change write behavior in the shared handler
  set (`handlers.py` / `safety.py`), never in one call path — the daemon, in-process, and CLI
  paths must stay identical.
- **Counts are derived, not hardcoded.** Don't hardcode agent/tool/blueprint counts in docs or
  prompts — derive them from `hubspot agents list` / `hubspot tools list`.

## Local setup

```bash
git clone https://github.com/promptmetrics/hubspot-claude.git
cd hubspot-claude
pip install -e ".[dev]"     # Python >= 3.12
```

## Checks (must be green before you open a PR)

```bash
pytest -x                                    # full suite
claude plugin validate ./                    # schema-check plugin.json + marketplace.json + hooks
bash scripts/check-artifact-allowlist.sh     # shipping-artifact allowlist gate
```

CI runs the same three checks on Python 3.12 for every PR and push to main (R10). Match the
existing test style: `pytest-asyncio`, `respx` / `pytest-httpx` (no live HubSpot calls), and
`hypothesis` for property tests. Assert on outbound HTTP request bodies and cover error
envelopes — never trust a success envelope.

## Adding an agent or tool

- A new **agent** must be registered in `src/hubspot_agent/agents/__init__.py` **and** the
  dispatch tables in `dispatch.py` (`_EXECUTE_DISPATCH`, `_RECONCILE_DISPATCH`).
- A new **tool** lives under `src/hubspot_agent/tools/` and is picked up by the pkgutil walk in
  `tools/__init__.py` — don't break that import, or the daemon subprocess sees an empty registry.

## Commits & pull requests

- Use conventional commits (`feat:`, `fix:`, `test:`, `docs:` …) and reference requirement IDs.
- When bumping the version, keep `pyproject.toml`, `.claude-plugin/plugin.json`, and
  `.claude-plugin/marketplace.json` in sync.
- Open PRs against `promptmetrics/hubspot-claude`.

By contributing, you agree that your contributions are licensed under the MIT License (see
[LICENSE](LICENSE)).
