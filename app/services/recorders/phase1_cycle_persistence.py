from __future__ import annotations

import logging
from hashlib import sha256
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.artifact import RunArtifactContract
from app.domain.contracts.decision import DecisionLedgerContract
from app.domain.contracts.market_snapshot import MarketSnapshotContract
from app.domain.contracts.rejection import RejectionLedgerContract
from app.domain.contracts.ranking_snapshot import RankingSnapshotContract
from app.services.recorders.artifact_recorder import ArtifactRecorder
from app.services.recorders.cycle_recorder import CycleRecorder
from app.services.recorders.decision_ledger_recorder import DecisionLedgerRecorder
from app.services.recorders.market_snapshot_recorder import MarketSnapshotRecorder
from app.services.recorders.rejection_recorder import RejectionRecorder
from app.services.recorders.ranking_snapshot_recorder import RankingSnapshotRecorder
from app.stage4 import build_allowed_universe, get_stage4_settings, rank_candidates
from gamma_crawler import edge_cents, hours_remaining

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(slots=True)
class PersistedCycleHandle:
    cycle_id: str | None
    started_perf: float | None


@dataclass(slots=True)
class RankedSelectionEntry:
    market_id: str
    rank_position: int
    base_score: float
    adaptive_rank: float
    selected_flag: bool
    bucket: str
    expected_edge_proxy: float | None
    recommendation_action: str
    recommendation_confidence: float
    recommendation_reason: str
    ranking_breakdown: dict[str, object]


@dataclass(slots=True)
class MarketDecisionEntry:
    market_id: str
    decision_type: str
    selected: bool
    reason: str
    confidence: float | None
    bucket_type: str | None
    expected_edge_proxy: float | None
    metadata: dict[str, object]


@dataclass(slots=True)
class SelectionView:
    ranked_entries: list[RankedSelectionEntry]
    decisions: list[MarketDecisionEntry]
    selected_market_id: str | None


