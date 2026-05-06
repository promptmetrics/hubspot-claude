from __future__ import annotations

import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/oauth/callback":
            if "code" in params:
                _CallbackHandler.code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this tab.</p>")
            elif "error" in params:
                _CallbackHandler.error = params["error"][0]
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization failed.</h1><p>Please check the CLI.</p>")
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def run_callback_server(port: int = 3000, timeout: float = 300.0) -> str:
    _CallbackHandler.code = None
    _CallbackHandler.error = None

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _CallbackHandler.code is not None:
                return _CallbackHandler.code
            if _CallbackHandler.error is not None:
                raise RuntimeError(f"OAuth error: {_CallbackHandler.error}")
            time.sleep(0.5)
        raise TimeoutError("OAuth callback timed out — no code received.")
    finally:
        server.shutdown()
