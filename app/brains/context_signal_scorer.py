from __future__ import annotations

from typing import Any

from app.brains.contracts import ContextBrainInput, ContextBrainOutput, bounded


class ContextSignalScorer:
    def score(self, payload: ContextBrainInput) -> ContextBrainOutput:
        supporting: list[dict[str, Any]] = []
        contradicting: list[dict[str, Any]] = []
        risks = list(payload.insufficient_data_reasons)
        if not any([payload.news_signals, payload.social_signals, payload.whale_signals, payload.technical_signals]):
            return ContextBrainOutput(
                market_id=payload.market_id,
                insufficient_data=True,
                insufficient_data_reasons=risks or ["missing_context_signals"],
                explanation="No reliable context signals were available.",
            )

        strength = 0.0
        confidence = 0.0
        direction_votes: list[str] = []
        already_priced = 0.0
        ttl = 3600
        urgency = 0.0

        for row in payload.news_signals:
            score = bounded(row.get("strength") or row.get("impact_score") or row.get("confidence"))
            priced = bounded(row.get("already_priced_in"))
            strength += score * 0.35 * (1 - priced)
            confidence += bounded(row.get("confidence"), 0.3) * 0.25
            already_priced = max(already_priced, priced)
            ttl = max(ttl, int(row.get("ttl_seconds") or 0))
            urgency = max(urgency, bounded(row.get("urgency")))
            direction_votes.append(str(row.get("direction") or "UNKNOWN").upper())
            supporting.append({"source": "news", "score": score, "priced_in": priced})

        for row in payload.social_signals:
            hype = bounded(row.get("hype_pressure"))
            bot = bounded(row.get("bot_risk"))
            spam = bounded(row.get("spam_ratio"))
            useful = hype * (1 - max(bot, spam))
            strength += useful * 0.15
            confidence += bounded(row.get("confidence"), 0.2) * (1 - max(bot, spam)) * 0.12
            if bot > 0.5 or spam > 0.5:
                risks.append("noisy_social_signal")
            direction_votes.append(str(row.get("sentiment") or "UNKNOWN").upper())
            supporting.append({"source": "social", "score": useful, "bot_risk": bot, "spam_ratio": spam})

        whale_memory = payload.memory_snapshot.get("whale_memory") or {}
        whale_memory_score = bounded(whale_memory.get("whale_score") or whale_memory.get("follow_value_avg"))
        whale_memory_confidence = bounded(whale_memory.get("confidence"))
        for row in payload.whale_signals:
            follow = bounded(row.get("follow_value"))
            size_only_penalty = 0.2 if whale_memory_confidence <= 0 else 1.0
            useful = follow * max(whale_memory_score, 0.1) * max(whale_memory_confidence, 0.1) * size_only_penalty
            strength += useful * 0.25
            confidence += whale_memory_confidence * 0.15
            direction_votes.append(str(row.get("side") or "UNKNOWN").upper())
            supporting.append({"source": "whale", "score": useful, "memory_confidence": whale_memory_confidence})

        for row in payload.technical_signals:
            tech_score = bounded(row.get("technical_score") or row.get("momentum_score"))
            strength += tech_score * 0.2
            confidence += bounded(row.get("data_completeness_score"), payload.data_completeness_score) * 0.12
            if row.get("technical_blocked") is True:
                risks.append("technical_block")
                confidence *= 0.7
            supporting.append({"source": "technical", "score": tech_score, "blocked": bool(row.get("technical_blocked"))})

        rules = (payload.memory_snapshot.get("rules_risk_memory") or payload.rules_signals or [{}])[0] if isinstance(payload.memory_snapshot.get("rules_risk_memory"), list) else payload.memory_snapshot.get("rules_risk_memory", {})
        wording_risk = bounded((rules or {}).get("rules_risk_score") or (rules or {}).get("avg_wording_risk"))
        if wording_risk >= 0.6:
            risks.append("high_wording_risk")
            confidence *= 0.7
        memory_confidence = bounded(payload.memory_snapshot.get("confidence") or payload.memory_snapshot.get("memory_confidence"))
        confidence = bounded((confidence + memory_confidence * 0.2) * payload.data_completeness_score)
        risk_score = bounded((wording_risk * 0.35) + (already_priced * 0.35) + (0.2 if "technical_block" in risks else 0))
        strength = bounded(strength * (1 - risk_score * 0.35))
        context_shift = strength >= 0.25 and confidence >= 0.2 and already_priced < 0.8
        direction = _direction(direction_votes)
        if direction == "UNKNOWN" and not context_shift:
            direction = "NONE"
        return ContextBrainOutput(
            market_id=payload.market_id,
            context_shift=context_shift,
            direction=direction,
            strength=strength,
            confidence=confidence,
            already_priced_in_score=already_priced,
            ttl_seconds=ttl,
            urgency_score=urgency,
            risk_score=risk_score,
            risks=risks,
            supporting_signals=supporting,
            contradicting_signals=contradicting,
            insufficient_data=bool(payload.insufficient_data_reasons),
            insufficient_data_reasons=payload.insufficient_data_reasons,
            ai_context_summary=(payload.ai_analysis or {}).get("summary") if payload.ai_analysis else None,
            explanation="Context shift detected." if context_shift else "No real context shift detected.",
        )


def _direction(votes: list[str]) -> str:
    clean = [vote for vote in votes if vote in {"YES", "NO"}]
    if not clean:
        return "UNKNOWN"
    yes = clean.count("YES")
    no = clean.count("NO")
    if yes and no and yes == no:
        return "BOTH"
    return "YES" if yes > no else "NO"
