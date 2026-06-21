from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(slots=True)
class MarketRecord:
    market_id: str
    question: str
    slug: str | None = None
    category: str | None = None
    market_family: str | None = None
    condition_id: str | None = None
    yes_token_id: str | None = None
    no_token_id: str | None = None
    outcome_tokens_json: dict[str, object] = field(default_factory=dict)
    resolution_source: str | None = None
    accepting_orders: bool | None = None
    closed: bool = False
    archived: bool = False
    active: bool = True
    close_time: datetime | None = None
    resolution_time: datetime | None = None
    raw_market_json: dict[str, object] = field(default_factory=dict)
    metadata_json: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class MarketRulesRecord:
    market_id: str
    rules_text: str | None = None
    resolution_source: str | None = None
    resolution_source_url: str | None = None
    resolution_source_status: str = "MISSING"
    resolution_source_type: str = "MISSING"
    resolution_source_evidence: str | None = None
    resolution_source_confidence: float = 0.0
    resolution_source_penalty: float = 0.45
    resolution_source_hard_block: bool = False
    settlement_method: str | None = None
    deadline_at: datetime | None = None
    rules_hash: str | None = None
    ambiguity_flags_json: list[object] = field(default_factory=list)
    raw_rules_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MarketSnapshotV2:
    snapshot_id: str
    market_id: str
    cycle_id: str | None = None
    correlation_id: str | None = None
    current_price_yes: float | None = None
    current_price_no: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    volume_1h: float | None = None
    volume_24h: float | None = None
    liquidity: float | None = None
    time_to_close_seconds: int | None = None
    accepting_orders: bool | None = None
    closed: bool | None = None
    data_completeness_score: float = 0.0
    stale: bool = False
    snapshot_at: datetime | None = None
    raw_snapshot_json: dict[str, object] = field(default_factory=dict)
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class OrderbookSnapshot:
    orderbook_snapshot_id: str
    market_id: str
    token_id: str | None = None
    side: str | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    mid_price: float | None = None
    depth_1c: float | None = None
    depth_2c: float | None = None
    depth_5c: float | None = None
    depth_bid_1c: float | None = None
    depth_ask_1c: float | None = None
    depth_bid_2c: float | None = None
    depth_ask_2c: float | None = None
    depth_bid_5c: float | None = None
    depth_ask_5c: float | None = None
    total_bid_depth: float | None = None
    total_ask_depth: float | None = None
    liquidity_score: float | None = None
    source: str = "unknown"
    snapshot_status: str = "OK"
    is_stale: bool = False
    stale_reason: str | None = None
    raw_payload_ref: str | None = None
    correlation_id: str | None = None
    collected_at: datetime | None = None
    bid_depth_json: list[dict[str, object]] = field(default_factory=list)
    ask_depth_json: list[dict[str, object]] = field(default_factory=list)
    imbalance: float | None = None
    raw_orderbook_json: dict[str, object] = field(default_factory=dict)
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class LiquiditySnapshot:
    liquidity_snapshot_id: str
    market_id: str
    orderbook_snapshot_id: str | None = None
    liquidity_score: float = 0.0
    exit_quality: float = 0.0
    expected_slippage_small: float | None = None
    expected_slippage_medium: float | None = None
    expected_slippage_large: float | None = None
    max_safe_size: float | None = None
    fill_probability: float | None = None
    liquidity_usd: float | None = None
    depth_1c: float | None = None
    depth_2c: float | None = None
    depth_5c: float | None = None
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class FeeSnapshot:
    fee_snapshot_id: str
    market_id: str
    maker_fee: float | None = None
    taker_fee: float | None = None
    spread_cost: float | None = None
    estimated_slippage_cost: float | None = None
    reward_pool: float | None = None
    reward_rate: float | None = None
    net_edge_adjustment: float | None = None
    raw_fee_json: dict[str, object] = field(default_factory=dict)
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class DataCompletenessScore:
    market_id: str
    has_market_id: bool
    has_question: bool
    has_tokens: bool
    has_price: bool
    has_orderbook: bool
    has_rules: bool
    has_liquidity: bool
    has_time_to_close: bool
    has_resolution_source: bool
    score: float
    missing_fields: list[str] = field(default_factory=list)
    stale_fields: list[str] = field(default_factory=list)
    candidate_allowed: bool = False
    no_trade_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
