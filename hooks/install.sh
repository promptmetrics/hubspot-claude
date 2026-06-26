#!/bin/sh
# SessionStart hook — provision the plugin venv (FR-15 venv contract).
#
# Recreates ${CLAUDE_PLUGIN_DATA}/venv whenever the bundled pyproject.toml
# changes (or on first run), writes ${CLAUDE_PLUGIN_DATA}/venv.path so
# bin/hubspot can resolve the venv python, and NEVER blocks the session on
# failure (the skill falls back to the system python).  No curl|sh; the daemon
# is NOT started here.
set -u

ROOT="${CLAUDE_PLUGIN_ROOT:-}"
DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/hubspot}"
mkdir -p "$DATA"

PYPROJECT="$ROOT/pyproject.toml"
HASH="$DATA/.pyproject.sha"
VENV="$DATA/venv"
VENV_PATH_FILE="$DATA/venv.path"
LOG="$DATA/install.log"

# sha256 helper (macOS ships shasum, Linux ships sha256sum).
_compute_sha() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
  else
    return 1
  fi
}

# Hash-gate: rebuild only when the bundled manifest changed (or first run).
need_rebuild=0
if [ ! -d "$VENV" ] || [ ! -f "$VENV_PATH_FILE" ] || [ ! -f "$HASH" ]; then
  need_rebuild=1
else
  cur=$(cat "$HASH" 2>/dev/null)
  new=$(_compute_sha "$PYPROJECT")
  if [ -z "$new" ] || [ "$cur" != "$new" ]; then
    need_rebuild=1
  fi
fi

if [ "$need_rebuild" -ne 1 ]; then
  printf '%s\n' "$VENV" >"$VENV_PATH_FILE"
  exit 0
fi

# (Re)build venv.  Prefer uv, else python3 -m venv + pip.  No curl|sh.
rm -rf "$VENV"

if command -v uv >/dev/null 2>&1; then
  if uv venv "$VENV" >>"$LOG" 2>&1 \
     && uv pip install --python "$VENV/bin/python" "$ROOT" >>"$LOG" 2>&1; then
    :
  else
    rm -rf "$VENV"
  fi
fi

if [ ! -d "$VENV" ] && command -v python3 >/dev/null 2>&1; then
  if python3 -m venv "$VENV" >>"$LOG" 2>&1 && [ -x "$VENV/bin/pip" ]; then
    "$VENV/bin/pip" install --quiet "$ROOT" >>"$LOG" 2>&1 || rm -rf "$VENV"
  else
    rm -rf "$VENV"
  fi
fi

if [ ! -d "$VENV" ] || [ ! -x "$VENV/bin/python" ]; then
  cat >&2 <<EOF
hubspot: could not provision the plugin venv.
  See $LOG for details; re-run Claude Code to retry.
  The /hubspot skill will fall back to the system python if available.
EOF
  rm -f "$HASH" "$VENV_PATH_FILE"
  exit 0  # never block the session
fi

printf '%s\n' "$VENV" >"$VENV_PATH_FILE"
new=$(_compute_sha "$PYPROJECT")
if [ -n "$new" ]; then
  printf '%s\n' "$new" >"$HASH"
else
  rm -f "$HASH"  # no hasher → force a rebuild next session
fi
exit 0