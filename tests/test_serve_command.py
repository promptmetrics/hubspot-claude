"""T13: ``hubspot serve`` (foreground start) + ``hubspot serve stop`` (shutdown
RPC) + idle-timeout self-exit leaves no orphan/stale socket.

The daemon-side shutdown + idle-exit are covered by ``test_daemon.py``; this
file covers the router ``serve`` subcommand and a real end-to-end ``serve
stop`` through ``router.rpc_call`` against a fake-warmed daemon.
"""
from __future__ import annotations

import asyncio
import os
import types
from pathlib import Path

import pytest

import hubspot_agent.agents  # noqa: F401 — registers tools for the daemon handlers
from hubspot_agent import router


def test_route_serve_start_calls_daemon_main(monkeypatch, capsys):
    captured: dict = {}

    def fake_main(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("hubspot_agent.daemon.main", fake_main)
    assert router.route(["serve", "--portal", "123"]) == 0
    assert captured["argv"] == ["123"]


def test_route_serve_start_no_portal(monkeypatch, capsys):
    monkeypatch.setattr("hubspot_agent.config.detect_default_portal", lambda wd: None)
    monkeypatch.setattr("hubspot_agent.daemon.main", lambda argv: pytest.fail("must not start with no portal"))
    assert router.route(["serve"]) == 1
    assert "No default portal" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_route_serve_stop_real_integration(tmp_path, monkeypatch):
    from hubspot_agent.config import PortalConfig
    from hubspot_agent.daemon import HubSpotDaemon

    sock = Path(f"/tmp/hsd-t13-{os.getpid()}.sock")
    if sock.exists():
        sock.unlink()
    pid_file = tmp_path / "hubspot.pid"

    # Both the router and the daemon must agree on the socket + pid paths.
    monkeypatch.setattr(router, "socket_path", lambda: sock)
    monkeypatch.setattr(router, "pid_path", lambda: pid_file)
    monkeypatch.setattr("hubspot_agent.daemon.pid_path", lambda: pid_file)

    daemon = HubSpotDaemon(PortalConfig(portal_id="123", token="t"), sock_path=sock, idle_timeout=30)

    async def _warm(self):
        self.client = None
        self.cache = None

    daemon._warm = types.MethodType(_warm, daemon)
    task = asyncio.create_task(daemon.serve())

    try:
        elapsed = 0.0
        while not (sock.exists() and pid_file.exists()) and elapsed < 5.0:
            await asyncio.sleep(0.02)
            elapsed += 0.02
        assert sock.exists() and pid_file.exists()

        # Blocking rpc_call runs in a thread so the daemon loop can answer.
        rc = await asyncio.to_thread(router.route, ["serve", "stop"])
        assert rc == 0
        await asyncio.wait_for(task, timeout=5)
    finally:
        daemon._stop.set()
        try:
            await asyncio.wait_for(task, timeout=2)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    assert not sock.exists()
    assert not pid_file.exists()


def test_cli_fallback_envelope_on_unexpected_exception(monkeypatch, capsys):
    """Bug 8b: an unhandled exception in the in-process fallback path must render
    as the daemon-shaped NFR-15 envelope (``{"error": {"kind": "server", ...}}``),
    not a raw traceback."""
    import json as _json

    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("hubspot_agent.cli.hubspot_command", _boom)
    # Non-tool, non-serve path → _cli_fallback.
    assert router.route(["agents", "list"]) == 0
    out = capsys.readouterr().out
    assert "Traceback" not in out
    payload = _json.loads(out)
    assert payload["error"]["kind"] == "server"
    assert "kaboom" in payload["error"]["message"]
    assert payload["error"]["retryable"] is True


def test_cli_fallback_tool_envelope_on_unexpected_exception(monkeypatch, capsys):
    """Bug 8b (tool path): the in-process tool fallback emits the same
    daemon-shaped envelope when ``hubspot_command`` raises."""
    import json as _json

    def _boom(*args, **kwargs):
        raise RuntimeError("tool-kaboom")

    monkeypatch.setattr("hubspot_agent.cli.hubspot_command", _boom)
    # No portal → daemon path skipped → _cli_fallback_tool.
    monkeypatch.setattr("hubspot_agent.config.detect_default_portal", lambda wd: None)
    assert router.route(["tool", "hubspot_search_objects", "--input", "{}"]) == 0
    out = capsys.readouterr().out
    assert "Traceback" not in out
    payload = _json.loads(out)
    assert payload["error"] == {"kind": "server", "message": "tool-kaboom", "retryable": True}