"""T11: warm-client daemon — Unix-socket JSON-RPC, lifecycle, idle self-exit.

The daemon's ``_warm`` is stubbed so no real HubSpot HTTP occurs; a fake client
stands in for the warm ``HubSpotClient``.  Tests cover stale-socket cleanup,
a full RPC round-trip, ``serve_stop`` shutdown, idle self-exit, and error
envelopes (unknown method, malformed JSON).
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import types
from pathlib import Path

import pytest

import hubspot_agent.agents  # noqa: F401 — registers tools
from hubspot_agent.config import PortalConfig
from hubspot_agent.daemon import HubSpotDaemon, cleanup_stale_socket, pid_path, socket_path


class _FakeResp:
    def __init__(self, body):
        self.body = body


class FakeClient:
    async def get(self, url, **kw):
        return _FakeResp({"id": "42", "properties": {"firstname": "Izzy"}})

    async def post(self, url, **kw):
        return _FakeResp({"id": "new-1", "properties": kw.get("body", {}).get("properties", {})})

    async def patch(self, url, **kw):
        return _FakeResp({"id": "1", "properties": {}})

    async def delete(self, url, **kw):
        return _FakeResp({"id": "1"})

    async def close(self):
        return None


def _portal():
    return PortalConfig(portal_id="123", token="test-token", tier="Professional")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("hubspot_agent.persistence.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.loop_state.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.loop_log.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("hubspot_agent.config.CONFIG_DIR", tmp_path)
    return tmp_path


def _fake_warm(daemon: HubSpotDaemon) -> None:
    async def _warm(self):
        self.client = FakeClient()
        self.cache = None

    daemon._warm = types.MethodType(_warm, daemon)


async def _wait_for_socket(path: Path, timeout: float = 5.0) -> None:
    elapsed = 0.0
    while not path.exists() and elapsed < timeout:
        await asyncio.sleep(0.02)
        elapsed += 0.02
    if not path.exists():
        raise TimeoutError(f"socket {path} never appeared")


def _short_sock(name: str) -> Path:
    """A short Unix-socket path under /tmp to stay under the AF_UNIX limit."""
    path = Path(f"/tmp/hsd-test-{os.getpid()}-{name}.sock")
    if path.exists():
        path.unlink()
    return path


# ---------------------------------------------------------------------------
# stale-socket cleanup
# ---------------------------------------------------------------------------


def test_cleanup_stale_socket_removes_orphan(env, tmp_path):
    sock = socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.touch()
    assert sock.exists()
    assert cleanup_stale_socket() is True
    assert not sock.exists()


def test_cleanup_stale_socket_keeps_live_pid(env, tmp_path):
    sock = socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.touch()
    pid_path().parent.mkdir(parents=True, exist_ok=True)
    pid_path().write_text(str(os.getpid()))
    assert cleanup_stale_socket() is False
    assert sock.exists()


def test_cleanup_stale_socket_removes_dead_pid(env, tmp_path):
    sock = socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.touch()
    pid_path().parent.mkdir(parents=True, exist_ok=True)
    pid_path().write_text("999999")
    assert cleanup_stale_socket() is True
    assert not sock.exists()


def test_cleanup_stale_socket_no_file(env):
    assert cleanup_stale_socket() is False


# ---------------------------------------------------------------------------
# RPC round-trip + shutdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daemon_rpc_tool_roundtrip(env, tmp_path):
    sock = _short_sock("rpc")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        req = {
            "method": "tool",
            "params": {"tool_name": "hubspot_get_object", "input": {"object_type": "contacts", "object_id": "42"}},
            "id": 1,
        }
        writer.write((json.dumps(req) + "\n").encode("utf-8"))
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] == 1
        assert resp["result"]["ok"] is True
        assert resp["result"]["data"]["result"]["id"] == "42"
        writer.close()
        await writer.wait_closed()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)
    assert not sock.exists()


@pytest.mark.asyncio
async def test_daemon_serve_stop_shuts_down(env, tmp_path):
    sock = _short_sock("stop")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        writer.write((json.dumps({"method": "serve_stop", "params": {}, "id": 9}) + "\n").encode("utf-8"))
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] == 9
        assert resp["result"]["ok"] is True
        assert resp["_stop"] is True
        writer.close()
        await writer.wait_closed()
    finally:
        await asyncio.wait_for(task, timeout=5)
    assert not sock.exists()
    assert not pid_path().exists()


@pytest.mark.asyncio
async def test_daemon_unknown_method_error(env, tmp_path):
    sock = _short_sock("unk")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        writer.write((json.dumps({"method": "bogus", "params": {}, "id": 3}) + "\n").encode("utf-8"))
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] == 3
        assert resp["error"]["kind"] == "not_found"
        writer.close()
        await writer.wait_closed()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_daemon_rejects_mismatched_portal(env, tmp_path):
    """A tool call targeting a different portal than the daemon serves must be
    refused with a portal_mismatch error, not silently run against the wrong
    portal (the socket is global, one daemon per plugin data dir)."""
    sock = _short_sock("pmm")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)  # serves "123"
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        writer.write(
            (json.dumps({
                "method": "tool",
                "params": {"tool_name": "hubspot_get_object", "input": {}, "portal_id": "999"},
                "id": 7,
            }) + "\n").encode("utf-8")
        )
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] == 7
        assert resp["error"]["kind"] == "portal_mismatch"
        assert "123" in resp["error"]["message"]
        writer.close()
        await writer.wait_closed()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_daemon_malformed_json_error(env, tmp_path):
    sock = _short_sock("bad")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        writer.write(b"not json\n")
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] is None
        assert resp["error"]["kind"] == "validation"
        writer.close()
        await writer.wait_closed()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_daemon_non_dict_payload_error(env, tmp_path):
    sock = _short_sock("nondict")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        # Valid JSON, but not an object — must yield a structured error, not an AttributeError.
        writer.write(b"[1, 2, 3]\n")
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] is None
        assert resp["error"]["kind"] == "validation"
        assert "object" in resp["error"]["message"]
        writer.close()
        await writer.wait_closed()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_daemon_warm_discovers_custom_schemas(env, tmp_path, monkeypatch):
    # #5: the daemon's _warm must discover custom schemas (not just standard
    # ones) so the warm cache knows custom object types.
    from hubspot_agent import daemon as daemon_mod

    discovered: list[bool] = []

    async def _fake_warm_std(portal_config):
        from hubspot_agent.cache import SchemaCache
        return SchemaCache(portal_config.portal_id)

    async def _fake_discover(portal_config):
        discovered.append(True)
        return ["custom_thing"]

    monkeypatch.setattr(daemon_mod, "warm_standard_schemas", _fake_warm_std)
    monkeypatch.setattr(daemon_mod, "discover_custom_schemas", _fake_discover)

    daemon = HubSpotDaemon(_portal(), sock_path=_short_sock("warm"), idle_timeout=30)
    await daemon._warm()
    try:
        assert discovered == [True]
        assert daemon.client is not None
        assert daemon.cache is not None
    finally:
        if daemon.client is not None:
            await daemon.client.close()


@pytest.mark.asyncio
async def test_daemon_idle_self_exit(env, tmp_path):
    sock = _short_sock("idle")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=0.4)
    _fake_warm(daemon)
    await asyncio.wait_for(daemon.serve(), timeout=5)
    # Idle timeout with no connections → self-exit, socket + pid cleaned up.
    assert not sock.exists()
    assert not pid_path().exists()


@pytest.mark.asyncio
async def test_daemon_loop_status_rpc(env, tmp_path):
    sock = _short_sock("loop")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        reader, writer = await asyncio.open_unix_connection(str(sock))
        writer.write((json.dumps({"method": "loop_status", "params": {}, "id": 7}) + "\n").encode("utf-8"))
        await writer.drain()
        resp = json.loads(await reader.readline())
        assert resp["id"] == 7
        # No loop exists → not_found error (NFR-15 shape).
        assert resp["error"]["kind"] == "not_found"
        writer.close()
        await writer.wait_closed()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)


# ---------------------------------------------------------------------------
# #2: SIGTERM/SIGINT handlers attached to the running loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daemon_signal_handlers_attached_to_running_loop(env, monkeypatch):
    # #2: signal handlers must be registered on the loop asyncio.run actually
    # runs (the running loop), and the callback must trip _stop for a clean
    # shutdown.  Verifies wiring without sending a real OS signal.
    daemon = HubSpotDaemon(_portal(), sock_path=_short_sock("sig"), idle_timeout=30)
    loop = asyncio.get_running_loop()
    registered: list[tuple] = []

    def _spy(sig, callback, *args):
        registered.append((sig, callback))

    monkeypatch.setattr(loop, "add_signal_handler", _spy)
    await daemon._install_signal_handlers()
    sigs = [s for s, _ in registered]
    assert signal.SIGTERM in sigs
    assert signal.SIGINT in sigs
    # The SIGTERM callback triggers the clean-stop path.
    term_cb = [cb for s, cb in registered if s == signal.SIGTERM][0]
    assert daemon._stop.is_set() is False
    term_cb()
    assert daemon._stop.is_set() is True


@pytest.mark.asyncio
async def test_daemon_stop_closes_warm_client(env, tmp_path):
    # #2: a clean shutdown (the path SIGTERM now triggers) must close the warm
    # HubSpotClient gracefully via serve()'s finally block.
    sock = _short_sock("close")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    closed = {"count": 0}

    class _Client:
        async def close(self):
            closed["count"] += 1

    async def _warm(self):
        self.client = _Client()
        self.cache = None

    daemon._warm = types.MethodType(_warm, daemon)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            daemon._stop.set()
            await asyncio.wait_for(task, timeout=5)
    assert closed["count"] == 1  # warm client closed on shutdown
    assert not sock.exists()
    assert not pid_path().exists()


# ---------------------------------------------------------------------------
# #3: PID file written before socket bind (startup TOCTOU)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daemon_writes_pid_before_binding_socket(env, tmp_path, monkeypatch):
    # #3: the PID file must exist before the socket is bound so a concurrent
    # is_daemon_alive() caller trusts a live PID and does not unlink the socket.
    sock = _short_sock("pidorder")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)
    pid_existed_at_bind = {"v": False}
    real_start = asyncio.start_unix_server

    async def _spy(handler, *, path=None, **kw):
        pid_existed_at_bind["v"] = pid_path().exists()
        return await real_start(handler, path=path, **kw)

    monkeypatch.setattr(asyncio, "start_unix_server", _spy)
    task = asyncio.create_task(daemon.serve())
    try:
        await _wait_for_socket(sock)
        assert pid_existed_at_bind["v"] is True  # PID written before bind
        assert pid_path().exists()
    finally:
        daemon._stop.set()
        await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_daemon_bind_failure_cleans_pid_file(env, tmp_path, monkeypatch):
    # #3: if the socket bind fails, the PID file written just before it must be
    # removed so it doesn't read as a stale live daemon.
    sock = _short_sock("bindfail")
    daemon = HubSpotDaemon(_portal(), sock_path=sock, idle_timeout=30)
    _fake_warm(daemon)

    async def _fail(handler, *, path=None, **kw):
        raise OSError("bind failed")

    monkeypatch.setattr(asyncio, "start_unix_server", _fail)
    # _warm runs (fake ok); _serve_forever writes PID, bind raises, PID unlinked,
    # OSError propagates out of serve() after its finally closes the fake client.
    with pytest.raises(OSError):
        await daemon.serve()
    assert not pid_path().exists()