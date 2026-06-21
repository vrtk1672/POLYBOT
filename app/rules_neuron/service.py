from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.compliance_block_repository import ComplianceBlockRepository
from app.repositories.resolution_source_repository import ResolutionSourceRepository
from app.repositories.rules_analysis_repository import RulesAnalysisRepository
from app.repositories.wording_risk_repository import WordingRiskRepository
from app.rules_neuron.ai_wording_analyzer import AIWordingAnalyzer
from app.rules_neuron.ambiguous_terms_detector import detect_ambiguous_terms
from app.rules_neuron.compliance_guard import evaluate_compliance
from app.rules_neuron.contracts import ParsedRules, RulesAnalysisResult, RulesStatus
from app.rules_neuron.deadline_parser import compute_deadline_risk, parse_deadline_from_rules
from app.rules_neuron.dispute_risk_scorer import compute_dispute_risk
from app.rules_neuron.edge_case_detector import detect_contradictions, detect_dangerous_edge_cases, detect_edge_cases, detect_scope_ambiguity
from app.rules_neuron.jurisdiction_guard import evaluate_jurisdiction
from app.rules_neuron.resolution_clarity_scorer import compute_resolution_clarity
from app.rules_neuron.resolution_source_parser import parse_resolution_source
from app.rules_neuron.rules_errors import RulesAnalysisBlocked
from app.rules_neuron.rules_ingestion import RulesIngestion
from app.rules_neuron.settlement_method_parser import parse_settlement_method
from app.rules_neuron.source_verification_guard import verify_resolution_source
from app.rules_neuron.wording_risk_scorer import compute_wording_risk
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class RulesNeuronService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, state_governor: StateGovernor | None = None, ai_analyzer: AIWordingAnalyzer | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.ingestion = RulesIngestion(connection_factory=self._factory, event_bus=self._event_bus)
        self._analyses = RulesAnalysisRepository()
        self._wording = WordingRiskRepository()
        self._blocks = ComplianceBlockRepository()
        self._sources = ResolutionSourceRepository()
        self.ai_analyzer = ai_analyzer or AIWordingAnalyzer(connection_factory=self._factory, event_bus=self._event_bus)

    def analyze_market_rules(
        self,
        market_id: str,
        *,
        allow_ai: bool = False,
        log_no_trade_block: bool = True,
    ) -> RulesAnalysisResult:
        self._assert_analysis_allowed()
        rules_input = self.ingestion.build_rules_input(market_id)
        rules_hash = rules_input.metadata.get("rules_hash")
        source_status = verify_resolution_source(parse_resolution_source(rules_input.rules_text, {**rules_input.raw_market_json, "resolution_source": rules_input.resolution_source, "resolution_source_url": rules_input.resolution_source_url}, market_id=market_id))
        deadline = rules_input.deadline_at or parse_deadline_from_rules(rules_input.rules_text)
        deadline_result = compute_deadline_risk(rules_input.rules_text, deadline, rules_input.close_time)
        settlement_method = parse_settlement_method(rules_input.rules_text)
        ambiguous_terms = detect_ambiguous_terms(rules_input.rules_text)
        edge_cases = detect_edge_cases(rules_input.rules_text, rules_input.question, rules_input.category)
        edge_cases.extend(detect_scope_ambiguity(rules_input.rules_text, rules_input.question))
        contradictions = detect_contradictions(rules_input.rules_text)
        edge_cases.extend(contradictions)
        dangerous = detect_dangerous_edge_cases(edge_cases)
        parsed = ParsedRules(
            market_id=market_id,
            rules_hash=str(rules_hash) if rules_hash else None,
            rules_text_present=bool(rules_input.rules_text),
            resolution_source_present=bool(rules_input.resolution_source or rules_input.resolution_source_url),
            deadline_present=deadline_result.get("deadline_at") is not None,
            settlement_method=settlement_method,
            deadline_at=deadline_result.get("deadline_at"),
            ambiguous_terms=ambiguous_terms,
            edge_cases=edge_cases,
            dangerous_edge_cases=dangerous,
        )
        wording = compute_wording_risk(parsed, deadline_result=deadline_result, edge_cases=edge_cases, ambiguous_terms=ambiguous_terms, source_status=source_status, contradictions=contradictions)
        dispute = compute_dispute_risk(parsed, source_status, edge_cases, settlement_method, category=rules_input.category)
        clarity = compute_resolution_clarity(parsed, source_status, deadline_result, settlement_method)
        jurisdiction_status, jurisdiction_blocks = evaluate_jurisdiction(market_id, category=rules_input.category, rules_text=rules_input.rules_text)
        decision = evaluate_compliance(
            market_id,
            rules_text_present=parsed.rules_text_present,
            wording_risk=wording.total_wording_risk,
            dispute_risk=dispute.dispute_risk,
            resolution_clarity=clarity,
            source_status=source_status.verification_status,
            jurisdiction_status=jurisdiction_status,
            jurisdiction_blocks=jurisdiction_blocks,
        )
        result = RulesAnalysisResult(
            market_id=market_id,
            rules_hash=parsed.rules_hash,
            rules_text_present=parsed.rules_text_present,
            resolution_source_present=parsed.resolution_source_present,
            deadline_present=parsed.deadline_present,
            settlement_method=settlement_method,
            deadline_at=parsed.deadline_at,
            ambiguous_terms=ambiguous_terms,
            edge_cases=edge_cases,
            dangerous_edge_cases=dangerous,
            wording_risk=wording.total_wording_risk,
            dispute_risk=dispute.dispute_risk,
            resolution_clarity=clarity,
            source_verification_status=source_status.verification_status,
            jurisdiction_status=jurisdiction_status,
            compliance_status=decision.compliance_status,
            recommendation=decision.recommendation,
            cannot_trade_reason=decision.cannot_trade_reason,
            metadata={"dispute_factors": dispute.factors, "warnings": decision.warnings},
        )
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._sources.upsert_source(conn, source_status)
                self._analyses.insert_analysis(conn, result)
                wording.rules_analysis_id = result.rules_analysis_id
                self._wording.insert_score(conn, wording)
                for block in decision.blocks:
                    self._blocks.insert_block(conn, block)
        self._publish_all(result, wording, dispute.dispute_risk, source_status, decision.blocks)
        if log_no_trade_block and result.recommendation == "NO_TRADE":
            self._log_no_trade_block(result, rules_input)
        if allow_ai:
            self.ai_analyzer.analyze_wording_with_ai(rules_input, result, allow_cloud=False)
        return result

    def analyze_all_active_markets(self, *, limit: int = 50, allow_ai: bool = False) -> dict[str, Any]:
        self._assert_analysis_allowed()
        if not self._factory.enabled:
            return {"analyzed": 0, "failed": 0, "items": []}
        with self._factory.connect() as conn:
            rows = conn.execute("SELECT market_id FROM markets_v2 WHERE active = true ORDER BY last_seen_at DESC LIMIT %s", (limit,)).fetchall()
        items = []
        failed = 0
        for row in rows:
            try:
                items.append(self.analyze_market_rules(row["market_id"], allow_ai=allow_ai).signal())
            except Exception:
                failed += 1
        return {"analyzed": len(items), "failed": failed, "items": items}

    def get_latest_analysis(self, market_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._analyses.get_latest(conn, market_id)

    def _assert_analysis_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.RUN_INTELLIGENCE)
        except Exception as exc:
            raise RulesAnalysisBlocked("rules analysis blocked by runtime mode") from exc

    def _publish_all(self, result: RulesAnalysisResult, wording, dispute_risk: float, source_status, blocks) -> None:
        payload = {"market_id": result.market_id, "rules_analysis_id": result.rules_analysis_id, "recommendation": result.recommendation.value if hasattr(result.recommendation, "value") else result.recommendation}
        self._publish(EventType.RULES_SOURCE_VERIFIED.value, {"market_id": result.market_id, "status": source_status.verification_status.value if hasattr(source_status.verification_status, "value") else source_status.verification_status})
        self._publish(EventType.RULES_ANALYSIS_CREATED.value, {**payload, "wording_risk": result.wording_risk, "dispute_risk": result.dispute_risk})
        self._publish(EventType.RULES_WORDING_RISK_SCORED.value, {"market_id": result.market_id, "rules_analysis_id": result.rules_analysis_id, "wording_risk": wording.total_wording_risk})
        self._publish(EventType.RULES_DISPUTE_RISK_SCORED.value, {"market_id": result.market_id, "rules_analysis_id": result.rules_analysis_id, "dispute_risk": dispute_risk})
        for block in blocks:
            self._publish(EventType.RULES_COMPLIANCE_BLOCKED.value, {"market_id": result.market_id, "block_type": block.block_type.value, "severity": block.severity.value})
        self._publish(EventType.RULES_RECOMMENDATION_CREATED.value, payload)

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, source_service="rules_neuron", aggregate_type="market", aggregate_id=payload.get("market_id"), metadata={"non_trading_event": True})
        except Exception:
            pass

    def _log_no_trade_block(self, result: RulesAnalysisResult, rules_input) -> None:  # noqa: ANN001
        if not self._factory.enabled:
            return
        reasons = _rules_no_trade_reasons(result)
        payload = {
            "market_id": result.market_id,
            "market_family": rules_input.market_family,
            "source_layer": "rules",
            "source_run_id": result.rules_analysis_id,
            "source_record_id": result.rules_analysis_id,
            "decision_status": "NO_TRADE",
            "primary_reason": reasons[0],
            "reasons": reasons,
            "risk_flags": [
                {
                    "source": "rules_neuron",
                    "wording_risk": result.wording_risk,
                    "dispute_risk": result.dispute_risk,
                    "resolution_clarity": result.resolution_clarity,
                    "cannot_trade_reason": result.cannot_trade_reason,
                }
            ],
            "decision_confidence": max(result.wording_risk, result.dispute_risk, 0.75),
            "data_confidence": result.resolution_clarity,
            "insufficient_data": not result.rules_text_present or not result.resolution_source_present,
            "insufficient_data_reasons": _insufficient_rules_reasons(result),
            "explanation": result.cannot_trade_reason or "Rules neuron produced a NO_TRADE block.",
        }
        try:
            from app.no_trade.service import NoTradeService

            NoTradeService(connection_factory=self._factory, event_bus=self._event_bus).log_decision(payload)
        except Exception:
            return


def _rules_no_trade_reasons(result: RulesAnalysisResult) -> list[str]:
    reasons: list[str] = []
    if not result.rules_text_present:
        reasons.append("bad_rules")
    if result.wording_risk >= 0.75:
        reasons.append("high_wording_risk")
    if result.dispute_risk >= 0.75:
        reasons.append("bad_rules")
    if not result.resolution_source_present:
        reasons.append("insufficient_data")
    return list(dict.fromkeys(reasons or ["bad_rules"]))


def _insufficient_rules_reasons(result: RulesAnalysisResult) -> list[str]:
    reasons: list[str] = []
    if not result.rules_text_present:
        reasons.append("missing_rules")
    if not result.resolution_source_present:
        reasons.append("missing_resolution_source")
    if not result.deadline_present:
        reasons.append("missing_deadline")
    return reasons
