import threading
import time
import urllib.request

from hubspot_agent.callback_server import run_callback_server


def test_callback_server_receives_code():
    server_thread = threading.Thread(target=lambda: None)
    server_thread.start()
    time.sleep(0.2)

    # Start server in background
    from hubspot_agent.callback_server import run_callback_server

    result = {"code": None}

    def server_runner():
        try:
            result["code"] = run_callback_server(port=13001, timeout=5.0)
        except Exception:
            pass

    runner = threading.Thread(target=server_runner)
    runner.start()
    time.sleep(0.3)

    # Simulate browser callback
    urllib.request.urlopen("http://127.0.0.1:13001/oauth/callback?code=test-code-123")
    runner.join(timeout=3.0)

    assert result["code"] == "test-code-123"


def test_callback_server_timeout():
    from hubspot_agent.callback_server import run_callback_server
    import pytest

    with pytest.raises(TimeoutError):
        run_callback_server(port=13002, timeout=0.5)
