"""hubspot CLI router — venv-resolved entrypoint that routes ``tool`` calls
through the warm-client daemon (FR-15) and falls back to the in-process CLI.

Invoked by ``bin/hubspot`` after it resolves the plugin venv python.  Only the
``tool`` subcommand benefits from the warm daemon (HubSpot I/O via one reused
``HubSpotClient`` + ``SchemaCache``); ``serve stop`` is daemon-native.
Everything else — ``approve``/``reject`` (low-frequency, no warm-client
benefit), ``loop *`` (local disk), ``route``, ``agents`` — runs in-process via
:func:`hubspot_agent.cli.hubspot_command` so behaviour is identical to the
console-script path.  ``approve`` is routed in-process deliberately: it is
low-frequency and the in-process path shares the same
:func:`hubspot_agent.handlers.execute_pending_write` core (FR-19 gate,
FR-17/18 undo, FR-17 audit) as the daemon handler, so both paths behave
identically.

Crash recovery (FR-15): a stale PID → unlink socket + restart; a PRE-send
failure (connect refused / stale socket — the request never reached the
daemon) → kill + restart once + retry, else fall back to the in-process CLI.
A POST-send failure (recv timeout / EOF) means the daemon may have already
persisted a pending preview, so a WRITE tool is never re-sent and never falls
back — the caller gets a warning pointing at ``hubspot pending`` instead of a
duplicate/orphan preview.  Reads stay retryable (re-running a read is safe).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DAEMON_IDLE_TIMEOUT = 600.0
# 2x the client's per-request httpx timeout (30s): a tool RPC is a handful of
# HubSpot requests at most (writes only build a read-based preview).  The old
# 5s value SIGTERM'd a healthy daemon mid-request and re-ran the call up to
# three times, persisting a distinct pending preview per pass (M11).
RPC_TIMEOUT = 60.0
LAZY_START_TIMEOUT = 5.0


class DaemonUnreachable(OSError):
    """Connect failed — the request never reached the daemon (safe to retry)."""


def plugin_data_dir() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "plugins" / "data" / "hubspot"


def socket_path() -> Path:
    return plugin_data_dir() / "hubspot.sock"


def pid_path() -> Path:
    return plugin_data_dir() / "hubspot.pid"


def install_log_path() -> Path:
    return plugin_data_dir() / "install.log"


def resolve_venv_python() -> str | None:
    """Resolve the plugin venv python (FR-15 venv contract).

    Priority: ``$CLAUDE_PLUGIN_DATA/venv.path`` → ``$CLAUDE_PLUGIN_DATA/venv/bin/python``
    → glob ``~/.claude/plugins/data/hubspot-*/venv/bin/python`` → None.
    """
    data = plugin_data_dir()
    venv_path_file = data / "venv.path"
    if venv_path_file.is_file():
        try:
            vp = venv_path_file.read_text().strip()
        except OSError:
            vp = ""
        if vp:
            cand = Path(vp) / "bin" / "python"
            if cand.exists() and os.access(cand, os.X_OK):
                return str(cand)
    cand = data / "venv" / "bin" / "python"
    if cand.exists() and os.access(cand, os.X_OK):
        return str(cand)
    for p in sorted(Path.home().glob(".claude/plugins/data/hubspot-*/venv/bin/python")):
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_pid() -> int:
    try:
        return int(pid_path().read_text().strip())
    except (OSError, ValueError):
        return 0


def is_daemon_alive() -> bool:
    """True if a live daemon owns the socket.  Cleans up a stale socket/PID."""
    sock = socket_path()
    if not sock.exists():
        return False
    pid = _read_pid()
    if pid and _pid_alive(pid):
        return True
    try:
        sock.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass
    return False


def rpc_call(method: str, params: dict[str, Any], *, timeout: float = RPC_TIMEOUT) -> dict[str, Any]:
    """Send one JSON-RPC line to the daemon and return the parsed response."""
    payload = (json.dumps({"method": method, "params": params, "id": 1}) + "\n").encode("utf-8")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(str(socket_path()))
        except OSError as exc:
            raise DaemonUnreachable(str(exc)) from exc
        s.sendall(payload)
        buf = bytearray()
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    if not buf:
        raise TimeoutError("daemon returned no response")
    return json.loads(buf.decode("utf-8"))


def start_daemon(portal_id: str, *, idle_timeout: float = DAEMON_IDLE_TIMEOUT) -> subprocess.Popen:
    """Lazily start the warm-client daemon detached (FR-15)."""
    plugin_data_dir().mkdir(parents=True, exist_ok=True)
    os.chmod(plugin_data_dir(), 0o700)
    log = open(install_log_path(), "a")
    return subprocess.Popen(
        [sys.executable, "-m", "hubspot_agent.daemon", portal_id, "--idle-timeout", str(idle_timeout)],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )


def _kill_daemon() -> None:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.05)
    try:
        socket_path().unlink(missing_ok=True)
    except OSError:
        pass
    try:
        pid_path().unlink(missing_ok=True)
    except OSError:
        pass


def _wait_for_socket(timeout: float = LAZY_START_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if socket_path().exists():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(str(socket_path()))
                s.close()
                return True
            except OSError:
                pass
        time.sleep(0.05)
    return False


def _parse_tool_argv(tokens: list[str]) -> tuple[str, dict[str, Any]]:
    if not tokens:
        raise ValueError("tool name required")
    tool_name = tokens[0]
    tool_input: dict[str, Any] = {}
    if "--input" in tokens:
        i = tokens.index("--input")
        raw = tokens[i + 1] if i + 1 < len(tokens) else ""
        if raw == "-":
            raw = sys.stdin.read()
        if raw.strip():
            tool_input = json.loads(raw)  # raises on bad JSON
            if not isinstance(tool_input, dict):
                raise ValueError("--input must be a JSON object")
    return tool_name, tool_input


def _format_tool_response(resp: dict[str, Any]) -> str:
    if "error" in resp:
        err = resp["error"]
        return f"error: {err.get('message', err.get('kind', 'unknown'))}"
    data = resp.get("result", {}).get("data", {})
    if "result" in data:  # read → match cli._tool_read output
        return json.dumps(data["result"], indent=2, default=str)
    return json.dumps(data, indent=2, default=str)  # write preview → match cli._tool_write


def _is_portal_mismatch(resp: dict[str, Any]) -> bool:
    """True if the daemon rejected the call because it serves another portal."""
    err = resp.get("error")
    return isinstance(err, dict) and err.get("kind") == "portal_mismatch"


def _rpc_tool(params: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """One ``tool`` RPC.  Returns ``(response, failure_kind)`` where
    failure_kind is ``""`` on success, ``"unreachable"`` when the request never
    reached the daemon, or ``"post_send"`` when it may have been processed."""
    try:
        return rpc_call("tool", params), ""
    except DaemonUnreachable:
        return None, "unreachable"
    except (OSError, TimeoutError, json.JSONDecodeError):
        return None, "post_send"


def _is_write_tool_call(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Registry-driven write classification (never tool-name heuristics)."""
    from hubspot_agent.handlers import _is_write_tool
    from hubspot_agent.scope_registry import get_required_scopes

    target = tool_input.get("object_type") if isinstance(tool_input, dict) else None
    return _is_write_tool(get_required_scopes([tool_name], target), tool_name, tool_input)


