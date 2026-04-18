from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import brain
from app.models.market import NormalizedMarket
from app.models.score import ScoreBreakdown, ScoredMarket
from app.stage2.claude_analyst import MarketRecommendation
from app.stage4.auth import resolve_signature_type, validate_stage4_credentials
from app.stage4.buckets import compute_bucket_targets, recommended_bucket_notional
from app.stage4.config import Stage4Settings
from app.stage4.execution_policy import evaluate_execution_policy
from app.stage4.execution_client import normalize_usdc_balance
from app.stage4.live_guard import LiveGuard
from app.stage4.order_builder import LiveOrderValidationError, build_live_order_intent
from app.stage4.ranking import rank_candidates
from app.stage4.universe import build_allowed_universe


def _make_scored_market(
    *,
    market_id: str,
    question: str,
    yes_price: float,
    no_price: float,
    score: float,
    accepting_orders: bool = True,
    liquidity: float = 10000.0,
    volume_24h: float = 25000.0,
) -> ScoredMarket:
    return ScoredMarket(
        market=NormalizedMarket(
            market_id=market_id,
            event_id=f"evt-{market_id}",
            event_title=question,
            question=question,
            yes_price=yes_price,
            no_price=no_price,
            liquidity=liquidity,
            volume_24h=volume_24h,
            accepting_orders=accepting_orders,
            raw_market={
                "clobTokenIds": [
                    f"{market_id}1",
                    f"{market_id}2",
                ]
            },
        ),
        score=score,
        breakdown=ScoreBreakdown(
            price_attractiveness=25.0,
            time_to_close=20.0,
            liquidity_volume=15.0,
            market_activity=10.0,
        ),
        reason="test",
        computed_at=datetime.now(UTC),
    )


def _make_recommendation(
    *,
    rank: int,
    question: str,
    action: str,
    confidence: float,
    score: float,
    yes_price: float,
    no_price: float,
) -> MarketRecommendation:
    return MarketRecommendation(
        rank=rank,
        question=question,
        confidence=confidence,
        action=action,
        reason="test edge",
        yes_price=yes_price,
        no_price=no_price,
        score=score,
        computed_at=datetime.now(UTC).isoformat(),
    )


def test_bucket_targets_are_deterministic() -> None:
    targets = compute_bucket_targets(1000.0)
    assert targets.safe == 50.0
    assert targets.high == 100.0
    assert targets.whale == 150.0
    assert targets.reserve == 700.0
    assert recommended_bucket_notional(1000.0, "whale", max_order_usd=2.0) == 2.0


def test_usdc_balance_normalization_uses_6_decimals() -> None:
    assert normalize_usdc_balance("14580000") == 14.58


def test_bucket_targets_use_normalized_balance() -> None:
    targets = compute_bucket_targets(normalize_usdc_balance("14580000"))
    assert targets.safe == 0.73
    assert targets.high == 1.46
    assert targets.whale == 2.19
    assert targets.reserve == 10.21


def test_order_builder_rejects_below_minimum_size_when_cap_too_small() -> None:
    scored = _make_scored_market(
        market_id="564198",
        question="Pistons",
        yes_price=0.20,
        no_price=0.80,
        score=70.8,
    )
    recommendation = _make_recommendation(
        rank=1,
        question="Pistons",
        action="BUY_NO",
        confidence=0.75,
        score=70.8,
        yes_price=0.20,
        no_price=0.80,
    )
    with pytest.raises(LiveOrderValidationError, match="minimum size"):
        build_live_order_intent(
            scored,
            recommendation,
            bucket="whale",
            tick_size="0.01",
            neg_risk=True,
            min_order_size=5.0,
            max_order_usd=1.0,
            balance_hint=100.0,
        )


