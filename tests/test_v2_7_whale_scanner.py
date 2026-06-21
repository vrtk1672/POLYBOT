from app.whale_neuron.scanner import WhaleScanner


def test_manual_scanner_marks_whale_and_low_size():
    scanner = WhaleScanner()
    event = scanner.ingest_manual_event({"source_id": "manual", "size_usd": 12000, "action_type": "BUY"})
    small = scanner.ingest_manual_event({"source_id": "manual", "size_usd": 100, "action_type": "BUY"})
    assert event["potential_whale"] is True
    assert small["potential_whale"] is False
    assert event["raw_event_hash"] == scanner.ingest_manual_event({"source_id": "manual", "size_usd": 12000, "action_type": "BUY", "event_time": event["event_time"]})["raw_event_hash"]


def test_bad_source_does_not_block_all():
    assert WhaleScanner().scan_all_enabled(limit_per_source=1) == []

