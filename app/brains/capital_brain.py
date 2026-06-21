from app.brains.capital_recommendation_builder import CapitalRecommendationBuilder
from app.brains.contracts import CapitalBrainInput, CapitalBrainOutput


class CapitalBrain:
    def __init__(self, builder: CapitalRecommendationBuilder | None = None) -> None:
        self._builder = builder or CapitalRecommendationBuilder()

    def analyze(self, payload: CapitalBrainInput) -> CapitalBrainOutput:
        return self._builder.build(payload)