def test_order_builder_resizes_up_to_minimum_when_within_cap() -> None:
    scored = _make_scored_market(
        market_id="600001",
        question="Cheap YES",
        yes_price=0.10,
        no_price=0.90,
        score=68.0,
    )
    recommendation = _make_recommendation(
        rank=1,
        question="Cheap YES",
        action="BUY_YES",
        confidence=0.70,
        score=68.0,
        yes_price=0.10,
        no_price=0.90,
    )
    intent = build_live_order_intent(
        scored,
        recommendation,
        bucket="safe",
        tick_size="0.01",
        neg_risk=True,
        min_order_size=5.0,
        max_order_usd=1.0,
        balance_hint=100.0,
    )
    assert intent.size >= 5.0
    assert intent.notional_usd == 1.0


def test_live_guard_blocks_unarmed_unwhitelisted_live_order() -> None:
    settings = Stage4Settings(
        LIVE_TRADING_ENABLED=True,
        LIVE_MAX_ORDER_USD=2,
        LIVE_MARKET_WHITELIST="abc123",
        LIVE_KILL_SWITCH=False,
    )
    decision = LiveGuard(settings).evaluate_order(
        market_id="not-listed",
        notional_usd=3.0,
        live=True,
        armed=False,
    )
    assert decision.allowed is False
    assert any("--armed" in reason for reason in decision.reasons)
    assert any("not in LIVE_MARKET_WHITELIST" in reason for reason in decision.reasons)
    assert any("exceeds LIVE_MAX_ORDER_USD" in reason for reason in decision.reasons)


def test_live_guard_allows_empty_whitelist_in_adaptive_mode() -> None:
    settings = Stage4Settings(
        LIVE_TRADING_ENABLED=False,
        LIVE_MAX_ORDER_USD=2,
        LIVE_MARKET_WHITELIST="",
        LIVE_OPTIONAL_WHITELIST_MODE="subset",
    )
    decision = LiveGuard(settings).evaluate_order(
        market_id="553866",
        notional_usd=1.0,
        live=False,
        armed=False,
    )
    assert decision.allowed is True


def test_auth_validation_flags_missing_wallet_requirements() -> None:
    settings = Stage4Settings(
        _env_file=None,
        poly_api_key="key",
        poly_api_secret="secret",
        poly_api_passphrase="pass",
    )
    validation = validate_stage4_credentials(settings)
    assert validation.ok is False
    assert "POLY_PRIVATE_KEY is missing" in validation.errors
    assert "POLY_FUNDER is missing" in validation.errors


def test_signature_type_infers_eoa_when_signer_matches_funder() -> None:
    settings = Stage4Settings(
        _env_file=None,
        POLY_PRIVATE_KEY="0x90620ca77857c83820cb3921f415fe51e528a8ff20b6ee2486e8b4ca40578c8e",
        POLY_FUNDER="0x7D631aF4CE17Adb6fB50e77D4A240Ae39e01811A",
    )
    assert "poly_signature_type" not in settings.model_fields_set
    assert resolve_signature_type(settings) == 0


def test_signature_type_respects_explicit_override() -> None:
    settings = Stage4Settings(
        _env_file=None,
        POLY_PRIVATE_KEY="0x90620ca77857c83820cb3921f415fe51e528a8ff20b6ee2486e8b4ca40578c8e",
        POLY_FUNDER="0x7D631aF4CE17Adb6fB50e77D4A240Ae39e01811A",
        POLY_SIGNATURE_TYPE=2,
    )
    assert resolve_signature_type(settings) == 2


def test_whitelist_single_value_env_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_MARKET_WHITELIST", "553866")
    settings = Stage4Settings()
    assert settings.live_market_whitelist == ["553866"]


def test_whitelist_csv_env_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_MARKET_WHITELIST", "553866,777777")
    settings = Stage4Settings()
    assert settings.live_market_whitelist == ["553866", "777777"]


def test_whitelist_csv_env_parses_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_MARKET_WHITELIST", " 553866 , 777777 ")
    settings = Stage4Settings()
    assert settings.live_market_whitelist == ["553866", "777777"]


