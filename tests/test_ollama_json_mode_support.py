from __future__ import annotations

import httpx

from app.services.ai_mesh_intelligence import OllamaMeshClient


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _Client:
    payloads: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, url: str, json: dict[str, object]):
        self.payloads.append(json)
        return _Response({"response": '{"status":"OK","summary":"ok","confidence":0.5}'})


def test_ollama_format_json_option_is_passed(monkeypatch) -> None:
    _Client.payloads.clear()
    monkeypatch.setattr(httpx, "Client", _Client)
    client = OllamaMeshClient(base_urls=["http://ollama.test"], model_name="qwen3:4b")

    payload = client.complete_json(prompt="return json", timeout_seconds=1, num_predict=24, task="PING")

    assert payload["status"] == "OK"
    assert _Client.payloads[0]["format"] == "json"
    assert _Client.payloads[0]["stream"] is False
    assert _Client.payloads[0]["options"]["temperature"] == 0
    assert _Client.payloads[0]["options"]["num_predict"] == 24
