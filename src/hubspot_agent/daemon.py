"""Warm-client HubSpot daemon — a Unix-socket JSON-RPC server (FR-15/FR-16).

Holds ONE warm ``HubSpotClient`` + ONE ``cache.SchemaCache`` for a portal and
serves line-delimited JSON-RPC requests ``{method, params, id}`` →
``{id, result}`` / ``{id, error}``.  All request handling delegates to the
shared :mod:`hubspot_agent.handlers` so the daemon, in-process fallback, and CLI
sync path share one implementation.

Lifecycle:
- stale-socket cleanup on start (unlink if no live PID owns it);
- PID file written on start, removed on exit;
- idle self-exit after ``idle_timeout`` seconds with no connections (default 600);
- ``serve_stop`` RPC triggers a clean shutdown.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from hubspot_agent.cache import SchemaCache, discover_custom_schemas, warm_standard_schemas
from hubspot_agent.client import HubSpotClient
from hubspot_agent.config import PortalConfig
from hubspot_agent.handlers import HANDLERS, HandlerError


def plugin_data_dir() -> Path:
    """Resolve the plugin's per-user data directory."""
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "plugins" / "data" / "hubspot"


def socket_path() -> Path:
    return plugin_data_dir() / "hubspot.sock"


def pid_path() -> Path:
    return plugin_data_dir() / "hubspot.pid"


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


def cleanup_stale_socket(path: Path | None = None) -> bool:
    """Remove the socket file if no live daemon owns it.  Returns True if removed."""
    path = path or socket_path()
    if not path.exists():
        return False
    pid_file = pid_path()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pid = 0
        if _pid_alive(pid):
            return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