def test_empty_whitelist_allows_adaptive_universe() -> None:
    scored = [
        _make_scored_market(
            market_id="553866",
            question="Will the San Antonio Spurs win the 2026 NBA Finals?",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        )
    ]
    recs = [
        _make_recommendation(
            rank=1,
            question=scored[0].market.question,
            action="BUY_NO",
            confidence=0.68,
            score=scored[0].score,
            yes_price=0.15,
            no_price=0.85,
        )
    ]
    settings = Stage4Settings(_env_file=None, LIVE_MARKET_WHITELIST="")
    allowed, skipped = build_allowed_universe(scored, recs, settings)
    assert len(allowed) == 1
    assert skipped == []


def test_whitelist_subset_narrows_adaptive_universe() -> None:
    scored = [
        _make_scored_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        ),
        _make_scored_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            score=72.5,
        ),
    ]
    recs = [
        _make_recommendation(rank=1, question="Spurs", action="BUY_NO", confidence=0.68, score=71.2, yes_price=0.15, no_price=0.85),
        _make_recommendation(rank=2, question="PSG", action="BUY_NO", confidence=0.72, score=72.5, yes_price=0.25, no_price=0.75),
    ]
    settings = Stage4Settings(_env_file=None, LIVE_MARKET_WHITELIST="553866")
    allowed, skipped = build_allowed_universe(scored, recs, settings)
    assert [candidate.market.market_id for candidate in allowed] == ["553866"]
    assert any("outside_whitelist_subset" in reason for reason in skipped)


def test_ranking_engine_is_deterministic() -> None:
    scored = [
        _make_scored_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        ),
        _make_scored_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            score=72.5,
        ),
    ]
    recs = [
        _make_recommendation(rank=1, question="Spurs", action="BUY_NO", confidence=0.68, score=71.2, yes_price=0.15, no_price=0.85),
        _make_recommendation(rank=2, question="PSG", action="BUY_NO", confidence=0.72, score=72.5, yes_price=0.25, no_price=0.75),
    ]
    settings = Stage4Settings(_env_file=None, LIVE_MARKET_WHITELIST="")
    allowed, _ = build_allowed_universe(scored, recs, settings)
    ranked = rank_candidates(allowed)
    assert [entry.candidate.market.market_id for entry in ranked] == ["566136", "553866"]
    assert ranked[0].total_rank >= ranked[1].total_rank


def test_empty_whitelist_selects_best_candidate_automatically() -> None:
    scored = [
        _make_scored_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        ),
        _make_scored_market(
            market_id="564198",
            question="Pistons",
            yes_price=0.20,
            no_price=0.80,
            score=70.8,
        ),
        _make_scored_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            score=72.5,
        ),
    ]
    recs = [
        _make_recommendation(rank=1, question="Spurs", action="BUY_NO", confidence=0.68, score=71.2, yes_price=0.15, no_price=0.85),
        _make_recommendation(rank=2, question="Pistons", action="BUY_NO", confidence=0.70, score=70.8, yes_price=0.20, no_price=0.80),
        _make_recommendation(rank=3, question="PSG", action="BUY_NO", confidence=0.72, score=72.5, yes_price=0.25, no_price=0.75),
    ]
    settings = Stage4Settings(_env_file=None, LIVE_MARKET_WHITELIST="")
    allowed, skipped = build_allowed_universe(scored, recs, settings)
    ranked = rank_candidates(allowed)
    assert skipped == []
    assert ranked[0].candidate.market.market_id == "566136"


def test_execution_policy_blocks_duplicate_same_market_exposure() -> None:
    scored = [
        _make_scored_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        )
    ]
    recs = [
        _make_recommendation(rank=1, question="Spurs", action="BUY_NO", confidence=0.68, score=71.2, yes_price=0.15, no_price=0.85)
    ]
    settings = Stage4Settings(_env_file=None, LIVE_MARKET_WHITELIST="", live_max_same_market_exposure=1)
    allowed, _ = build_allowed_universe(scored, recs, settings)
    ranked = rank_candidates(allowed)
    decision = evaluate_execution_policy(
        ranked[0],
        open_orders=[{"market_id": "553866"}],
        settings=settings,
    )
    assert decision.allowed is False
    assert any("same-market exposure" in reason for reason in decision.reasons)


