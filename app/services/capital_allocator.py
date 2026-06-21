from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.stage4 import Stage4ExecutionClient, Stage4Settings, get_stage4_settings

OPEN_PAPER_ORDER_STATUSES = ("CREATED", "OPEN", "PARTIALLY_FILLED")
OPEN_PAPER_POSITION_STATUSES = ("OPEN", "EXIT_PENDING")


@dataclass(slots=True)
class CapitalSnapshot:
    source_mode: str
    total_equity_usd: float
    available_cash_usd: float
    reserved_cash_usd: float
    deployed_notional_usd: float
    pending_notional_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    open_positions_count: int
    pending_orders_count: int
    timestamp: datetime
    source_status: str = "READY"
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "source_mode": self.source_mode,
            "total_equity_usd": round(self.total_equity_usd, 6),
            "available_cash_usd": round(self.available_cash_usd, 6),
            "reserved_cash_usd": round(self.reserved_cash_usd, 6),
            "deployed_notional_usd": round(self.deployed_notional_usd, 6),
            "pending_notional_usd": round(self.pending_notional_usd, 6),
            "realized_pnl_usd": round(self.realized_pnl_usd, 6),
            "unrealized_pnl_usd": round(self.unrealized_pnl_usd, 6),
            "open_positions_count": self.open_positions_count,
            "pending_orders_count": self.pending_orders_count,
            "timestamp": self.timestamp.isoformat(),
            "source_status": self.source_status,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AllocationDecision:
    action: str
    approved_notional_usd: float
    allocation_priority_score: float
    reason_code: str
    reason_text: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "approved_notional_usd": round(self.approved_notional_usd, 6),
            "allocation_priority_score": round(self.allocation_priority_score, 6),
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "metadata": dict(self.metadata),
        }


class CapitalSource:
    def snapshot(self) -> CapitalSnapshot:
        raise NotImplementedError


