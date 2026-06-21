from app.db.migrate import run_migrations
from app.whale_neuron.service import WhaleNeuronService


def test_manual_whale_event_pipeline_persists_core_records(postgres_test_schema):
    run_migrations()
    service = WhaleNeuronService()
    summary = service.process_manual_whale_event({"source_id": "manual", "whale_id": "wpipe", "wallet_address": "0xpipe", "side": "YES", "action_type": "BUY", "size_usd": 12000, "price": 0.42})
    assert summary["whale_id"] == "wpipe"
    assert summary["event_created"] is True
    assert summary["profile"]["sample_size"] >= 1
    assert summary["categories"]
    assert summary["follow_decision"]["decision"] in {"WATCH", "INSUFFICIENT_DATA", "FOLLOW", "IGNORE", "PENALIZE"}

