def test_hubspot_error_str():
    from hubspot_agent.errors import HubSpotError
    exc = HubSpotError("something failed", status_code=400)
    assert str(exc) == "HubSpotError(400): something failed"


def test_rate_limit_error():
    from hubspot_agent.errors import RateLimitError
    exc = RateLimitError("Rate limit exceeded", retry_after=30)
    assert exc.status_code == 429
    assert exc.retry_after == 30


def test_scope_error():
    from hubspot_agent.errors import ScopeError
    exc = ScopeError("Missing scopes", required_scopes=["crm.objects.contacts.read"])
    assert exc.status_code == 403
    assert exc.required_scopes == ["crm.objects.contacts.read"]
