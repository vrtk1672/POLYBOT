class NoTradeError(Exception):
    """Base V2.17 no-trade error."""


class NoTradeValidationError(NoTradeError):
    """Raised when a no-trade decision is missing required audit fields."""