def test_execution_policy_blocks_when_open_position_limit_reached() -> None:
    scored = [
        _make_scored_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            score=72.5,
        )
    ]
    recs = [
        _make_recommendation(rank=1, question="PSG", action="BUY_NO", confidence=0.72, score=72.5, yes_price=0.25, no_price=0.75)
    ]
    settings = Stage4Settings(_env_file=None, LIVE_MARKET_WHITELIST="", live_max_open_positions=1)
    allowed, _ = build_allowed_universe(scored, recs, settings)
    ranked = rank_candidates(allowed)
    decision = evaluate_execution_policy(
        ranked[0],
        open_orders=[{"market_id": "other-market"}],
        settings=settings,
    )
    assert decision.allowed is False
    assert any("LIVE_MAX_OPEN_POSITIONS" in reason for reason in decision.reasons)


@pytest.mark.asyncio
async def test_live_mode_submits_only_best_candidate_once(monkeypatch: pytest.MonkeyPatch) -> None:
    scored_markets = [
        _make_scored_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        ),
        _make_scored_market(
            market_id="564198",
            question="Pistons",
            yes_price=0.20,
            no_price=0.80,
            score=70.8,
        ),
        _make_scored_market(
            market_id="566136",
            question="PSG",
            yes_price=0.25,
            no_price=0.75,
            score=72.5,
        ),
    ]
    recommendations = [
        _make_recommendation(rank=1, question="Spurs", action="BUY_NO", confidence=0.68, score=71.2, yes_price=0.15, no_price=0.85),
        _make_recommendation(rank=2, question="Pistons", action="BUY_NO", confidence=0.70, score=70.8, yes_price=0.20, no_price=0.80),
        _make_recommendation(rank=3, question="PSG", action="BUY_NO", confidence=0.72, score=72.5, yes_price=0.25, no_price=0.75),
    ]
    submitted_market_ids: list[str] = []

    class FakeExecutionClient:
        def auth_context(self) -> dict[str, str | int]:
            return {"signature_type": 0, "credential_source": "env"}

        def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0.1")

        def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
            return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

        def get_open_orders(self) -> list[dict[str, str]]:
            return []

        def create_signed_order(self, intent):  # noqa: ANN001
            return {"market_id": intent.market_id, "token_id": intent.token_id}

        def submit_order(self, intent):  # noqa: ANN001
            submitted_market_ids.append(intent.market_id)
            return {"response": {"orderID": "abc123", "status": "open"}}

        def get_order_status(self, order_id: str) -> dict[str, str]:
            return {"orderID": order_id, "status": "open"}

    monkeypatch.setattr(
        brain,
        "get_stage4_settings",
        lambda: Stage4Settings(
            LIVE_TRADING_ENABLED=True,
            LIVE_MAX_ORDER_USD=1,
            LIVE_MARKET_WHITELIST="",
        ),
    )
    monkeypatch.setattr(brain, "Stage4ExecutionClient", lambda settings: FakeExecutionClient())

    await brain.handle_live_order_path(
        brain.CycleResult(
            all_scored=scored_markets,
            top_scored=scored_markets,
            recommendations=recommendations,
        ),
        live=True,
        armed=True,
    )

    assert submitted_market_ids == ["566136"]


