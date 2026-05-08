from __future__ import annotations

from unittest.mock import patch

import pytest

from hubspot_agent.config import PortalConfig
from hubspot_agent.tour import run_tour


@pytest.fixture
def portal_config() -> PortalConfig:
    return PortalConfig(portal_id="123", token="fake-token")


class TestRunTour:
    def test_tour_contains_title(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "# Welcome to the HubSpot Agent Tour" in text
        assert "Portal: 123" in text

    def test_tour_has_seven_steps(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        for i in range(1, 8):
            assert f"{i}." in text

    def test_tour_includes_read_examples(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "find all contacts" in text
        assert "get pipeline stages for deals" in text
        assert "objects" in text
        assert "pipelines" in text

    def test_tour_includes_write_previews(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "update contact 123 email to alice@example.com" in text
        assert "create a new company named Acme Inc" in text
        assert "MEDIUM" in text

    def test_tour_includes_batch_mode(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "batch update contacts --batch" in text
        assert "Batch mode" in text
        assert "Approve entire plan" in text

    def test_tour_includes_workflow_blueprint(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "create a welcome email workflow" in text
        assert "workflows" in text

    def test_tour_includes_approval_explanation(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "Approval flow explained" in text
        assert "Every write operation stops for your approval" in text

    def test_tour_has_next_steps(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "Next steps" in text
        assert "/hubspot find contacts" in text
        assert "/hubspot status" in text
        assert "Tour complete!" in text

    def test_tour_does_not_make_live_changes(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        assert "None of these examples make live changes" in text

    def test_tour_previews_are_simulated(self, portal_config):
        text = run_tour("123", portal_config=portal_config)
        # Simulated previews should show impact counts and prompts
        assert "Impact:" in text
        assert "Approve?" in text
