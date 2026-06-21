class CapitalError(Exception):
    """Base V2.13 capital exception."""


class CapitalAllocationBlocked(CapitalError):
    """Raised when runtime state blocks capital intelligence."""

