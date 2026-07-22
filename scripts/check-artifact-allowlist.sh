#!/bin/sh
# Pre-publish check: every git-tracked file must be inside the shipping
# allowlist.  Run before tagging/publishing:
#   bash scripts/check-artifact-allowlist.sh
#
# Allowlist (PRD §10): src/ tests/ bin/hubspot hooks/ .claude-plugin/ .github/
# output-styles/ SKILL.md README.md CHANGELOG.md LICENSE pyproject.toml .gitignore
# scripts/check-artifact-allowlist.sh (this script is committed so CI can run it)
# docs/PRD.md (the only tracked file under docs/; source-of-truth spec)
# community-health: CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md GOVERNANCE.md
set -u

allow_regex='^(src/|tests/|bin/hubspot$|hooks/|\.claude-plugin/|\.github/|scripts/check-artifact-allowlist\.sh$|docs/PRD\.md$|output-styles/|SKILL\.md$|README\.md$|CHANGELOG\.md$|CONTRIBUTING\.md$|CODE_OF_CONDUCT\.md$|SECURITY\.md$|GOVERNANCE\.md$|LICENSE$|pyproject\.toml$|\.gitignore$)'

bad=$(git ls-files | grep -Ev "$allow_regex")
if [ -n "$bad" ]; then
  echo "ERROR: tracked files outside the shipping allowlist:" >&2
  printf '%s\n' "$bad" | sed 's/^/  /' >&2
  echo "  Fix: git rm --cached <path> && add it to .gitignore." >&2
  exit 1
fi

echo "OK: all $(git ls-files | wc -l | tr -d ' ') tracked files are within the shipping allowlist."