def _post_send_write_warning(tool_name: str) -> str:
    return (
        f"error: the daemon did not answer within {int(RPC_TIMEOUT)}s for {tool_name}. "
        "The write preview may still have been stored — run `hubspot pending` and "
        "`hubspot reject <action_id>` on any orphan before retrying."
    )


def _daemon_tool_path(tool_name: str, tool_input: dict[str, Any], portal_id: str) -> str | None:
    """Try the warm-client daemon for a tool call.  Return formatted output or
    None when the daemon path fails (caller falls back to the in-process CLI)."""
    # The socket is global (one per plugin data dir), so a live daemon may serve a
    # different portal than requested.  Send the target portal so the daemon can
    # reject a mismatch; on rejection we restart it bound to the right portal
    # below.  Without this a `--portal B` call silently hits a daemon warmed for
    # portal A (reads A's data, stores the write preview under A).
    params = {
        "tool_name": tool_name,
        "input": tool_input,
        "batch_mode": "single",
        "portal_id": portal_id,
    }

    # Attempt 1: reuse a live daemon, else lazy-start one for this portal.
    if not is_daemon_alive():
        try:
            start_daemon(portal_id)
        except OSError:
            return None
        if not _wait_for_socket():
            return None
    resp, failure = _rpc_tool(params)
    if resp is not None and not _is_portal_mismatch(resp):
        return _format_tool_response(resp)
    if resp is None and failure == "post_send" and _is_write_tool_call(tool_name, tool_input):
        # The daemon may have already persisted this write's pending preview;
        # re-sending (or falling back in-process) would mint a second one.
        return _post_send_write_warning(tool_name)

    # Attempt 2: the live daemon serves a different portal, or the request
    # never got through / a read failed post-send — kill the daemon, restart
    # one bound to THIS portal, and retry once (FR-15; reads are re-runnable).
    _kill_daemon()
    try:
        start_daemon(portal_id)
    except OSError:
        return None
    if not _wait_for_socket():
        return None
    resp, failure = _rpc_tool(params)
    if resp is None:
        if failure == "post_send" and _is_write_tool_call(tool_name, tool_input):
            return _post_send_write_warning(tool_name)
        return None
    return _format_tool_response(resp)


