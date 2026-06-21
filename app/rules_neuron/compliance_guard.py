from __future__ import annotations

from app.rules_neuron.contracts import (
    ComplianceBlock,
    ComplianceBlockType,
    ComplianceDecision,
    RulesAnalysisResult,
    RulesRecommendation,
    RulesStatus,
    Severity,
)


def evaluate_compliance(
    market_id: str,
    *,
    rules_text_present: bool,
    wording_risk: float,
    dispute_risk: float,
    resolution_clarity: float,
    source_status: RulesStatus,
    jurisdiction_status: RulesStatus,
    jurisdiction_blocks: list[ComplianceBlock] | None = None,
) -> ComplianceDecision:
    blocks = list(jurisdiction_blocks or [])
    warnings: list[str] = []
    if not rules_text_present:
        blocks.append(ComplianceBlock(market_id=market_id, block_type=ComplianceBlockType.MISSING_RULES, severity=Severity.BLOCKING, reason="rules text is missing"))
    if source_status in {RulesStatus.UNVERIFIED, RulesStatus.BROKEN}:
        blocks.append(ComplianceBlock(market_id=market_id, block_type=ComplianceBlockType.UNVERIFIED_SOURCE, severity=Severity.WARNING, reason="resolution source is not verified"))
    if wording_risk >= 0.75:
        blocks.append(ComplianceBlock(market_id=market_id, block_type=ComplianceBlockType.UNCLEAR_RESOLUTION, severity=Severity.BLOCKING if wording_risk >= 0.85 else Severity.WARNING, reason="wording risk is high"))
    if dispute_risk >= 0.75:
        blocks.append(ComplianceBlock(market_id=market_id, block_type=ComplianceBlockType.DISPUTE_RISK_HIGH, severity=Severity.BLOCKING if dispute_risk >= 0.85 else Severity.WARNING, reason="dispute risk is high"))
    if resolution_clarity < 0.35:
        warnings.append("low resolution clarity")
    if jurisdiction_status == RulesStatus.BLOCKED:
        blocks.append(ComplianceBlock(market_id=market_id, block_type=ComplianceBlockType.JURISDICTION_BLOCK, severity=Severity.BLOCKING, reason="jurisdiction guard blocked market"))
    if any(block.severity == Severity.BLOCKING for block in blocks):
        recommendation = RulesRecommendation.NO_TRADE
        status = RulesStatus.BLOCKED
    elif blocks or wording_risk >= 0.55 or dispute_risk >= 0.55:
        recommendation = RulesRecommendation.PENALIZE_HEAVILY
        status = RulesStatus.WARNING
    elif resolution_clarity < 0.6:
        recommendation = RulesRecommendation.REVIEW_REQUIRED
        status = RulesStatus.WARNING
    else:
        recommendation = RulesRecommendation.TRADE_ALLOWED
        status = RulesStatus.CLEAR
    cannot = "; ".join(block.reason for block in blocks if block.severity == Severity.BLOCKING) or None
    return ComplianceDecision(market_id=market_id, compliance_status=status, blocks=blocks, warnings=warnings, recommendation=recommendation, cannot_trade_reason=cannot)


def compliance_from_analysis(result: RulesAnalysisResult) -> ComplianceDecision:
    return evaluate_compliance(
        result.market_id,
        rules_text_present=result.rules_text_present,
        wording_risk=result.wording_risk,
        dispute_risk=result.dispute_risk,
        resolution_clarity=result.resolution_clarity,
        source_status=RulesStatus(result.source_verification_status),
        jurisdiction_status=RulesStatus(result.jurisdiction_status),
    )

