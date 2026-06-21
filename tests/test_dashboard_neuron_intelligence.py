from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.neuron_intelligence import NeuronIntelligenceService

from test_neuron_intelligence_pack1_service import _prepare_pack, _seed_pack_sources


def test_dashboard_neuron_intelligence_returns_real_truth(postgres_test_schema) -> None:
    ids = _prepare_pack()
    _seed_pack_sources(str(ids["market_id"]))
    NeuronIntelligenceService().run_pack(cycle_id="pack-dashboard", limit=10)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/neuron-intelligence?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["status"] == "OK"
    assert payload["rules"]["wording_risk_score"] == 0.12
    assert "entry_liquidity_score" in payload["liquidity"]
    assert "estimated_cost" in payload["fees"]
    assert "time_to_resolution" in payload["time"]
    assert payload["news"]["news_impact_score"] == 0.8
    assert len(payload["recent_evidence"]) == 5
