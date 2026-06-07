import pytest

from hubspot_agent.orchestrator import _normalize_informing_sources


class TestNormalizeInformingSources:
    def test_empty_returns_empty(self):
        assert _normalize_informing_sources(None) == []
        assert _normalize_informing_sources([]) == []

    def test_official_url_corrected_to_official(self):
        sources = [
            {
                "source": "community",
                "trust_tier": "community-unverified",
                "title": "Contacts API",
                "url": "https://developers.hubspot.com/docs/api/crm/contacts",
                "last_updated": "2026-05-01",
            }
        ]
        result = _normalize_informing_sources(sources)
        assert result[0]["source"] == "official"
        assert result[0]["trust_tier"] == "official"

    def test_community_url_downgraded_from_official(self):
        sources = [
            {
                "source": "official",
                "trust_tier": "official",
                "title": "Random Post",
                "url": "https://community.hubspot.com/t5/abc",
                "last_updated": "2026-05-01",
            }
        ]
        result = _normalize_informing_sources(sources)
        assert result[0]["source"] == "community"
        assert result[0]["trust_tier"] == "community-unverified"

    def test_mixed_sources_preserved(self):
        sources = [
            {
                "source": "official",
                "trust_tier": "official",
                "title": "Docs",
                "url": "https://developers.hubspot.com/docs",
                "last_updated": "2026-05-01",
            },
            {
                "source": "community",
                "trust_tier": "community-accepted",
                "title": "Forum Post",
                "url": "https://community.hubspot.com/t5/abc",
                "last_updated": "2026-04-01",
            },
        ]
        result = _normalize_informing_sources(sources)
        assert result[0]["source"] == "official"
        assert result[0]["trust_tier"] == "official"
        assert result[1]["source"] == "community"
        assert result[1]["trust_tier"] == "community-accepted"

    def test_unknown_domain_defaults_to_community_unverified(self):
        sources = [
            {
                "source": "official",
                "trust_tier": "official",
                "title": "Stack Overflow",
                "url": "https://stackoverflow.com/questions/123",
                "last_updated": "2026-05-01",
            }
        ]
        result = _normalize_informing_sources(sources)
        assert result[0]["source"] == "community"
        assert result[0]["trust_tier"] == "community-unverified"
