from app.exit_cortex.service import ExitCortexService
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_plan_dry_run_writes_nothing():
    result = ExitCortexService().create_plan(market_id="m1", dry_run=True, manual_input=exit_plan_manual())
    assert result["written"] is False
    assert result["plan"]["plan_status"] == "ACTIVE"


def test_runtime_blocks_data_only_persisted_exit_intent():
    service = ExitCortexService()
    plan = service.plan_builder.build(market_id="m1", manual=exit_plan_manual())
    block = service._runtime_block(plan=plan, current=current_market(runtime_mode="DATA_ONLY"), emergency=False)
    assert block == "DATA_ONLY_evaluation_only"


def test_paper_and_shadow_modes_are_separate():
    service = ExitCortexService()
    paper = service.plan_builder.build(market_id="m1", manual=exit_plan_manual(exit_mode="PAPER_SIM_EXIT"))
    shadow = service.plan_builder.build(market_id="m1", manual=exit_plan_manual(exit_mode="SHADOW_EXIT_PLAN"))
    assert service._runtime_block(plan=paper, current=current_market(runtime_mode="PAPER"), emergency=False) is None
    assert service._runtime_block(plan=shadow, current=current_market(runtime_mode="SHADOW_LIVE"), emergency=False) is None
    assert service._runtime_block(plan=paper, current=current_market(runtime_mode="SMALL_LIVE"), emergency=False) == "LIVE_NOT_CERTIFIED"

