class RulesNeuronError(Exception):
    """Base error for the Rules Neuron."""


class RulesAnalysisBlocked(RulesNeuronError):
    """Raised when runtime mode blocks rules analysis."""