class Phase1CyclePersistenceService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._cycle_recorder = CycleRecorder()
        self._market_recorder = MarketSnapshotRecorder()
        self._ranking_recorder = RankingSnapshotRecorder()
        self._decision_recorder = DecisionLedgerRecorder()
        self._artifact_recorder = ArtifactRecorder()
        self._rejection_recorder = RejectionRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def open_cycle(
        self,
        *,
        mode: str,
        trigger_source: str,
        top_n: int,
        pages_requested: int | None,
        session_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PersistedCycleHandle:
        if not self.enabled:
            return PersistedCycleHandle(cycle_id=None, started_perf=None)
        try:
            with self._factory.connect() as conn, conn.transaction():
                cycle_id, started_perf = self._cycle_recorder.open_cycle(
                    conn,
                    mode=mode,
                    trigger_source=trigger_source,
                    top_n=top_n,
                    pages_requested=pages_requested,
                    session_id=session_id,
                    metadata=metadata,
                )
            return PersistedCycleHandle(cycle_id=cycle_id, started_perf=started_perf)
        except Exception:
            logger.exception("phase1_cycle_open_failed")
            return PersistedCycleHandle(cycle_id=None, started_perf=None)

    def persist_cycle_snapshot(self, *, handle: PersistedCycleHandle, cycle_result) -> None:
        if not self.enabled or not handle.cycle_id or handle.started_perf is None:
            return
        try:
            with self._factory.connect() as conn, conn.transaction():
                selection_view = build_selection_view(
                    cycle_result.top_scored,
                    cycle_result.recommendations,
                )
                snapshots = build_market_snapshot_contracts(
                    cycle_id=handle.cycle_id,
                    items=cycle_result.top_scored,
                )
                market_snapshot_ids = self._market_recorder.record_many(conn, snapshots)
                rankings = build_ranking_snapshot_contracts(
                    cycle_id=handle.cycle_id,
                    selection_view=selection_view,
                    market_snapshot_ids=market_snapshot_ids,
                )
                ranking_snapshot_ids = self._ranking_recorder.record_many(conn, rankings)
                decisions = build_decision_contracts(
                    cycle_id=handle.cycle_id,
                    selection_view=selection_view,
                    market_snapshot_ids=market_snapshot_ids,
                    ranking_snapshot_ids=ranking_snapshot_ids,
                )
                self._decision_recorder.record_many(conn, decisions)
                rejections = build_rejection_contracts(
                    cycle_id=handle.cycle_id,
                    selection_view=selection_view,
                )
                self._rejection_recorder.record_many(conn, rejections)
                artifact = self._persist_cycle_artifact(
                    cycle_id=handle.cycle_id,
                    cycle_result=cycle_result,
                    selection_view=selection_view,
                )
                if artifact is not None:
                    self._artifact_recorder.record(conn, artifact)
                self._cycle_recorder.close_cycle(
                    conn,
                    cycle_id=handle.cycle_id,
                    started_perf=handle.started_perf,
                    status="COMPLETED",
                    markets_fetched_count=len(cycle_result.top_scored),
                    markets_scored_count=len(cycle_result.top_scored),
                    markets_ranked_count=len(rankings),
                    decisions_count=len(decisions),
                    selected_market_id=selection_view.selected_market_id,
                )
        except Exception:
            logger.exception("phase1_cycle_persist_failed cycle_id=%s", handle.cycle_id)
            self.fail_cycle(
                handle=handle,
                markets_fetched_count=len(cycle_result.top_scored),
                markets_scored_count=len(cycle_result.top_scored),
                last_error="phase1_persist_failed",
            )

    def fail_cycle(
        self,
        *,
        handle: PersistedCycleHandle,
        markets_fetched_count: int,
        markets_scored_count: int,
        last_error: str,
    ) -> None:
        if not self.enabled or not handle.cycle_id or handle.started_perf is None:
            return
        try:
            with self._factory.connect() as conn, conn.transaction():
                self._cycle_recorder.close_cycle(
                    conn,
                    cycle_id=handle.cycle_id,
                    started_perf=handle.started_perf,
                    status="FAILED",
                    markets_fetched_count=markets_fetched_count,
                    markets_scored_count=markets_scored_count,
                    markets_ranked_count=0,
                    decisions_count=0,
                    selected_market_id=None,
                    last_error=last_error,
                )
        except Exception:
            logger.exception("phase1_cycle_fail_close_failed cycle_id=%s", handle.cycle_id)

    def _persist_cycle_artifact(
        self,
        *,
        cycle_id: str,
        cycle_result,
        selection_view: SelectionView,
    ) -> RunArtifactContract | None:
        try:
            artifacts_root = Path(self._settings.artifacts_root)
            base_dir = artifacts_root if artifacts_root.is_absolute() else REPO_ROOT / artifacts_root
            artifact_dir = base_dir / "cycles" / cycle_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = artifact_dir / "cycle_snapshot.json"
            payload = {
                "cycle_id": cycle_id,
                "captured_market_ids": [item.market.market_id for item in cycle_result.top_scored],
                "selected_market_id": selection_view.selected_market_id,
                "ranked_market_ids": [entry.market_id for entry in selection_view.ranked_entries],
                "decisions": [
                    {
                        "market_id": decision.market_id,
                        "decision_type": decision.decision_type,
                        "reason": decision.reason,
                        "selected": decision.selected,
                    }
                    for decision in selection_view.decisions
                ],
            }
            artifact_body = json.dumps(payload, indent=2, sort_keys=True)
            artifact_path.write_text(artifact_body, encoding="utf-8")
            checksum = sha256(artifact_body.encode("utf-8")).hexdigest()
            relative_path = artifact_path.relative_to(REPO_ROOT).as_posix()
            return RunArtifactContract(
                id=str(uuid4()),
                cycle_id=cycle_id,
                artifact_type="replay_snapshot",
                artifact_scope="cycle",
                path=relative_path,
                checksum=checksum,
                metadata_json={
                    "cycle_id": cycle_id,
                    "market_count": len(cycle_result.top_scored),
                    "ranking_count": len(selection_view.ranked_entries),
                    "decision_count": len(selection_view.decisions),
                    "selected_market_id": selection_view.selected_market_id,
                },
            )
        except Exception:
            logger.exception("phase1_cycle_artifact_persist_failed cycle_id=%s", cycle_id)
            return None


def build_selection_view(top_scored, recommendations) -> SelectionView:
    settings = get_stage4_settings()
    source_limit = (
        settings.live_allowed_universe_top_n
        if settings.live_use_adaptive_selector
        else 1
    )
    source_markets = top_scored[:source_limit]
    deferred_markets = top_scored[source_limit:]
    allowed_universe, skipped = build_allowed_universe(source_markets, recommendations, settings)
    ranked_candidates = rank_candidates(allowed_universe)
    skipped_map = {}
    for value in skipped:
        market_id, _, reason = value.partition(":")
        skipped_map[market_id] = reason or "skipped"

    selected_market_id = (
        ranked_candidates[0].candidate.market.market_id
        if ranked_candidates
        else None
    )
    ranked_entries: list[RankedSelectionEntry] = []
    decisions: list[MarketDecisionEntry] = []

    for position, ranked in enumerate(ranked_candidates, start=1):
        candidate = ranked.candidate
        market_id = candidate.market.market_id
        selected_flag = market_id == selected_market_id
        ranked_entries.append(
            RankedSelectionEntry(
                market_id=market_id,
                rank_position=position,
                base_score=float(candidate.item.score),
                adaptive_rank=float(ranked.total_rank),
                selected_flag=selected_flag,
                bucket=candidate.bucket,
                expected_edge_proxy=(
                    float(candidate.edge_cents)
                    if candidate.edge_cents is not None
                    else None
                ),
                recommendation_action=candidate.recommendation.action,
                recommendation_confidence=float(candidate.recommendation.confidence),
                recommendation_reason=candidate.recommendation.reason,
                ranking_breakdown={
                    "market_score": ranked.breakdown.market_score,
                    "confidence": ranked.breakdown.confidence,
                    "edge": ranked.breakdown.edge,
                    "time": ranked.breakdown.time,
                    "execution": ranked.breakdown.execution,
                    "risk_penalty": ranked.breakdown.risk_penalty,
                    "reason": ranked.reason,
                },
            )
        )
        decisions.append(
            MarketDecisionEntry(
                market_id=market_id,
                decision_type="SELECT" if selected_flag else "SKIP",
                selected=selected_flag,
                reason=(
                    ranked.reason
                    if selected_flag
                    else f"not_selected_higher_ranked:{selected_market_id}"
                    if selected_market_id
                    else "not_selected_no_ranked_candidate"
                ),
                confidence=float(candidate.recommendation.confidence),
                bucket_type=candidate.bucket,
                expected_edge_proxy=(
                    float(candidate.edge_cents)
                    if candidate.edge_cents is not None
                    else None
                ),
                metadata={
                    "recommendation_action": candidate.recommendation.action,
                    "eligible": True,
                    "rank_position": position,
                },
            )
        )

    ranked_market_ids = {entry.market_id for entry in ranked_entries}
    rec_by_rank = {rec.rank: rec for rec in recommendations}
    for index, item in enumerate(source_markets, start=1):
        market_id = item.market.market_id
        if market_id in ranked_market_ids:
            continue
        recommendation = rec_by_rank.get(index)
        reason = skipped_map.get(market_id, "excluded_from_adaptive_universe")
        decision_type = "BLOCK" if "not_accepting_orders" in reason else "SKIP"
        decisions.append(
            MarketDecisionEntry(
                market_id=market_id,
                decision_type=decision_type,
                selected=False,
                reason=reason,
                confidence=float(recommendation.confidence) if recommendation else None,
                bucket_type=None,
                expected_edge_proxy=edge_cents(item.market),
                metadata={
                    "recommendation_action": recommendation.action if recommendation else None,
                    "eligible": False,
                    "rank_position": None,
                },
            )
        )

    for item in deferred_markets:
        decisions.append(
            MarketDecisionEntry(
                market_id=item.market.market_id,
                decision_type="NO_ACTION",
                selected=False,
                reason="outside_adaptive_selection_window",
                confidence=None,
                bucket_type=None,
                expected_edge_proxy=edge_cents(item.market),
                metadata={
                    "eligible": False,
                    "recommendation_action": None,
                    "rank_position": None,
                },
            )
        )

    return SelectionView(
        ranked_entries=ranked_entries,
        decisions=sorted(decisions, key=lambda item: (not item.selected, item.market_id)),
        selected_market_id=selected_market_id,
    )


def build_market_snapshot_contracts(*, cycle_id: str, items) -> list[MarketSnapshotContract]:
    contracts: list[MarketSnapshotContract] = []
    for item in items:
        remaining_hours = hours_remaining(item.market)
        contracts.append(
            MarketSnapshotContract(
                cycle_id=cycle_id,
                market_id=item.market.market_id,
                event_id=item.market.event_id,
                question=item.market.question,
                slug=item.market.slug,
                captured_at=item.computed_at,
                yes_price=item.market.yes_price,
                no_price=item.market.no_price,
                last_trade_price=item.market.last_trade_price,
                best_bid=item.market.best_bid,
                best_ask=item.market.best_ask,
                spread=item.market.spread,
                tick_size=None,
                liquidity=item.market.liquidity,
                volume=item.market.volume,
                volume_24h=item.market.volume_24h,
                open_interest=item.market.open_interest,
                comment_count=item.market.comment_count,
                competitive=item.market.competitive,
                neg_risk=None,
                orderbook_enabled=None,
                accepting_orders=item.market.accepting_orders,
                time_to_close_seconds=(
                    round(remaining_hours * 3600)
                    if remaining_hours is not None
                    else None
                ),
                raw_payload=item.market.raw_market,
            )
        )
    return contracts


def build_ranking_snapshot_contracts(
    *,
    cycle_id: str,
    selection_view: SelectionView,
    market_snapshot_ids: dict[str, int],
) -> list[RankingSnapshotContract]:
    contracts: list[RankingSnapshotContract] = []
    for entry in selection_view.ranked_entries:
        contracts.append(
            RankingSnapshotContract(
                cycle_id=cycle_id,
                market_snapshot_id=market_snapshot_ids[entry.market_id],
                market_id=entry.market_id,
                rank_position=entry.rank_position,
                base_score=entry.base_score,
                adaptive_rank=entry.adaptive_rank,
                selected_flag=entry.selected_flag,
                eligible_flag=True,
                reject_reason=None if entry.selected_flag else "not_selected",
                ranking_breakdown=entry.ranking_breakdown,
                recommendation_action=entry.recommendation_action,
                recommendation_confidence=entry.recommendation_confidence,
                recommendation_reason=entry.recommendation_reason,
            )
        )
    return contracts


def build_decision_contracts(
    *,
    cycle_id: str,
    selection_view: SelectionView,
    market_snapshot_ids: dict[str, int],
    ranking_snapshot_ids: dict[str, int],
) -> list[DecisionLedgerContract]:
    contracts: list[DecisionLedgerContract] = []
    for decision in selection_view.decisions:
        contracts.append(
            DecisionLedgerContract(
                id=str(uuid4()),
                cycle_id=cycle_id,
                market_snapshot_id=market_snapshot_ids[decision.market_id],
                ranking_snapshot_id=ranking_snapshot_ids.get(decision.market_id),
                market_id=decision.market_id,
                decision_type=decision.decision_type,
                selected=decision.selected,
                reason=decision.reason,
                confidence=decision.confidence,
                trade_type=None,
                bucket_type=decision.bucket_type,
                expected_edge_proxy=decision.expected_edge_proxy,
                invalidation_rules={},
                metadata=decision.metadata,
            )
        )
    return contracts


def build_rejection_contracts(
    *,
    cycle_id: str,
    selection_view: SelectionView,
) -> list[RejectionLedgerContract]:
    contracts: list[RejectionLedgerContract] = []
    for decision in selection_view.decisions:
        if decision.selected or decision.decision_type not in {"SKIP", "BLOCK"}:
            continue
        reason_code = normalize_rejection_reason_code(decision.reason)
        contracts.append(
            RejectionLedgerContract(
                id=str(uuid4()),
                cycle_id=cycle_id,
                market_id=decision.market_id,
                stage="adaptive_selection",
                reason_code=reason_code,
                reason_text=decision.reason,
                payload={
                    "decision_type": decision.decision_type,
                    "confidence": decision.confidence,
                    "bucket_type": decision.bucket_type,
                    "expected_edge_proxy": decision.expected_edge_proxy,
                    "metadata": decision.metadata,
                },
            )
        )
    return contracts


def normalize_rejection_reason_code(reason: str) -> str:
    if reason.startswith("not_selected_higher_ranked:"):
        return "higher_ranked_candidate"
    normalized = reason.strip().lower().replace("-", "_").replace(":", "_")
    normalized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in normalized)
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized[:64] or "unknown_rejection"
