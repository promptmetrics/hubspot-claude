"""T12: bin/hubspot venv resolver + daemon router + fallback (FR-15).

Exercises ``hubspot_agent.router``: the venv-python resolver priority, the
daemon-alive fast path, lazy-start-then-retry, crash recovery (kill + restart +
retry once), and the in-process CLI fallback.  All daemon I/O (socket, PID
file, subprocess) is mocked so no real daemon spawns.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hubspot_agent import router


def _make_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    path.chmod(0o755)
    return path


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# resolve_venv_python — priority chain
# ---------------------------------------------------------------------------


def test_resolve_venv_python_venv_path_wins(data_dir, tmp_path):
    fake_venv = tmp_path / "fakevenv"
    _make_exe(fake_venv / "bin" / "python")
    (tmp_path / "venv.path").write_text(str(fake_venv))
    # Canonical candidate exists too — venv.path must take precedence.
    _make_exe(tmp_path / "venv" / "bin" / "python")
    assert router.resolve_venv_python() == str(fake_venv / "bin" / "python")


def test_resolve_venv_python_canonical(data_dir, tmp_path):
    _make_exe(tmp_path / "venv" / "bin" / "python")
    assert router.resolve_venv_python() == str(tmp_path / "venv" / "bin" / "python")


def test_resolve_venv_python_glob(data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cand = _make_exe(tmp_path / ".claude/plugins/data/hubspot-xyz/venv/bin/python")
    assert router.resolve_venv_python() == str(cand)


def test_resolve_venv_python_none(data_dir, tmp_path, monkeypatch):
    # Hermetic: isolate from any real ~/.claude/plugins/data/hubspot-*/venv
    # a SessionStart hook may have provisioned on this machine.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert router.resolve_venv_python() is None


# ---------------------------------------------------------------------------
# is_daemon_alive — stale cleanup
# ---------------------------------------------------------------------------


def test_is_daemon_alive_stale_cleans_up(data_dir, tmp_path):
    router.socket_path().parent.mkdir(parents=True, exist_ok=True)
    router.socket_path().touch()
    router.pid_path().write_text("999999")  # dead pid
    assert router.is_daemon_alive() is False
    assert not router.socket_path().exists()
    assert not router.pid_path().exists()


def test_is_daemon_alive_live_pid(data_dir, tmp_path):
    router.socket_path().parent.mkdir(parents=True, exist_ok=True)
    router.socket_path().touch()
    router.pid_path().write_text(str(os.getpid()))
    assert router.is_daemon_alive() is True
    assert router.socket_path().exists()


# ---------------------------------------------------------------------------
# route — tool daemon path
# ---------------------------------------------------------------------------


def _tool_argv():
    return ["tool", "hubspot_get_object", "--input", '{"object_type":"contacts","object_id":"42"}', "--portal", "123"]


def test_route_tool_daemon_alive_fast_path(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: True)

    def _no_start(*a, **k):
        raise AssertionError("start_daemon must not be called when daemon is alive")

    monkeypatch.setattr(router, "start_daemon", _no_start)
    monkeypatch.setattr(
        router,
        "rpc_call",
        lambda method, params, **k: {"result": {"data": {"tool": "hubspot_get_object", "result": {"id": "42"}}}},
    )
    assert router.route(_tool_argv()) == 0
    out = capsys.readouterr().out
    assert '"42"' in out


def test_route_tool_lazy_start_then_retry(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: False)
    starts: list = []
    monkeypatch.setattr(router, "start_daemon", lambda portal_id, **k: starts.append(portal_id) or object())
    monkeypatch.setattr(router, "_wait_for_socket", lambda *a, **k: True)
    monkeypatch.setattr(
        router,
        "rpc_call",
        lambda method, params, **k: {"result": {"data": {"tool": "x", "result": {"id": "7"}}}},
    )
    assert router.route(_tool_argv()) == 0
    assert starts == ["123"]
    assert '"7"' in capsys.readouterr().out


def test_route_tool_fallback_to_cli(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: False)

    def _bad_start(*a, **k):
        raise OSError("no venv")

    monkeypatch.setattr(router, "start_daemon", _bad_start)
    monkeypatch.setattr(router, "rpc_call", lambda *a, **k: pytest.fail("rpc_call must not run on fallback"))
    monkeypatch.setattr("hubspot_agent.cli.hubspot_command", lambda req, wd, *, portal_id=None: "cli-output")
    assert router.route(_tool_argv()) == 0
    assert capsys.readouterr().out.strip() == "cli-output"


def test_route_tool_crash_recovery(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: True)
    calls = {"rpc": 0, "kills": 0, "starts": 0}

    def _rpc(method, params, **k):
        calls["rpc"] += 1
        if calls["rpc"] == 1:
            raise TimeoutError("hung daemon")
        return {"result": {"data": {"tool": "x", "result": {"id": "9"}}}}

    monkeypatch.setattr(router, "rpc_call", _rpc)
    monkeypatch.setattr(router, "_kill_daemon", lambda: calls.__setitem__("kills", calls["kills"] + 1))
    monkeypatch.setattr(router, "start_daemon", lambda portal_id, **k: calls.__setitem__("starts", calls["starts"] + 1) or object())
    monkeypatch.setattr(router, "_wait_for_socket", lambda *a, **k: True)
    assert router.route(_tool_argv()) == 0
    assert calls["rpc"] == 2
    assert calls["kills"] == 1
    assert calls["starts"] == 1
    assert '"9"' in capsys.readouterr().out


def test_route_tool_no_portal_falls_back(data_dir, monkeypatch, capsys):
    monkeypatch.setattr("hubspot_agent.config.detect_default_portal", lambda wd: None)
    monkeypatch.setattr(router, "is_daemon_alive", lambda: pytest.fail("daemon must not be probed with no portal"))
    monkeypatch.setattr("hubspot_agent.cli.hubspot_command", lambda req, wd, *, portal_id=None: "no-portal-cli")
    assert router.route(["tool", "x", "--input", "{}"]) == 0
    assert capsys.readouterr().out.strip() == "no-portal-cli"


def test_route_tool_parse_error_returns_usage(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: pytest.fail("parse error must short-circuit"))
    assert router.route(["tool", "--input", "{bad json}", "--portal", "123"]) == 0
    out = capsys.readouterr().out
    assert "Usage" in out and "error" in out


# ---------------------------------------------------------------------------
# M11: post-send failures never re-send a WRITE (the daemon may have already
# persisted its pending preview); reads stay retryable; `--input -` stdin is
# consumed exactly once and survives the in-process fallback.
# ---------------------------------------------------------------------------


def _write_argv():
    return [
        "tool", "hubspot_create_object",
        "--input", '{"object_type":"contacts","properties":{"email":"a@example.com"}}',
        "--portal", "123",
    ]


def test_write_tool_post_send_timeout_no_retry_no_fallback(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: True)

    def _rpc(method, params, **k):
        raise TimeoutError("hung daemon")

    monkeypatch.setattr(router, "rpc_call", _rpc)
    monkeypatch.setattr(router, "_kill_daemon", lambda: pytest.fail("write must not kill/retry post-send"))
    monkeypatch.setattr(router, "start_daemon", lambda *a, **k: pytest.fail("write must not restart the daemon"))
    monkeypatch.setattr("hubspot_agent.cli.hubspot_command", lambda *a, **k: pytest.fail("write must not fall back in-process"))
    assert router.route(_write_argv()) == 0
    out = capsys.readouterr().out
    assert "did not answer" in out
    assert "hubspot pending" in out


def test_write_tool_unreachable_is_retried(data_dir, monkeypatch, capsys):
    # Pre-send failure: the request never reached the daemon, so a write is
    # safe to retry after a restart.
    monkeypatch.setattr(router, "is_daemon_alive", lambda: True)
    calls = {"rpc": 0}

    def _rpc(method, params, **k):
        calls["rpc"] += 1
        if calls["rpc"] == 1:
            raise router.DaemonUnreachable("connect refused")
        return {"result": {"data": {"status": "preview", "action_id": "abc12345"}}}

    monkeypatch.setattr(router, "rpc_call", _rpc)
    monkeypatch.setattr(router, "_kill_daemon", lambda: None)
    monkeypatch.setattr(router, "start_daemon", lambda *a, **k: object())
    monkeypatch.setattr(router, "_wait_for_socket", lambda *a, **k: True)
    assert router.route(_write_argv()) == 0
    assert calls["rpc"] == 2
    assert "abc12345" in capsys.readouterr().out


def test_stdin_read_once_on_fallback(data_dir, monkeypatch, capsys):
    # `--input -` used to be consumed by the router parse, then re-read (empty)
    # by the CLI fallback — yielding a write preview for {}.
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO('{"object_type":"contacts","object_id":"42"}'))
    monkeypatch.setattr(router, "is_daemon_alive", lambda: False)

    def _bad_start(*a, **k):
        raise OSError("no venv")

    monkeypatch.setattr(router, "start_daemon", _bad_start)
    received = {}

    def _fake_cmd(req, wd, *, portal_id=None):
        received["req"] = req
        return "ok"

    monkeypatch.setattr("hubspot_agent.cli.hubspot_command", _fake_cmd)
    assert router.route(["tool", "hubspot_get_object", "--input", "-", "--portal", "123"]) == 0
    assert '"object_id"' in received["req"]
    assert "42" in received["req"]


# ---------------------------------------------------------------------------
# route — non-tool + serve stop
# ---------------------------------------------------------------------------


def test_route_non_tool_goes_to_cli(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: pytest.fail("non-tool must not probe daemon"))
    captured: dict = {}
    monkeypatch.setattr(
        "hubspot_agent.cli.hubspot_command",
        lambda req, wd, *, portal_id=None: captured.update(req=req, wd=wd, pid=portal_id) or "status-out",
    )
    assert router.route(["status"]) == 0
    assert captured["req"] == "status"
    assert capsys.readouterr().out.strip() == "status-out"


def test_route_defaults_working_dir_to_cwd_when_absent(data_dir, monkeypatch, tmp_path, capsys):
    # Regression: without a --working-dir flag, _strip_global_flags returns
    # working_dir=None; detect_default_portal(None) used to raise TypeError
    # (Path(None)). route() must default working_dir to os.getcwd() so status/
    # setup work from the CLI without an explicit --working-dir.
    monkeypatch.chdir(tmp_path)
    seen: dict = {}

    def _fake_detect(wd):
        seen["wd"] = wd
        return None

    # _handle_status uses cli.py's module-level binding, so patch that, not the
    # config-module attribute (cli.py already bound the name at import time).
    monkeypatch.setattr("hubspot_agent.cli.detect_default_portal", _fake_detect)
    # Exercise the real hubspot_command → _handle_status path (no portal → safe
    # early return), not a stub, so a None working_dir would surface as TypeError.
    assert router.route(["status"]) == 0
    assert seen["wd"] is not None
    assert seen["wd"] == str(tmp_path)
    assert "No default portal" in capsys.readouterr().out


def test_route_serve_stop_alive(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: True)
    called: list = []
    monkeypatch.setattr(router, "rpc_call", lambda method, params, **k: called.append((method, params)) or {"result": {"ok": True}, "_stop": True})
    assert router.route(["serve", "stop"]) == 0
    assert called == [("serve_stop", {})]
    assert "daemon stop requested" in capsys.readouterr().out


def test_route_serve_stop_not_running(data_dir, monkeypatch, capsys):
    monkeypatch.setattr(router, "is_daemon_alive", lambda: False)
    monkeypatch.setattr(router, "rpc_call", lambda *a, **k: pytest.fail("rpc must not run when daemon down"))
    assert router.route(["serve", "stop"]) == 0
    assert "daemon not running" in capsys.readouterr().out