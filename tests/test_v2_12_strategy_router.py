from app.strategy.router import StrategyRouter


def _base():
    return {
        "market_id": "m1",
        "side": "YES",
        "opportunity_score": 0.82,
        "opportunity_score_band": "STRONG",
        "candidate_engines_from_opportunity": ["SAFE", "STRIKE", "CONVEX"],
        "opportunity_components": {
            "confidence": 0.86,
            "trigger_strength": 0.78,
            "repricing_potential": 0.76,
            "time_efficiency": 0.7,
            "liquidity_quality": 0.82,
            "exit_probability": 0.83,
            "convexity": 0.72,
            "wording_risk": 0.08,
            "risk_penalty": 0.1,
            "trap_risk": 0.1,
            "already_priced_in_score": 0.12,
            "capital_allowed": True,
            "max_safe_size_usd": 1000,
        },
        "context_output": {"context_shift": True},
        "capital_output": {"capital_allowed": True, "max_position_size_usd": 500},
        "technical_truth": {"orderbook_signal": {"has_bid_ask": True, "depth_2c": 700}, "liquidity_signal": {"max_safe_size_usd": 1000}},
        "data_completeness_score": 1.0,
    }


def test_router_revalidates_candidates_and_selects_one_route():
    from app.strategy.contracts import StrategyRouteInput

    route = StrategyRouter().route(StrategyRouteInput(**_base()))
    assert route.selected_engine in {"SAFE", "STRIKE", "CONVEX"}
    assert len([d for d in route.engine_decisions if d.selected]) == 1
    assert route.contract is not None
    assert route.contract.execution_mode == "CONTRACT_ONLY"


def test_hard_blocks_force_no_trade():
    from app.strategy.contracts import StrategyRouteInput

    payload = _base()
    payload["opportunity_score_band"] = "BLOCKED"
    payload["opportunity_risk_flags"] = [{"risk_flag": "missing_bid_ask", "severity": "BLOCKING", "blocks_opportunity": True}]
    route = StrategyRouter().route(StrategyRouteInput(**payload))
    assert route.selected_engine == "NO_TRADE"
    assert route.route_status == "BLOCKED"


def test_reproducibility_hash_stable_for_same_inputs():
    from app.strategy.contracts import StrategyRouteInput

    payload = StrategyRouteInput(**_base())
    a = StrategyRouter().route(payload).reproducibility_hash
    b = StrategyRouter().route(payload).reproducibility_hash
    assert a == b

