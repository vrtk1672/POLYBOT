from __future__ import annotations

from app.services.opportunity_memory import evidence_fingerprint, fingerprint_payload_from_row


def test_evidence_fingerprint_ignores_runtime_decision_id_but_tracks_meaningful_score_change() -> None:
    base = {
        "decision_id": "decision-old",
        "market_id": "market-fingerprint",
        "condition_id": "condition-market-fingerprint",
        "side": "YES",
        "token_id": "token-market-fingerprint-YES",
        "decision": "ENTER",
        "opportunity_score": 55.46,
        "blockers_json": [],
        "evidence": {
            "paper_defense": {"defense_level": 20, "profile": {"adjusted_threshold": 42}},
            "orderbook_best_ask": 0.51,
        },
    }
    same_evidence_new_decision = {**base, "decision_id": "decision-new"}
    changed_score = {**base, "decision_id": "decision-newer", "opportunity_score": 60.0}

    base_hash = evidence_fingerprint(fingerprint_payload_from_row(base))
    assert evidence_fingerprint(fingerprint_payload_from_row(same_evidence_new_decision)) == base_hash
    assert evidence_fingerprint(fingerprint_payload_from_row(changed_score)) != base_hash