class HubSpotDaemon:
    """Async Unix-socket JSON-RPC daemon with one warm client + cache."""

    def __init__(
        self,
        portal_config: PortalConfig,
        *,
        sock_path: Path | None = None,
        idle_timeout: float = 600.0,
    ) -> None:
        self.portal_config = portal_config
        self.sock_path = sock_path or socket_path()
        self.idle_timeout = idle_timeout
        self.client: HubSpotClient | None = None
        self.cache: SchemaCache | None = None
        self._server: asyncio.AbstractServer | None = None
        self._last_activity = time.monotonic()
        self._stop = asyncio.Event()

    async def _warm(self) -> None:
        self.cache = await warm_standard_schemas(self.portal_config)
        # Discover custom object schemas so the warm cache (and the on-disk
        # SchemaCache the tools validate against) knows custom types, not just
        # WARM_DOMAINS.  Mirrors orchestrator.initialize_session on the agent path.
        await discover_custom_schemas(self.portal_config)
        self.client = HubSpotClient(self.portal_config)

    async def _serve_forever(self) -> None:
        self.sock_path.parent.mkdir(parents=True, exist_ok=True)
        cleanup_stale_socket(self.sock_path)
        self.sock_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the PID file BEFORE binding the socket.  router.is_daemon_alive
        # trusts a live PID over socket existence, so during the bind window a
        # concurrent caller sees a live PID (not a stale socket) and does not
        # unlink the just-bound socket.  Closes the startup TOCTOU race (#3).
        pid_path().parent.mkdir(parents=True, exist_ok=True)
        pid_path().write_text(str(os.getpid()))
        try:
            self._server = await asyncio.start_unix_server(self._handle_conn, path=str(self.sock_path))
        except OSError:
            # Bind failed — no daemon owns the socket; drop the PID we wrote so
            # cleanup_stale_socket / a later start isn't confused by a stale PID.
            pid_path().unlink(missing_ok=True)
            raise
        try:
            self.sock_path.chmod(0o600)
        except OSError:
            pass

        watchdog = asyncio.create_task(self._idle_watchdog())
        stop_wait = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait({stop_wait, watchdog}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watchdog.cancel()
            stop_wait.cancel()
            self._server.close()
            await self._server.wait_closed()
            try:
                if self.sock_path.exists():
                    self.sock_path.unlink()
            except OSError:
                pass
            try:
                pid_path().unlink(missing_ok=True)
            except OSError:
                pass

    async def _idle_watchdog(self) -> None:
        while True:
            remaining = self.idle_timeout - (time.monotonic() - self._last_activity)
            if remaining <= 0:
                self._stop.set()
                return
            await asyncio.sleep(min(remaining, 1.0))

    async def _handle_conn(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._last_activity = time.monotonic()
        try:
            while not reader.at_eof():
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=self.idle_timeout)
                except asyncio.TimeoutError:
                    break
                if not line:
                    break
                self._last_activity = time.monotonic()
                response = await self._process_line(line)
                writer.write((json.dumps(response, default=str) + "\n").encode("utf-8"))
                await writer.drain()
                if response.get("_stop"):
                    break
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass

    async def _process_line(self, line: bytes) -> dict[str, Any]:
        try:
            req = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"id": None, "error": {"kind": "validation", "message": f"Malformed JSON-RPC: {exc}", "retryable": False}}

        if not isinstance(req, dict):
            return {
                "id": None,
                "error": {"kind": "validation", "message": "JSON-RPC payload must be an object", "retryable": False},
            }

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        if method not in HANDLERS:
            return {
                "id": req_id,
                "error": {"kind": "not_found", "message": f"Unknown method: {method}", "retryable": False},
            }
        try:
            result = await HANDLERS[method](self.client, self.cache, self.portal_config, params)
        except HandlerError as exc:
            return {"id": req_id, "error": exc.error}
        except Exception as exc:  # pragma: no cover - defensive envelope
            return {"id": req_id, "error": {"kind": "server", "message": str(exc), "retryable": True}}

        response: dict[str, Any] = {"id": req_id, "result": result}
        if method == "serve_stop":
            self._stop.set()
            response["_stop"] = True
        return response

    async def serve(self) -> None:
        await self._install_signal_handlers()
        try:
            await self._warm()
        except Exception as exc:
            print(f"hubspot daemon: failed to warm client/cache: {exc}", file=sys.stderr)
            return
        try:
            await self._serve_forever()
        finally:
            if self.client is not None:
                await self.client.close()

    async def _install_signal_handlers(self) -> None:
        """Register SIGTERM/SIGINT to trigger a clean stop on the running loop.

        Must be called from inside the running loop (it is, from ``serve()``)
        so ``add_signal_handler`` binds to the loop ``asyncio.run`` actually
        runs.  Registering before ``asyncio.run`` (the old approach) bound the
        handler to a never-run loop, so SIGTERM fell through to the default OS
        action and the warm client was never closed gracefully (#2).
        """
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except (NotImplementedError, RuntimeError):
                # Not supported on this platform (e.g. Windows) — serve_stop and
                # the idle watchdog still provide clean shutdown paths.
                pass


async def serve(portal_config: PortalConfig, *, sock_path: Path | None = None, idle_timeout: float = 600.0) -> None:
    """Entrypoint: run a daemon until idle-timeout or ``serve_stop``."""
    daemon = HubSpotDaemon(portal_config, sock_path=sock_path, idle_timeout=idle_timeout)
    await daemon.serve()


def main(argv: list[str] | None = None) -> int:
    """``python -m hubspot_agent.daemon <portal_id>`` — run the daemon."""
    import argparse

    from hubspot_agent.config import load_portal_config

    parser = argparse.ArgumentParser(prog="hubspot-agent-daemon")
    parser.add_argument("portal_id")
    parser.add_argument("--idle-timeout", type=float, default=600.0)
    args = parser.parse_args(argv)

    portal_config = load_portal_config(args.portal_id)
    if portal_config is None:
        print(f"No config for portal {args.portal_id}", file=sys.stderr)
        return 2

    daemon = HubSpotDaemon(portal_config, idle_timeout=args.idle_timeout)

    try:
        asyncio.run(daemon.serve())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())