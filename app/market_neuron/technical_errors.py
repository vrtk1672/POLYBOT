class MarketNeuronError(RuntimeError):
    """Base error for V2.8 market technical neurons."""


class MarketNeuronBlocked(MarketNeuronError):
    """Raised when runtime mode blocks market technical analysis."""

