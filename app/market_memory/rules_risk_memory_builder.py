from __future__ import annotations

from typing import Any

from app.market_memory.contracts import RulesRiskMemory, avg, bounded


class RulesRiskMemoryBuilder:
    def build(self, rows: list[dict[str, Any]], *, market_id: str | None = None, market_family: str | None = None) -> RulesRiskMemory:
        wording = avg([row.get("wording_risk") for row in rows])
        dispute = avg([row.get("dispute_risk") for row in rows])
        clarity = avg([row.get("resolution_clarity") for row in rows])
        ambiguous = sum(len(row.get("ambiguous_terms_json") or []) for row in rows)
        edge_cases = sum(len(row.get("edge_cases_json") or []) for row in rows)
        risk = bounded(((wording or 0) * 0.4) + ((dispute or 0) * 0.35) + ((1 - (clarity or 0)) * 0.25))
        rules_block_rate = _rate([str(row.get("recommendation") or "").upper() == "NO_TRADE" for row in rows])
        return RulesRiskMemory(
            market_id=market_id,
            market_family=market_family,
            observations_count=len(rows),
            avg_wording_risk=wording,
            avg_dispute_risk=dispute,
            avg_resolution_clarity=clarity,
            ambiguous_terms_count=ambiguous,
            edge_case_count=edge_cases,
            rules_block_rate=rules_block_rate,
            rules_risk_score=risk if rows else 0.0,
            confidence=bounded(len(rows) / 10),
            summary={"source": "v2.9", "insufficient_data": not rows, "rules_block_rate": rules_block_rate},
        )


def _rate(values: list[bool]) -> float:
    return 0.0 if not values else bounded(sum(1 for value in values if value) / len(values))
