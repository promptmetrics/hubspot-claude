class HubSpotError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def __str__(self) -> str:
        return f"HubSpotError({self.status_code}): {self.message}"


class RateLimitError(HubSpotError):
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ScopeError(HubSpotError):
    def __init__(self, message: str, required_scopes: list[str] | None = None):
        super().__init__(message, status_code=403)
        self.required_scopes = required_scopes or []
