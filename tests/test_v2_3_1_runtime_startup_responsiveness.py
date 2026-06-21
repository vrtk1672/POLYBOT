from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai_brain.cloud_escalation_worker import CloudEscalationWorker
from app.ai_brain.local_ai_worker import LocalAIWorker
from app.ai_brain.service import HybridAIBrainService
from app.api.ai_routes import create_ai_router
from app.main import create_app
from app.scheduler import RefreshScheduler


def test_healthz_is_lightweight_and_does_not_run_market_refresh(monkeypatch) -> None:
    started = {"scheduler": False, "refresh_called": False}

    async def fake_start(self):
        started["scheduler"] = True

    async def fake_refresh():
        started["refresh_called"] = True

    monkeypatch.setattr(RefreshScheduler, "start", fake_start)
    app = create_app()
    app.state.market_service.refresh = fake_refresh

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "polybot", "ready": True}
    assert started["scheduler"] is True
    assert started["refresh_called"] is False


def test_app_creation_and_ai_routes_do_not_contact_ollama_or_cloud(monkeypatch) -> None:
    def fail_local(*_args, **_kwargs):
        raise AssertionError("startup should not call local AI generation")

    def fail_cloud(*_args, **_kwargs):
        raise AssertionError("startup should not call cloud escalation")

    monkeypatch.setattr(LocalAIWorker, "generate_json", fail_local)
    monkeypatch.setattr(CloudEscalationWorker, "escalate", fail_cloud)
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/ai/health" in paths
    assert "/healthz" in paths


def test_ai_health_returns_structured_unavailable_without_ollama() -> None:
    from fastapi import FastAPI

    service = HybridAIBrainService(local_worker=LocalAIWorker())
    app = FastAPI()
    app.include_router(create_ai_router(ai_service=service))

    response = TestClient(app).get("/ai/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["local_ai_available"] is False
    assert payload["cloud_enabled"] is False
    assert "status" in payload


def test_startup_does_not_call_ai_workers(monkeypatch) -> None:
    called = {"local": False, "cloud": False}

    def fake_local(*_args, **_kwargs):
        called["local"] = True

    def fake_cloud(*_args, **_kwargs):
        called["cloud"] = True

    async def fake_start(self):
        return None

    monkeypatch.setattr(LocalAIWorker, "generate_json", fake_local)
    monkeypatch.setattr(CloudEscalationWorker, "escalate", fake_cloud)
    monkeypatch.setattr(RefreshScheduler, "start", fake_start)

    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200

    assert called == {"local": False, "cloud": False}
