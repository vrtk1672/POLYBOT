from __future__ import annotations

from app.rules_neuron.contracts import ComplianceBlock, ComplianceBlockType, RulesStatus, Severity


PROHIBITED_CATEGORIES = {"prohibited", "illegal", "sanctioned"}
WARNING_CATEGORIES = {"regulation", "legal", "court", "politics-policy"}


def evaluate_jurisdiction(market_id: str, *, category: str | None = None, rules_text: str | None = None) -> tuple[RulesStatus, list[ComplianceBlock]]:
    blocks: list[ComplianceBlock] = []
    category_norm = (category or "").lower()
    lower = (rules_text or "").lower()
    if category_norm in PROHIBITED_CATEGORIES or "sanctioned jurisdiction" in lower:
        blocks.append(ComplianceBlock(market_id=market_id, block_type=ComplianceBlockType.JURISDICTION_BLOCK, severity=Severity.BLOCKING, reason="prohibited or unsupported jurisdiction/category"))
        return RulesStatus.BLOCKED, blocks
    if category_norm in WARNING_CATEGORIES or "regulatory" in lower:
        return RulesStatus.WARNING, blocks
    if not category_norm:
        return RulesStatus.UNKNOWN, blocks
    return RulesStatus.CLEAR, blocks