class PaperCapitalSource(CapitalSource):
    def __init__(
        self,
        *,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        stage4_settings: Stage4Settings | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = stage4_settings or get_stage4_settings()

    def snapshot(self) -> CapitalSnapshot:
        starting_capital = float(self._stage4_settings.paper_starting_capital_usd)
        if not self._factory.enabled:
            reserve_target = round(starting_capital * self._stage4_settings.paper_min_cash_reserve_pct, 6)
            return CapitalSnapshot(
                source_mode="paper",
                total_equity_usd=starting_capital,
                available_cash_usd=starting_capital,
                reserved_cash_usd=reserve_target,
                deployed_notional_usd=0.0,
                pending_notional_usd=0.0,
                realized_pnl_usd=0.0,
                unrealized_pnl_usd=0.0,
                open_positions_count=0,
                pending_orders_count=0,
                timestamp=datetime.now(UTC),
                source_status="DB_DISABLED",
                metadata=self._policy_metadata(total_equity_usd=starting_capital, reserve_target_usd=reserve_target),
            )

        with self._factory.connect() as conn:
            positions = conn.execute(
                """
                SELECT
                    COALESCE(SUM(size * COALESCE(avg_entry, 0)) FILTER (
                        WHERE closed_at IS NULL
                          AND current_status = ANY(%s)
                    ), 0) AS deployed_notional,
                    COALESCE(SUM(realized), 0) AS realized_pnl,
                    COALESCE(SUM(unrealized) FILTER (WHERE closed_at IS NULL), 0) AS unrealized_pnl,
                    COUNT(*) FILTER (
                        WHERE closed_at IS NULL
                          AND current_status = ANY(%s)
                    ) AS open_positions_count
                FROM paper_positions
                """,
                (list(OPEN_PAPER_POSITION_STATUSES), list(OPEN_PAPER_POSITION_STATUSES)),
            ).fetchone()
            orders = conn.execute(
                """
                SELECT
                    COALESCE(SUM(remaining_size * COALESCE(avg_fill_price, intended_price, 0)) FILTER (
                        WHERE status = ANY(%s)
                    ), 0) AS pending_notional,
                    COUNT(*) FILTER (WHERE status = ANY(%s)) AS pending_orders_count
                FROM paper_orders
                """,
                (list(OPEN_PAPER_ORDER_STATUSES), list(OPEN_PAPER_ORDER_STATUSES)),
            ).fetchone()

        deployed_notional = float(positions["deployed_notional"] or 0.0)
        pending_notional = float(orders["pending_notional"] or 0.0)
        realized_pnl = float(positions["realized_pnl"] or 0.0)
        unrealized_pnl = float(positions["unrealized_pnl"] or 0.0)
        open_positions_count = int(positions["open_positions_count"] or 0)
        pending_orders_count = int(orders["pending_orders_count"] or 0)
        total_equity = round(starting_capital + realized_pnl + unrealized_pnl, 6)
        available_cash = round(max(starting_capital + realized_pnl - deployed_notional - pending_notional, 0.0), 6)
        reserve_target = round(max(total_equity, 0.0) * self._stage4_settings.paper_min_cash_reserve_pct, 6)
        reserved_cash = round(min(available_cash, reserve_target), 6)
        return CapitalSnapshot(
            source_mode="paper",
            total_equity_usd=total_equity,
            available_cash_usd=available_cash,
            reserved_cash_usd=reserved_cash,
            deployed_notional_usd=round(deployed_notional, 6),
            pending_notional_usd=round(pending_notional, 6),
            realized_pnl_usd=round(realized_pnl, 6),
            unrealized_pnl_usd=round(unrealized_pnl, 6),
            open_positions_count=open_positions_count,
            pending_orders_count=pending_orders_count,
            timestamp=datetime.now(UTC),
            source_status="READY",
            metadata=self._policy_metadata(total_equity_usd=total_equity, reserve_target_usd=reserve_target),
        )

    def _policy_metadata(self, *, total_equity_usd: float, reserve_target_usd: float) -> dict[str, object]:
        return {
            "starting_capital_usd": round(self._stage4_settings.paper_starting_capital_usd, 6),
            "reserve_target_usd": round(reserve_target_usd, 6),
            "paper_min_cash_reserve_pct": self._stage4_settings.paper_min_cash_reserve_pct,
            "paper_max_alloc_per_trade_pct": self._stage4_settings.paper_max_alloc_per_trade_pct,
            "paper_max_total_deployment_pct": self._stage4_settings.paper_max_total_deployment_pct,
            "max_alloc_per_trade_usd": round(max(total_equity_usd, 0.0) * self._stage4_settings.paper_max_alloc_per_trade_pct, 6),
            "max_total_deployment_usd": round(max(total_equity_usd, 0.0) * self._stage4_settings.paper_max_total_deployment_pct, 6),
        }


class LiveCapitalSource(CapitalSource):
    def __init__(
        self,
        *,
        execution_client: Stage4ExecutionClient | None = None,
        stage4_settings: Stage4Settings | None = None,
    ) -> None:
        self._stage4_settings = stage4_settings or get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._stage4_settings)

    def snapshot(self) -> CapitalSnapshot:
        timestamp = datetime.now(UTC)
        if not self._stage4_settings.live_trading_enabled or self._stage4_settings.live_kill_switch:
            return CapitalSnapshot(
                source_mode="live",
                total_equity_usd=0.0,
                available_cash_usd=0.0,
                reserved_cash_usd=0.0,
                deployed_notional_usd=0.0,
                pending_notional_usd=0.0,
                realized_pnl_usd=0.0,
                unrealized_pnl_usd=0.0,
                open_positions_count=0,
                pending_orders_count=0,
                timestamp=timestamp,
                source_status="DISABLED",
                metadata={
                    "balance_source": "venue_balance_allowance",
                    "reason": "live_trading_disabled_or_kill_switch_active",
                    "live_trading_enabled": self._stage4_settings.live_trading_enabled,
                    "live_kill_switch": self._stage4_settings.live_kill_switch,
                },
            )
        if not self._stage4_settings.has_l2_credentials:
            return CapitalSnapshot(
                source_mode="live",
                total_equity_usd=0.0,
                available_cash_usd=0.0,
                reserved_cash_usd=0.0,
                deployed_notional_usd=0.0,
                pending_notional_usd=0.0,
                realized_pnl_usd=0.0,
                unrealized_pnl_usd=0.0,
                open_positions_count=0,
                pending_orders_count=0,
                timestamp=timestamp,
                source_status="UNAVAILABLE",
                metadata={
                    "balance_source": "venue_balance_allowance",
                    "error": "live authenticated balance source is not configured",
                },
            )
        try:
            balance_info = self._execution_client.get_balance_allowance(token_id=None)
            collateral = dict(balance_info.get("collateral") or {})
            available_cash = float(collateral.get("balance_usd") or 0.0)
            return CapitalSnapshot(
                source_mode="live",
                total_equity_usd=round(available_cash, 6),
                available_cash_usd=round(available_cash, 6),
                reserved_cash_usd=0.0,
                deployed_notional_usd=0.0,
                pending_notional_usd=0.0,
                realized_pnl_usd=0.0,
                unrealized_pnl_usd=0.0,
                open_positions_count=0,
                pending_orders_count=0,
                timestamp=timestamp,
                source_status="READY",
                metadata={
                    "balance_source": "venue_balance_allowance",
                    "balance_info": balance_info,
                },
            )
        except Exception as exc:
            return CapitalSnapshot(
                source_mode="live",
                total_equity_usd=0.0,
                available_cash_usd=0.0,
                reserved_cash_usd=0.0,
                deployed_notional_usd=0.0,
                pending_notional_usd=0.0,
                realized_pnl_usd=0.0,
                unrealized_pnl_usd=0.0,
                open_positions_count=0,
                pending_orders_count=0,
                timestamp=timestamp,
                source_status="UNAVAILABLE",
                metadata={
                    "balance_source": "venue_balance_allowance",
                    "error": str(exc),
                },
            )


