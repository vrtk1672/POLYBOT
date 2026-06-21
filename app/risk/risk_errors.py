class RiskError(Exception):
    """Base V2.14 risk exception."""


class RiskEvaluationBlocked(RiskError):
    """Raised when runtime state blocks risk evaluation."""


class ManualOverrideRejected(RiskError):
    """Raised when an unsafe or unaudited manual override is requested."""

