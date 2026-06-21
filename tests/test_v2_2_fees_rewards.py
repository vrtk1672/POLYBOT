from __future__ import annotations

from app.data_foundation.fees_rewards_collector import FeesRewardsCollector
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_unknown_fees_handled_honestly() -> None:
    snapshot = FeesRewardsCollector().extract_fees_rewards({}, market_id="m1")
    assert snapshot.maker_fee is None
    assert snapshot.metadata_json["fees_available"] is False


def test_spread_cost_calculated() -> None:
    snapshot = FeesRewardsCollector().extract_fees_rewards({}, market_id="m1", spread=0.04)
    assert snapshot.spread_cost == 0.02


def test_net_edge_adjustment_calculated_when_inputs_exist() -> None:
    snapshot = FeesRewardsCollector().extract_fees_rewards(
        {"makerFee": "0.001", "takerFee": "0.002", "rewardRate": "0.01"},
        market_id="m1",
        spread=0.02,
        estimated_slippage_cost=0.003,
    )
    assert snapshot.net_edge_adjustment == -0.006


def test_fee_snapshot_saved(postgres_test_schema) -> None:
    run_migrations()
    collector = FeesRewardsCollector()
    snapshot = collector.extract_fees_rewards({"makerFee": "0.001"}, market_id="m1")
    collector.persist_fee_snapshot(snapshot)
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM fee_snapshots WHERE fee_snapshot_id = %s", (snapshot.fee_snapshot_id,)).fetchone()
    assert row is not None