def _cli_fallback(remaining: list[str], working_dir: str, portal_id: str | None) -> str:
    from hubspot_agent.cli import hubspot_command

    return hubspot_command(" ".join(remaining), working_dir, portal_id=portal_id)


def _cli_fallback_tool(
    tool_name: str, tool_input: dict[str, Any], working_dir: str, portal_id: str | None
) -> str:
    """In-process fallback for a tool call, re-serializing the ALREADY-parsed
    input so ``--input -`` stdin is consumed exactly once (router-side); the
    CLI parser must never re-read an exhausted stdin into a ``{}`` preview."""
    from hubspot_agent.cli import hubspot_command

    args = f"tool {tool_name}"
    if tool_input:
        args += f" --input {json.dumps(tool_input)}"
    return hubspot_command(args, working_dir, portal_id=portal_id)


def route(argv: list[str]) -> int:
    from hubspot_agent.cli import _strip_global_flags
    from hubspot_agent.config import detect_default_portal

    remaining, working_dir, portal_id = _strip_global_flags(list(argv))
    if working_dir is None:
        working_dir = os.getcwd()
    if not remaining:
        print(_cli_fallback(remaining, working_dir, portal_id))
        return 0

    head = remaining[0].lower()

    if head == "tool":
        # Parse ONCE (consumes `--input -` stdin here and nowhere else).
        try:
            tool_name, tool_input = _parse_tool_argv(remaining[1:])
        except ValueError as exc:
            print(f"Usage: hubspot tool <name> [--input <json>|-]\n  error: {exc}")
            return 0
        pid = portal_id or detect_default_portal(working_dir)
        if pid:
            out = _daemon_tool_path(tool_name, tool_input, pid)
            if out is not None:
                print(out)
                return 0
        # No portal, or daemon path failed → in-process CLI fallback.
        print(_cli_fallback_tool(tool_name, tool_input, working_dir, portal_id))
        return 0

    if head == "serve":
        sub = remaining[1].lower() if len(remaining) >= 2 else ""
        if sub == "stop":
            if is_daemon_alive():
                try:
                    rpc_call("serve_stop", {})
                except OSError:
                    pass
                print("daemon stop requested")
            else:
                print("daemon not running")
            return 0
        # ``hubspot serve`` — start the warm-client daemon in the foreground
        # (blocks until idle-timeout or ``hubspot serve stop``).  The lazy-start
        # path in ``_daemon_tool_path`` covers the common case; this is for
        # explicit/E2E use (runbook §16.5).
        pid = portal_id or detect_default_portal(working_dir)
        if not pid:
            print("No default portal found.")
            return 1
        from hubspot_agent.daemon import main as daemon_main

        return daemon_main([pid])

    # approve/reject (undo+audit), loop_* (local disk), route/agents/tools/agent-prompt/status/…
    print(_cli_fallback(remaining, working_dir, portal_id))
    return 0


def main(argv: list[str] | None = None) -> int:
    return route(sys.argv[1:] if argv is None else list(argv))


if __name__ == "__main__":
    sys.exit(main())