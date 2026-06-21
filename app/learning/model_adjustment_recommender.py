from __future__ import annotations

from app.learning.contracts import EngineLearning, ModelAdjustment, NoTradeLearning, SignalPerformance


class ModelAdjustmentRecommender:
    def from_engine_learning(self, learning: EngineLearning) -> ModelAdjustment | None:
        if learning.learning_signal not in {"penalize_engine", "reward_engine", "insufficient_data"}:
            return None
        if learning.learning_signal == "insufficient_data":
            return ModelAdjustment(
                adjustment_type="data_coverage",
                target_module="learning",
                target_key=learning.engine,
                recommended_value="improve_data",
                reason="Engine learning lacks enough outcome evidence.",
                evidence=learning.model_dump(mode="json"),
                confidence=learning.confidence,
                status="REVIEW_REQUIRED",
            )
        return ModelAdjustment(
            adjustment_type="engine_weight",
            target_module="strategy_engine",
            target_key=learning.engine,
            recommended_value="decrease" if learning.learning_signal == "penalize_engine" else "increase",
            reason=learning.explanation,
            evidence=learning.model_dump(mode="json"),
            confidence=learning.confidence,
            status="RECOMMENDED",
        )

    def from_signal_performance(self, performance: SignalPerformance) -> ModelAdjustment | None:
        if performance.false_positive and performance.confidence >= 0.6:
            return ModelAdjustment(
                adjustment_type="signal_weight",
                target_module=performance.source_type,
                target_key=performance.signal_type,
                recommended_value="decrease",
                reason="Signal produced a false positive against observed outcome.",
                evidence=performance.model_dump(mode="json"),
                confidence=performance.confidence,
            )
        return None

    def from_no_trade_learning(self, learning: NoTradeLearning) -> ModelAdjustment | None:
        if learning.confidence < 0.55:
            return None
        return ModelAdjustment(
            adjustment_type="no_trade_filter",
            target_module="no_trade",
            target_key=learning.candidate_engine,
            recommended_value=learning.suggested_filter_change,
            reason=learning.explanation,
            evidence=learning.model_dump(mode="json"),
            confidence=learning.confidence,
            status="RECOMMENDED",
        )
