from app.brains.context_signal_scorer import ContextSignalScorer
from app.brains.contracts import ContextBrainInput, ContextBrainOutput


class ContextBrain:
    def __init__(self, scorer: ContextSignalScorer | None = None) -> None:
        self._scorer = scorer or ContextSignalScorer()

    def analyze(self, payload: ContextBrainInput) -> ContextBrainOutput:
        output = self._scorer.score(payload)
        if output.ai_context_summary and (output.risk_score >= 0.5 or output.risks):
            output.risks.append("ai_cannot_override_risk")
            output.context_shift = output.context_shift and output.risk_score < 0.8
        return output
