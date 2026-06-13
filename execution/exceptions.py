class BybitConfigError(Exception):
    """Raised when local Bybit configuration is missing or invalid."""


class BybitAPIError(Exception):
    """Raised when Bybit returns a non-zero retCode or invalid response."""