@pytest.mark.asyncio
async def test_live_mode_falls_back_when_top_candidate_fails_minimum_size(monkeypatch: pytest.MonkeyPatch) -> None:
    scored_markets = [
        _make_scored_market(
            market_id="564198",
            question="Pistons",
            yes_price=0.20,
            no_price=0.80,
            score=70.8,
        ),
        _make_scored_market(
            market_id="600001",
            question="Cheap YES",
            yes_price=0.10,
            no_price=0.90,
            score=68.0,
        ),
    ]
    recommendations = [
        _make_recommendation(rank=1, question="Pistons", action="BUY_NO", confidence=0.75, score=70.8, yes_price=0.20, no_price=0.80),
        _make_recommendation(rank=2, question="Cheap YES", action="BUY_YES", confidence=0.70, score=68.0, yes_price=0.10, no_price=0.90),
    ]
    submitted_market_ids: list[str] = []

    class FakeExecutionClient:
        def auth_context(self) -> dict[str, str | int]:
            return {"signature_type": 0, "credential_source": "env"}

        def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
            if token_id.endswith("2"):
                return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="5")
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="5")

        def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
            return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

        def get_open_orders(self) -> list[dict[str, str]]:
            return []

        def create_signed_order(self, intent):  # noqa: ANN001
            return {"market_id": intent.market_id, "token_id": intent.token_id}

        def submit_order(self, intent):  # noqa: ANN001
            submitted_market_ids.append(intent.market_id)
            return {"response": {"orderID": "fallback", "status": "open"}}

        def get_order_status(self, order_id: str) -> dict[str, str]:
            return {"orderID": order_id, "status": "open"}

    monkeypatch.setattr(
        brain,
        "get_stage4_settings",
        lambda: Stage4Settings(
            LIVE_TRADING_ENABLED=True,
            LIVE_MAX_ORDER_USD=1,
            LIVE_MARKET_WHITELIST="",
        ),
    )
    monkeypatch.setattr(brain, "Stage4ExecutionClient", lambda settings: FakeExecutionClient())

    await brain.handle_live_order_path(
        brain.CycleResult(
            all_scored=scored_markets,
            top_scored=scored_markets,
            recommendations=recommendations,
        ),
        live=True,
        armed=True,
    )

    assert submitted_market_ids == ["600001"]


@pytest.mark.asyncio
async def test_live_mode_does_not_submit_when_all_candidates_fail_minimum_size(monkeypatch: pytest.MonkeyPatch) -> None:
    scored_markets = [
        _make_scored_market(
            market_id="564198",
            question="Pistons",
            yes_price=0.20,
            no_price=0.80,
            score=70.8,
        ),
        _make_scored_market(
            market_id="553866",
            question="Spurs",
            yes_price=0.15,
            no_price=0.85,
            score=71.2,
        ),
    ]
    recommendations = [
        _make_recommendation(rank=1, question="Pistons", action="BUY_NO", confidence=0.75, score=70.8, yes_price=0.20, no_price=0.80),
        _make_recommendation(rank=2, question="Spurs", action="BUY_NO", confidence=0.72, score=71.2, yes_price=0.15, no_price=0.85),
    ]
    submit_called = False

    class FakeExecutionClient:
        def auth_context(self) -> dict[str, str | int]:
            return {"signature_type": 0, "credential_source": "env"}

        def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="5")

        def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
            return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

        def get_open_orders(self) -> list[dict[str, str]]:
            return []

        def create_signed_order(self, intent):  # noqa: ANN001
            return {"market_id": intent.market_id, "token_id": intent.token_id}

        def submit_order(self, intent):  # noqa: ANN001
            nonlocal submit_called
            submit_called = True
            return {"response": {"orderID": "should-not-happen"}}

    monkeypatch.setattr(
        brain,
        "get_stage4_settings",
        lambda: Stage4Settings(
            LIVE_TRADING_ENABLED=True,
            LIVE_MAX_ORDER_USD=1,
            LIVE_MARKET_WHITELIST="",
        ),
    )
    monkeypatch.setattr(brain, "Stage4ExecutionClient", lambda settings: FakeExecutionClient())

    await brain.handle_live_order_path(
        brain.CycleResult(
            all_scored=scored_markets,
            top_scored=scored_markets,
            recommendations=recommendations,
        ),
        live=True,
        armed=True,
    )

    assert submit_called is False


