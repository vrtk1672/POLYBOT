from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_trade_service_has_no_order_creation_paths():
    text = (ROOT / "app" / "no_trade" / "service.py").read_text(encoding="utf-8")
    forbidden = ["INSERT INTO orders", "INSERT INTO order_intents", "create_live_order", "send_live", "external_balance"]
    assert not any(token in text for token in forbidden)


def test_migration_is_no_trade_only():
    text = (ROOT / "app" / "db" / "migrations" / "0055_v2_17_no_trade_intelligence.sql").read_text(encoding="utf-8")
    assert "no_trade_log" in text
    assert "order_intents" not in text
    assert "live_orders" not in text
