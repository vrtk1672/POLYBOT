from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.connection import DatabaseConnectionFactory
from app.repositories.compliance_block_repository import ComplianceBlockRepository
from app.repositories.market_rules_repository import MarketRulesRepository
from app.repositories.rules_ai_analysis_repository import RulesAIAnalysisRepository
from app.repositories.rules_analysis_repository import RulesAnalysisRepository
from app.repositories.wording_risk_repository import WordingRiskRepository
from app.rules_neuron.service import RulesNeuronService


class AnalyzeRulesRequest(BaseModel):
    market_id: str = Field(min_length=1)
    allow_ai: bool = False
    reason: str = Field(min_length=1)


class AnalyzeAllRulesRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    allow_ai: bool = False
    reason: str = Field(min_length=1)


def create_rules_router(*, connection_factory: DatabaseConnectionFactory | None = None, rules_service: RulesNeuronService | None = None) -> APIRouter:
    router = APIRouter(prefix="/rules", tags=["rules-neuron"])
    factory = connection_factory or DatabaseConnectionFactory()
    service = rules_service or RulesNeuronService(connection_factory=factory)
    analyses = RulesAnalysisRepository()
    blocks = ComplianceBlockRepository()
    market_rules = MarketRulesRepository()
    wording = WordingRiskRepository()
    ai_repo = RulesAIAnalysisRepository()

    @router.get("/market/{market_id}")
    async def rules_for_market(market_id: str) -> dict[str, Any]:
        if not factory.enabled:
            raise HTTPException(status_code=404, detail="market not found")
        with factory.connect() as conn:
            rules = market_rules.get_rules(conn, market_id)
            latest = analyses.get_latest(conn, market_id)
            latest_wording = wording.get_latest(conn, market_id)
            block_rows = blocks.list_for_market(conn, market_id)
            ai_rows = ai_repo.list_for_market(conn, market_id, limit=20)
        if latest is None and rules is None:
            raise HTTPException(status_code=404, detail="rules analysis not found")
        return {
            "market_id": market_id,
            "latest_market_rules": _serialize(rules),
            "latest_rules_analysis": _serialize(latest),
            "wording_risk": _serialize(latest_wording),
            "dispute_risk": latest.get("dispute_risk") if latest else None,
            "resolution_clarity": latest.get("resolution_clarity") if latest else None,
            "compliance_status": latest.get("compliance_status") if latest else None,
            "recommendation": latest.get("recommendation") if latest else None,
            "compliance_blocks": [_serialize(row) for row in block_rows],
            "dangerous_edge_cases": latest.get("dangerous_edge_cases_json") if latest else [],
            "ai_analysis": [_serialize(row) for row in ai_rows],
        }

    @router.get("/analysis/recent")
    async def recent_analysis(
        limit: int = Query(default=100, ge=1, le=500),
        recommendation: str | None = None,
        compliance_status: str | None = None,
        min_wording_risk: float | None = Query(default=None, ge=0, le=1),
        min_dispute_risk: float | None = Query(default=None, ge=0, le=1),
    ) -> dict[str, Any]:
        if not factory.enabled:
            return {"items": [], "count": 0}
        with factory.connect() as conn:
            rows = analyses.list_recent(conn, limit=limit, recommendation=recommendation, compliance_status=compliance_status, min_wording_risk=min_wording_risk, min_dispute_risk=min_dispute_risk)
        return {"items": [_serialize(row) for row in rows], "count": len(rows)}

    @router.get("/blocks")
    async def rules_blocks(active: bool | None = True, severity: str | None = None, block_type: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        if not factory.enabled:
            return {"blocks": [], "count": 0}
        with factory.connect() as conn:
            rows = blocks.list_blocks(conn, active=active, severity=severity, block_type=block_type, limit=limit)
        return {"blocks": [_serialize(row) for row in rows], "count": len(rows)}

    @router.get("/coverage")
    async def rules_coverage() -> dict[str, Any]:
        if not factory.enabled:
            return _empty_coverage()
        with factory.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM markets_v2) AS total_markets,
                    (SELECT COUNT(DISTINCT market_id) FROM market_rules WHERE rules_text IS NOT NULL AND rules_text <> '') AS markets_with_rules,
                    (SELECT COUNT(DISTINCT market_id) FROM rules_analysis) AS markets_with_analysis,
                    (SELECT COUNT(*) FROM market_rules WHERE rules_text IS NULL OR rules_text = '') AS missing_rules_count,
                    (SELECT COUNT(*) FROM rules_analysis WHERE wording_risk >= 0.75) AS high_wording_risk_count,
                    (SELECT COUNT(*) FROM rules_analysis WHERE dispute_risk >= 0.75) AS high_dispute_risk_count,
                    (SELECT COUNT(*) FROM compliance_blocks WHERE active = true) AS compliance_block_count,
                    (SELECT AVG(resolution_clarity) FROM rules_analysis) AS average_resolution_clarity,
                    (SELECT MAX(created_at) FROM rules_analysis) AS latest_rules_analysis_at
                """
            ).fetchone()
        total = int(row["total_markets"] or 0)
        return {
            "total_markets": total,
            "markets_with_rules": int(row["markets_with_rules"] or 0),
            "markets_with_analysis": int(row["markets_with_analysis"] or 0),
            "rules_coverage_pct": _pct(row["markets_with_rules"], total),
            "missing_rules_count": int(row["missing_rules_count"] or 0),
            "high_wording_risk_count": int(row["high_wording_risk_count"] or 0),
            "high_dispute_risk_count": int(row["high_dispute_risk_count"] or 0),
            "compliance_block_count": int(row["compliance_block_count"] or 0),
            "average_resolution_clarity": float(row["average_resolution_clarity"] or 0),
            "latest_rules_analysis_at": _iso(row["latest_rules_analysis_at"]),
        }

    @router.post("/analyze")
    async def analyze_rules(payload: AnalyzeRulesRequest) -> dict[str, Any]:
        try:
            result = service.analyze_market_rules(payload.market_id, allow_ai=payload.allow_ai)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"analysis": result.model_dump(mode="json"), "signal": result.signal()}

    @router.post("/analyze/all")
    async def analyze_all(payload: AnalyzeAllRulesRequest) -> dict[str, Any]:
        try:
            return service.analyze_all_active_markets(limit=payload.limit, allow_ai=payload.allow_ai)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in dict(row).items()}


def _pct(value: object, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(value or 0) / total) * 100, 2)


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _empty_coverage() -> dict[str, Any]:
    return {
        "total_markets": 0,
        "markets_with_rules": 0,
        "markets_with_analysis": 0,
        "rules_coverage_pct": 0.0,
        "missing_rules_count": 0,
        "high_wording_risk_count": 0,
        "high_dispute_risk_count": 0,
        "compliance_block_count": 0,
        "average_resolution_clarity": 0.0,
        "latest_rules_analysis_at": None,
    }

