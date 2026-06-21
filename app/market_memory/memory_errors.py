class MarketMemoryError(RuntimeError):
    """Base error for Market Memory V2."""


class MarketMemoryBlocked(MarketMemoryError):
    """Raised when runtime mode blocks memory rebuild."""

