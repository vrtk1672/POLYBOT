from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_exit_cortex_has_no_live_send_paths():
    service = (ROOT / "app" / "exit_cortex" / "service.py").read_text(encoding="utf-8")
    forbidden = ["create_live_order", "submit_live", "send_live", "polymarket_client", "external_balance"]
    assert not any(token in service for token in forbidden)


def test_exit_intents_are_internal_paper_shadow_only():
    migration = (ROOT / "app" / "db" / "migrations" / "0054_v2_16_exit_cortex_v2.sql").read_text(encoding="utf-8")
    assert "PAPER_SIM_EXIT" in migration
    assert "SHADOW_EXIT_PLAN" in migration
    assert "LIVE_EXIT" in migration
    assert "paper_shadow_only IS TRUE" in migration