class CapitalAllocator:
    def __init__(self, stage4_settings: Stage4Settings | None = None) -> None:
        self._stage4_settings = stage4_settings or get_stage4_settings()

    def plan_entry(
        self,
        *,
        snapshot: CapitalSnapshot,
        market_id: str,
        total_rank: float,
        confidence: float,
    ) -> AllocationDecision:
        priority_score = round(self._priority_score(total_rank=total_rank, confidence=confidence), 6)
        if snapshot.source_mode != "paper":
            return AllocationDecision(
                action="SKIP",
                approved_notional_usd=0.0,
                allocation_priority_score=priority_score,
                reason_code="capital_source_not_supported",
                reason_text=f"{snapshot.source_mode} capital allocation is not armed for this path yet",
                metadata={"source_status": snapshot.source_status},
            )

        reserve_target_usd = float(snapshot.metadata.get("reserve_target_usd") or snapshot.reserved_cash_usd or 0.0)
        max_alloc_per_trade_usd = float(snapshot.metadata.get("max_alloc_per_trade_usd") or 0.0)
        max_total_deployment_usd = float(snapshot.metadata.get("max_total_deployment_usd") or 0.0)
        cash_headroom = round(max(snapshot.available_cash_usd - reserve_target_usd, 0.0), 6)
        deployment_headroom = round(
            max(max_total_deployment_usd - snapshot.deployed_notional_usd - snapshot.pending_notional_usd, 0.0),
            6,
        )
        approved_notional = round(min(max_alloc_per_trade_usd, cash_headroom, deployment_headroom), 6)
        metadata = {
            "market_id": market_id,
            "cash_headroom_usd": cash_headroom,
            "deployment_headroom_usd": deployment_headroom,
            "max_alloc_per_trade_usd": max_alloc_per_trade_usd,
            "max_total_deployment_usd": max_total_deployment_usd,
            "reserve_target_usd": reserve_target_usd,
            "available_cash_usd": round(snapshot.available_cash_usd, 6),
            "priority_score": priority_score,
        }

        if approved_notional <= 0:
            if cash_headroom <= 0:
                return AllocationDecision(
                    action="RESERVE_ONLY",
                    approved_notional_usd=0.0,
                    allocation_priority_score=priority_score,
                    reason_code="cash_reserved",
                    reason_text="available paper cash is fully reserved for higher-conviction opportunities",
                    metadata=metadata,
                )
            return AllocationDecision(
                action="SKIP",
                approved_notional_usd=0.0,
                allocation_priority_score=priority_score,
                reason_code="deployment_cap_reached",
                reason_text="paper deployment cap has already been reached",
                metadata=metadata,
            )

        return AllocationDecision(
            action="ENTER",
            approved_notional_usd=approved_notional,
            allocation_priority_score=priority_score,
            reason_code="capital_allocated",
            reason_text="paper capital is available for bounded deployment",
            metadata=metadata,
        )

    def reserve_pending_allocation(self, snapshot: CapitalSnapshot, *, approved_notional_usd: float) -> CapitalSnapshot:
        reserved_notional = round(max(approved_notional_usd, 0.0), 6)
        available_cash = round(max(snapshot.available_cash_usd - reserved_notional, 0.0), 6)
        pending_notional = round(snapshot.pending_notional_usd + reserved_notional, 6)
        reserve_target = float(snapshot.metadata.get("reserve_target_usd") or 0.0)
        updated_metadata = dict(snapshot.metadata)
        updated_metadata["provisional_pending_notional_usd"] = pending_notional
        return CapitalSnapshot(
            source_mode=snapshot.source_mode,
            total_equity_usd=snapshot.total_equity_usd,
            available_cash_usd=available_cash,
            reserved_cash_usd=round(min(available_cash, reserve_target), 6),
            deployed_notional_usd=snapshot.deployed_notional_usd,
            pending_notional_usd=pending_notional,
            realized_pnl_usd=snapshot.realized_pnl_usd,
            unrealized_pnl_usd=snapshot.unrealized_pnl_usd,
            open_positions_count=snapshot.open_positions_count,
            pending_orders_count=snapshot.pending_orders_count + 1,
            timestamp=datetime.now(UTC),
            source_status=snapshot.source_status,
            metadata=updated_metadata,
        )

    @staticmethod
    def _priority_score(*, total_rank: float, confidence: float) -> float:
        normalized_rank = min(max(total_rank / 100.0, 0.0), 1.0)
        normalized_confidence = min(max(confidence, 0.0), 1.0)
        return round((normalized_rank * 0.7) + (normalized_confidence * 0.3), 6)
