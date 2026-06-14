from unittest.mock import patch

import pytest

from hubspot_agent.cli import hubspot_command


def _setup_portal(tmp_path, monkeypatch):
    portal_file = tmp_path / ".hubspot-portal"
    portal_file.write_text("123\n")
    monkeypatch.setenv("HUBSPOT_TOKEN_123", "test-token")


def _async_return(value):
    async def _coro(*args, **kwargs):
        return value
    return _coro


@pytest.mark.asyncio
async def test_cli_loop_flag_runs_run_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)

    with patch("hubspot_agent.cli.run_loop", side_effect=_async_return("loop result")) as mock_run_loop:
        result = hubspot_command("--loop create property and workflow", working_dir=str(tmp_path))

    assert result == "loop result"
    mock_run_loop.assert_called_once()


@pytest.mark.asyncio
async def test_cli_multi_agent_defaults_to_loop(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)

    with patch("hubspot_agent.cli.run_loop", side_effect=_async_return("loop result")) as mock_run_loop:
        result = hubspot_command("create a property and build a workflow", working_dir=str(tmp_path))

    assert result == "loop result"
    mock_run_loop.assert_called_once()


@pytest.mark.asyncio
async def test_cli_single_agent_uses_flat_path(tmp_path, monkeypatch):
    _setup_portal(tmp_path, monkeypatch)

    with patch("hubspot_agent.cli.run_loop") as mock_run_loop:
        result = hubspot_command("find contacts", working_dir=str(tmp_path))

    assert "objects" in result
    mock_run_loop.assert_not_called()


def test_cli_loop_flag_stripped_before_portal_check():
    with patch("hubspot_agent.cli.run_loop") as mock_run_loop:
        result = hubspot_command("--loop find contacts", working_dir="/nonexistent")
    assert "No default portal found" in result
    mock_run_loop.assert_not_called()
