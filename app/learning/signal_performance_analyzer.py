from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.learning.contracts import SignalPerformance


class SignalPerformanceAnalyzer:
    def analyze(self, signal: dict[str, Any], *, market_id: str | None = None, market_family: str | None = None) -> SignalPerformance:
        direction = str(signal.get("direction") or signal.get("predicted_direction") or "").upper()
        observed_direction = str(signal.get("observed_direction") or "").upper()
        observed_move = float(signal.get("observed_move") or 0)
        predicted_strength = float(signal.get("predicted_strength") or signal.get("strength") or 0)
        if not observed_direction:
            observed_direction = "UP" if observed_move > 0 else "DOWN" if observed_move < 0 else "FLAT"
        correct_direction = bool(direction) and direction == observed_direction
        magnitude_score = min(1.0, abs(observed_move) / max(abs(predicted_strength), 0.01)) if predicted_strength else 0.5
        accuracy = 0.75 * (1.0 if correct_direction else 0.0) + 0.25 * min(1.0, magnitude_score)
        usefulness = max(0.0, min(1.0, accuracy * float(signal.get("confidence") or 0.75)))
        return SignalPerformance(
            signal_perf_id=signal.get("signal_perf_id") or f"sig_{uuid4().hex}",
            source_type=str(signal.get("source_type") or "technical"),
            source_id=signal.get("source_id"),
            signal_type=str(signal.get("signal_type") or "directional"),
            market_id=signal.get("market_id") or market_id,
            market_family=signal.get("market_family") or market_family,
            direction=direction or None,
            predicted_strength=predicted_strength,
            observed_move=observed_move,
            observed_direction=observed_direction,
            accuracy_score=round(accuracy, 8),
            usefulness_score=round(usefulness, 8),
            false_positive=bool(direction and not correct_direction and predicted_strength > 0),
            false_negative=bool((not direction or predicted_strength <= 0) and abs(observed_move) > 0.05),
            latency_seconds=signal.get("latency_seconds"),
            confidence=float(signal.get("confidence") or 0.75),
            evidence=signal,
        )
