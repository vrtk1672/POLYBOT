from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.exit_quality import ExitQualityScorer
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_exit_quality_is_recorded_with_flags():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    quality = ExitQualityScorer().score(plan=plan, current=current_market(expected_slippage_bps=300, exit_quality_score=0.1))
    assert quality.exit_quality_score < 1
    assert "high_exit_slippage" in quality.quality_flags
    assert "low_exit_liquidity" in quality.quality_flags

