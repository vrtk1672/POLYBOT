from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.security.redaction import contains_secret_like_value, mask_secret, redact_secrets
from scripts.safe_env_audit import build_audit


def test_safe_env_audit_masks_secrets_and_detects_duplicates(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test-secret-value-abcdefghijklmnopqrstuvwxyz",
                "OLLAMA_BASE_URL=http://localhost:11434",
                "OLLAMA_BASE_URL=http://host.docker.internal:11434",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\nOLLAMA_BASE_URL=\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("environment:\n  OPENAI_API_KEY: ${OPENAI_API_KEY:-}\n", encoding="utf-8")

    payload = build_audit(root=tmp_path)

    assert payload["raw_values_printed"] is False
    assert payload["key_status"]["OPENAI_API_KEY"]["status"] == "PRESENT"
    assert payload["key_status"]["OPENAI_API_KEY"]["masked"].startswith("sk-t...")
    assert "OLLAMA_BASE_URL" in payload["duplicate_env_keys"]
    assert "OLLAMA_BASE_URL" in payload["dangerous_duplicate_overrides"]
    assert "sk-test-secret-value" not in json.dumps(payload)


def test_redaction_masks_secret_like_values_and_keeps_risk_ids() -> None:
    text = "OPENAI_API_KEY=sk-test-secret-value-abcdefghijklmnopqrstuvwxyz risk-risk_decision_123"

    redacted = redact_secrets(text)

    assert "[REDACTED_SECRET]" in redacted
    assert contains_secret_like_value(text) is True
    assert contains_secret_like_value("risk-risk_decision_123") is False
    assert mask_secret("abcdefghi") == "abcd...fghi"


def test_dashboard_security_endpoint_returns_no_secrets(postgres_test_schema) -> None:
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/security/secrets?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["rotation_recommended"] is True
    assert payload["raw_values_returned"] is False
    assert "sk-test-secret-value" not in json.dumps(payload)
    assert "[REDACTED_SECRET]" not in json.dumps(payload.get("unsafe_patterns_found", []))
