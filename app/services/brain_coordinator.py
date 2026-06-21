from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.brain_outputs import BrainOutput, brain_output_from_row
from app.neural_mesh.coordinator import (
    CoordinatorDecision,
    CoordinatorDecisionConflict,
    CoordinatorDecisionInput,
    coordinator_conflict_from_row,
    coordinator_decision_from_row,
    coordinator_input_from_row,
)
from app.repositories.coordinator_repository import CoordinatorRepository


ENTRY_BLOCK_ACTIONS = ["PAPER_ENTRY", "LIVE_ENTRY", "ORDER_CREATION", "POSITION_OPEN", "EXECUTION"]
EXECUTION_BLOCK_ACTIONS = ["ORDER_CREATION", "EXECUTION"]
RULE_BLOCK_FLAGS = {"RESOLUTION_AMBIGUOUS", "WORDING_RISK_HIGH", "MISSING_RULES", "COMPLIANCE_BLOCK"}
CAPITAL_FLAGS = {"INSUFFICIENT_CAPITAL", "LOW_RESERVE", "CAPITAL_CONSTRAINED"}


class BrainCoordinatorService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: CoordinatorRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or CoordinatorRepository()

    def create_coordinator_decision(
        self,
        decision: CoordinatorDecision | dict[str, Any],
        *,
        inputs: list[CoordinatorDecisionInput | dict[str, Any]] | None = None,
        conflicts: list[CoordinatorDecisionConflict | dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        item = decision if isinstance(decision, CoordinatorDecision) else CoordinatorDecision(**decision)
        input_items = [_input_for_decision(item.coordinator_decision_id, data) for data in inputs or []]
        conflict_items = [_conflict_for_decision(item.coordinator_decision_id, data) for data in conflicts or []]
        if not self._factory.enabled:
            return self._serialize_decision(item, inputs=input_items, conflicts=conflict_items)
        with self._factory.connect() as conn, conn.transaction():
            row = self._repository.create_decision(conn, item)
            created = coordinator_decision_from_row(row)
            for input_item in input_items:
                self._repository.add_input(conn, input_item)
            for conflict in conflict_items:
                self._repository.add_conflict(conn, conflict)
        return self._serialize_decision(created, inputs=input_items, conflicts=conflict_items)

    def coordinate_market_outputs(self, market_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return self.coordinate_outputs([])
        with self._factory.connect() as conn:
            rows = self._repository.list_brain_outputs_for_market(conn, market_id, limit=limit)
        return self.coordinate_outputs([str(row["brain_output_id"]) for row in rows], market_id=market_id)

    def coordinate_position_outputs(self, position_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return self.coordinate_outputs([])
        with self._factory.connect() as conn:
            rows = self._repository.list_brain_outputs_for_position(conn, position_id, limit=limit)
        return self.coordinate_outputs([str(row["brain_output_id"]) for row in rows], position_id=position_id)

    def coordinate_outputs(
        self,
        brain_output_ids: list[str],
        *,
        market_id: str | None = None,
        position_id: str | None = None,
    ) -> dict[str, Any]:
        outputs = self._load_outputs(brain_output_ids)
        decision, inputs, conflicts = self.apply_coordination_rules(outputs, market_id=market_id, position_id=position_id)
        return self.create_coordinator_decision(decision, inputs=inputs, conflicts=conflicts)

    def detect_conflicts(self, outputs: list[dict[str, Any]]) -> list[CoordinatorDecisionConflict]:
        return _detect_conflicts([_output_object(item) for item in outputs])

    def apply_coordination_rules(
        self,
        outputs: list[dict[str, Any] | BrainOutput],
        *,
        market_id: str | None = None,
        position_id: str | None = None,
    ) -> tuple[CoordinatorDecision, list[CoordinatorDecisionInput], list[CoordinatorDecisionConflict]]:
        output_items = [_output_object(item) for item in outputs]
        explicit_market = market_id or _first_value(output_items, "market_id")
        explicit_position = position_id or _first_value(output_items, "position_id")
        inputs = [_decision_input(output) for output in output_items]
        conflicts = _detect_conflicts(output_items)
        brains = {output.brain for output in output_items}
        all_flags = sorted({flag for output in output_items for flag in _flags(output)})
        max_confidence = _max_number([output.confidence for output in output_items])
        max_urgency = _max_number([output.urgency for output in output_items])
        blocked_actions = set(EXECUTION_BLOCK_ACTIONS)
        approved_actions = {"WATCH"}
        required_reviews: set[str] = set()
        final_state = "WATCH"
        primary_reason = "Coordinator conservative default: watch and gather more evidence."
        status = "ACTIVE"

        if not output_items:
            final_state = "INSUFFICIENT_DATA"
            primary_reason = "No Brain Outputs were available for coordination."
            approved_actions = {"REQUEST_MORE_DATA"}
            required_reviews = {"SEND_TO_HUMAN_REVIEW"}
            blocked_actions.update(ENTRY_BLOCK_ACTIONS)
            status = "DEGRADED"
        else:
            opportunity = _find_opportunity(output_items)
            risk = _find_risk(output_items)
            rules_block = any(flag in RULE_BLOCK_FLAGS for flag in all_flags)
            capital_block = _find_capital_constraint(output_items)
            exit_review = _find_exit_review(output_items)
            no_trade = _find_no_trade(output_items)

            if opportunity:
                approved_actions.add("REVIEW")
            if risk:
                final_state = "RISK_BLOCKED"
                primary_reason = "Risk brain output blocks opportunity or entry candidate."
                approved_actions = {"SEND_TO_RISK_REVIEW"}
                required_reviews.add("SEND_TO_RISK_REVIEW")
                blocked_actions.update(ENTRY_BLOCK_ACTIONS)
                blocked_actions.add("OPPORTUNITY_OVERRIDE_RISK")
            elif rules_block:
                final_state = "PAPER_CANDIDATE_BLOCKED"
                primary_reason = "Rules or compliance risk blocks entry candidate."
                approved_actions = {"REVIEW"}
                required_reviews.add("SEND_TO_HUMAN_REVIEW")
                blocked_actions.update(ENTRY_BLOCK_ACTIONS)
            elif exit_review:
                final_state = "EXIT_REVIEW_REQUIRED"
                primary_reason = "Exit brain output requires review before any hold/close interpretation."
                approved_actions = {"SEND_TO_EXIT_REVIEW"}
                required_reviews.add("SEND_TO_EXIT_REVIEW")
                blocked_actions.update(["POSITION_CLOSE", "EXECUTION", "ORDER_CREATION"])
            elif no_trade:
                final_state = "NO_TRADE"
                primary_reason = "No-Trade brain output is valid and coordinator preserves the no-trade state."
                approved_actions = {"MARK_NO_TRADE", "WATCH"}
                blocked_actions.update(ENTRY_BLOCK_ACTIONS)
            elif capital_block:
                final_state = "REVIEW_REQUIRED"
                primary_reason = "Capital brain output limits action scope."
                approved_actions = {"REVIEW"}
                required_reviews.add("SEND_TO_HUMAN_REVIEW")
                blocked_actions.update(ENTRY_BLOCK_ACTIONS)
            elif opportunity:
                final_state = "REVIEW_REQUIRED" if conflicts else "WATCH"
                primary_reason = "Opportunity hint exists, but coordinator does not create executable candidates in this phase."
                approved_actions = {"REVIEW", "WATCH"}
                required_reviews.add("SEND_TO_HUMAN_REVIEW")
                blocked_actions.update(ENTRY_BLOCK_ACTIONS)

            if conflicts and final_state == "WATCH":
                final_state = "CONFLICT_REVIEW"
                primary_reason = "Brain Outputs disagree and require review."
                approved_actions = {"REVIEW"}
                required_reviews.add("SEND_TO_HUMAN_REVIEW")
                blocked_actions.update(ENTRY_BLOCK_ACTIONS)

        decision = CoordinatorDecision(
            market_id=explicit_market,
            position_id=explicit_position,
            final_state=final_state,
            primary_reason=primary_reason,
            confidence=max_confidence,
            urgency=max_urgency,
            conflicts_detected=bool(conflicts),
            governor_required=True,
            execution_allowed=False,
            approved_actions=sorted(approved_actions),
            blocked_actions=sorted(blocked_actions),
            required_reviews=sorted(required_reviews),
            risk_flags=all_flags,
            source_brain_count=len(brains),
            input_output_count=len(output_items),
            conflict_count=len(conflicts),
            correlation_id=_first_value(output_items, "correlation_id"),
            status=status,
            metadata={
                "rule_engine": "v2_part2b_deterministic",
                "non_executing": True,
                "output_ids": [output.brain_output_id for output in output_items],
            },
        )
        conflicts = [_conflict_for_decision(decision.coordinator_decision_id, conflict) for conflict in conflicts]
        inputs = [_input_for_decision(decision.coordinator_decision_id, item) for item in inputs]
        return decision, inputs, conflicts

    def list_recent_decisions(
        self,
        *,
        limit: int = 50,
        market_id: str | None = None,
        position_id: str | None = None,
        final_state: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_recent_decisions(
                conn,
                limit=limit,
                market_id=market_id,
                position_id=position_id,
                final_state=final_state,
                status=status,
            )
        return [coordinator_decision_from_row(dict(row)).to_api_dict() for row in rows]

    def get_decision(self, coordinator_decision_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_decision(conn, coordinator_decision_id)
            if not row:
                return None
            inputs = self._repository.list_inputs(conn, coordinator_decision_id)
            conflicts = self._repository.list_conflicts_for_decision(conn, coordinator_decision_id)
        return self._serialize_decision(
            coordinator_decision_from_row(row),
            inputs=[coordinator_input_from_row(dict(row)) for row in inputs],
            conflicts=[coordinator_conflict_from_row(dict(row)) for row in conflicts],
        )

    def list_decisions_by_market(self, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_decisions_by_market(conn, market_id, limit=limit)
        return [coordinator_decision_from_row(dict(row)).to_api_dict() for row in rows]

    def list_decisions_by_position(self, position_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_decisions_by_position(conn, position_id, limit=limit)
        return [coordinator_decision_from_row(dict(row)).to_api_dict() for row in rows]

    def list_conflicts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_conflicts(conn, limit=limit)
        return [coordinator_conflict_from_row(dict(row)).model_dump(mode="json") for row in rows]

    def get_coordinator_summary(self, *, limit: int = 10) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        status = "ERROR" if summary["execution_allowed_count"] else "OK"
        return {
            "status": status,
            "mock_data": False,
            "updated_at": datetime.now().astimezone().isoformat(),
            "total_decisions_24h": summary["total_decisions_24h"],
            "decisions_by_state": [_json_safe(dict(row)) for row in summary["decisions_by_state"]],
            "recent_decisions": [
                _json_safe(coordinator_decision_from_row(dict(row)).to_api_dict())
                for row in summary["recent_decisions"]
            ],
            "recent_conflicts": [
                _json_safe(coordinator_conflict_from_row(dict(row)).model_dump(mode="json"))
                for row in summary["recent_conflicts"]
            ],
            "conflicts_detected_24h": summary["conflicts_detected_24h"],
            "no_trade_decisions_24h": summary["no_trade_decisions_24h"],
            "risk_blocked_24h": summary["risk_blocked_24h"],
            "review_required_24h": summary["review_required_24h"],
            "execution_allowed_count": summary["execution_allowed_count"],
            "decisions_requiring_governor": summary["decisions_requiring_governor"],
            "blocked_actions_summary": [_json_safe(dict(row)) for row in summary["blocked_actions_summary"]],
        }

    def _load_outputs(self, brain_output_ids: list[str]) -> list[dict[str, Any]]:
        if not brain_output_ids or not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_brain_outputs_by_ids(conn, brain_output_ids)
        return [brain_output_from_row(dict(row)).to_api_dict() for row in rows]

    def _serialize_decision(
        self,
        decision: CoordinatorDecision,
        *,
        inputs: list[CoordinatorDecisionInput],
        conflicts: list[CoordinatorDecisionConflict],
    ) -> dict[str, Any]:
        return {
            **decision.to_api_dict(),
            "inputs": [item.model_dump(mode="json") for item in inputs],
            "conflicts": [item.model_dump(mode="json") for item in conflicts],
        }


def _output_object(item: dict[str, Any] | BrainOutput) -> BrainOutput:
    return item if isinstance(item, BrainOutput) else BrainOutput(**item)


def _decision_input(output: BrainOutput) -> CoordinatorDecisionInput:
    return CoordinatorDecisionInput(
        brain_output_id=output.brain_output_id,
        brain=output.brain,
        input_role=output.output_type,
        input_recommendation=output.recommendation,
        input_confidence=output.confidence,
    )


def _detect_conflicts(outputs: list[BrainOutput]) -> list[CoordinatorDecisionConflict]:
    conflicts: list[CoordinatorDecisionConflict] = []
    opportunity = _find_opportunity(outputs)
    risk = _find_risk(outputs)
    ai_positive = _find_ai_positive(outputs)
    capital = _find_capital_constraint(outputs)
    exit_review = _find_exit_review(outputs)
    no_trade = _find_no_trade(outputs)
    rules_block_output = _find_rules_block(outputs)

    if opportunity and risk:
        conflicts.append(
            _conflict(
                "opportunity_positive_vs_risk_high",
                "Opportunity hint conflicts with risk warning; risk wins.",
                0.9,
                opportunity,
                risk,
            )
        )
    if ai_positive and risk:
        conflicts.append(_conflict("ai_positive_vs_risk_block", "AI analysis cannot override risk.", 0.85, ai_positive, risk))
    if opportunity and capital:
        conflicts.append(
            _conflict(
                "capital_insufficient_vs_opportunity_candidate",
                "Opportunity hint conflicts with capital constraint.",
                0.7,
                opportunity,
                capital,
            )
        )
    if exit_review and any(_looks_like_hold(output) for output in outputs):
        hold = next(output for output in outputs if _looks_like_hold(output))
        conflicts.append(_conflict("exit_review_vs_hold", "Exit review conflicts with hold/watch interpretation.", 0.75, exit_review, hold))
    if opportunity and rules_block_output:
        conflicts.append(
            _conflict(
                "rules_ambiguous_vs_opportunity_candidate",
                "Opportunity hint conflicts with rules ambiguity or compliance block.",
                0.8,
                opportunity,
                rules_block_output,
            )
        )
    if opportunity and no_trade:
        conflicts.append(_conflict("no_trade_vs_opportunity_candidate", "No-Trade hint conflicts with opportunity hint.", 0.8, no_trade, opportunity))
    return conflicts


def _conflict(
    key: str,
    reason: str,
    severity: float,
    left: BrainOutput,
    right: BrainOutput,
) -> CoordinatorDecisionConflict:
    return CoordinatorDecisionConflict(
        conflict_type="brain_output_disagreement",
        conflict_key=key,
        conflict_reason=reason,
        conflict_severity=severity,
        left_brain=left.brain,
        right_brain=right.brain,
        left_output_id=left.brain_output_id,
        right_output_id=right.brain_output_id,
    )


def _find_opportunity(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(
        outputs,
        lambda output: output.brain == "opportunity"
        or output.output_type == "OPPORTUNITY_HINT"
        or "OPPORTUNITY" in output.recommendation.upper()
        or "CANDIDATE" in output.recommendation.upper(),
    )


def _find_risk(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(
        outputs,
        lambda output: output.brain == "risk"
        and (
            output.output_type == "RISK_WARNING"
            or output.recommendation.upper() in {"CAUTION", "REVIEW", "WATCH"}
            or any(flag in {"RISK_HIGH", "RISK_BLOCK", "COMPLIANCE_BLOCK"} for flag in _flags(output))
        )
        and (output.confidence is None or output.confidence >= 0.5),
    )


def _find_rules_block(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(outputs, lambda output: bool(set(_flags(output)).intersection(RULE_BLOCK_FLAGS)))


def _find_capital_constraint(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(
        outputs,
        lambda output: output.brain == "capital"
        and (
            bool(set(_flags(output)).intersection(CAPITAL_FLAGS))
            or "INSUFFICIENT" in output.recommendation.upper()
            or "LOW_RESERVE" in output.recommendation.upper()
        ),
    )


def _find_exit_review(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(
        outputs,
        lambda output: output.brain == "exit"
        and (output.output_type == "EXIT_REVIEW_HINT" or (output.urgency is not None and output.urgency >= 0.7)),
    )


def _find_no_trade(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(
        outputs,
        lambda output: output.brain == "no_trade"
        and (
            output.output_type == "NO_TRADE_HINT"
            or "NO_TRADE" in output.recommendation.upper()
            or "NO_TRADE" in _flags(output)
        )
        and (output.confidence is None or output.confidence >= 0.5),
    )


def _find_ai_positive(outputs: list[BrainOutput]) -> BrainOutput | None:
    return _first_matching(
        outputs,
        lambda output: output.brain == "ai"
        and ("OPPORTUNITY" in output.recommendation.upper() or "POSITIVE" in output.recommendation.upper()),
    )


def _looks_like_hold(output: BrainOutput) -> bool:
    text = f"{output.output_type} {output.recommendation}".upper()
    return "HOLD" in text or "WATCH" in text


def _first_matching(outputs: list[BrainOutput], predicate) -> BrainOutput | None:
    for output in outputs:
        if predicate(output):
            return output
    return None


def _flags(output: BrainOutput) -> list[str]:
    return [str(flag).strip().upper() for flag in output.risk_flags if str(flag).strip()]


def _first_value(outputs: list[BrainOutput], attr: str) -> str | None:
    for output in outputs:
        value = getattr(output, attr)
        if value:
            return str(value)
    return None


def _max_number(values: list[float | None]) -> float | None:
    real = [float(value) for value in values if value is not None]
    return max(real) if real else None


def _input_for_decision(coordinator_decision_id: str, item: CoordinatorDecisionInput | dict[str, Any]) -> CoordinatorDecisionInput:
    data = item.model_dump() if isinstance(item, CoordinatorDecisionInput) else dict(item)
    data["coordinator_decision_id"] = coordinator_decision_id
    return CoordinatorDecisionInput(**data)


def _conflict_for_decision(coordinator_decision_id: str, item: CoordinatorDecisionConflict | dict[str, Any]) -> CoordinatorDecisionConflict:
    data = item.model_dump() if isinstance(item, CoordinatorDecisionConflict) else dict(item)
    data["coordinator_decision_id"] = coordinator_decision_id
    return CoordinatorDecisionConflict(**data)


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now().astimezone().isoformat(),
        "total_decisions_24h": 0,
        "decisions_by_state": [],
        "recent_decisions": [],
        "recent_conflicts": [],
        "conflicts_detected_24h": 0,
        "no_trade_decisions_24h": 0,
        "risk_blocked_24h": 0,
        "review_required_24h": 0,
        "execution_allowed_count": 0,
        "decisions_requiring_governor": 0,
        "blocked_actions_summary": [],
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