@pytest.mark.asyncio
async def test_live_dry_run_never_submits_even_if_guards_would_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    market = NormalizedMarket(
        market_id="566136",
        event_id="evt-1",
        event_title="Champions League",
        question="Will PSG win the 2025-26 Champions League?",
        yes_price=0.26,
        no_price=0.74,
        accepting_orders=True,
        raw_market={
            "clobTokenIds": [
                "111111111111111111111111111111111111111111111111111111111111111111",
                "222222222222222222222222222222222222222222222222222222222222222222",
            ]
        },
    )
    scored = ScoredMarket(
        market=market,
        score=71.8,
        breakdown=ScoreBreakdown(
            price_attractiveness=25.0,
            time_to_close=20.0,
            liquidity_volume=15.0,
            market_activity=11.8,
        ),
        reason="Test candidate",
        computed_at=datetime.now(UTC),
    )
    recommendation = MarketRecommendation(
        rank=1,
        question=market.question,
        confidence=0.78,
        action="BUY_NO",
        reason="Test edge",
        yes_price=0.26,
        no_price=0.74,
        score=71.8,
        computed_at=datetime.now(UTC).isoformat(),
    )

    submit_called = False

    class FakeExecutionClient:
        def auth_context(self) -> dict[str, str | int]:
            return {"signature_type": 0, "credential_source": "env"}

        def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
            return SimpleNamespace(tick_size="0.01", neg_risk=True, min_order_size="0")

        def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str]]:
            return {"collateral": {"balance": "100000000", "balance_usd": 100.0}}

        def get_open_orders(self) -> list[dict[str, str]]:
            return []

        def create_signed_order(self, intent):  # noqa: ANN001
            return {"token_id": intent.token_id, "size": intent.size}

        def submit_order(self, intent):  # noqa: ANN001
            nonlocal submit_called
            submit_called = True
            return {"response": {"orderID": "should-not-happen"}}

        def get_order_status(self, order_id: str) -> dict[str, str]:
            return {"orderID": order_id}

    monkeypatch.setattr(
        brain,
        "get_stage4_settings",
        lambda: Stage4Settings(
            LIVE_TRADING_ENABLED=True,
            LIVE_MAX_ORDER_USD=2,
            LIVE_MARKET_WHITELIST="566136",
        ),
    )
    monkeypatch.setattr(brain, "Stage4ExecutionClient", lambda settings: FakeExecutionClient())

    await brain.handle_live_order_path(
        brain.CycleResult(
            all_scored=[scored],
            top_scored=[scored],
            recommendations=[recommendation],
        ),
        live=False,
        armed=False,
    )

    assert submit_called is False


@pytest.mark.asyncio
async def test_live_submit_failure_is_reported_without_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    market = _make_scored_market(
        market_id="553866",
        question="Will the San Antonio Spurs win the 2026 NBA Finals?",
        yes_price=0.15,
        no_price=0.85,
        score=71.2,
    )
    recommendation = _make_recommendation(
        rank=1,
        question=market.market.question,
        action="BUY_NO",
        confidence=0.70,
        score=71.2,
        yes_price=0.15,
        no_price=0.85,
    )

    class FakeExecutionClient:
        def auth_context(self) -> dict[str, str | int]:
            return {"signature_type": 0, "credential_source": "env"}

        def get_order_book_summary(self, token_id: str) -> SimpleNamespace:
            return SimpleNamespace(tick_size="0.001", neg_risk=True, min_order_size="0.1")

        def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
            return {"collateral": {"balance": "14580000", "balance_usd": 14.58}}

        def get_open_orders(self) -> list[dict[str, str]]:
            return []

        def create_signed_order(self, intent):  # noqa: ANN001
            return {"token_id": intent.token_id}

        def submit_order(self, intent):  # noqa: ANN001
            raise RuntimeError("invalid signature")

    monkeypatch.setattr(
        brain,
        "get_stage4_settings",
        lambda: Stage4Settings(
            LIVE_TRADING_ENABLED=True,
            LIVE_MAX_ORDER_USD=1,
            LIVE_MARKET_WHITELIST="553866",
        ),
    )
    monkeypatch.setattr(brain, "Stage4ExecutionClient", lambda settings: FakeExecutionClient())

    await brain.handle_live_order_path(
        brain.CycleResult(
            all_scored=[market],
            top_scored=[market],
            recommendations=[recommendation],
        ),
        live=True,
        armed=True,
    )
