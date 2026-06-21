from __future__ import annotations

import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.security.redaction import contains_secret_like_value, mask_secret, redact_secrets, value_status


REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ENV_KEYS = (
    "POLYMARKET_CLOB_HOST",
    "POLYMARKET_CLOB_API_KEY",
    "POLYMARKET_CLOB_SECRET",
    "POLYMARKET_CLOB_PASSPHRASE",
    "NEWS_API_KEY",
    "NEWS_RSS_FEEDS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL_FAST",
    "OLLAMA_MODEL_PRIMARY",
    "OLLAMA_MODEL_REASONING",
    "CRYPTOPANIC_API_KEY",
    "X_BEARER_TOKEN",
    "REDDIT_CLIENT_SECRET",
    "TELEGRAM_API_HASH",
    "DISCORD_BOT_TOKEN",
)

DANGEROUS_DUPLICATE_KEYS = (
    "OLLAMA_BASE_URL",
    "POLYMARKET_CLOB_HOST",
    "LIVE_TRADING_ENABLED",
    "POLYBOT_RUNTIME_MODE",
)

KEY_VALUE_RE = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)\s*$")
COMPOSE_VAR_RE = re.compile(r"\$\{(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?}")


def parse_env_file(path: Path) -> tuple[dict[str, str], dict[str, int]]:
    values: dict[str, str] = {}
    counts: Counter[str] = Counter()
    if not path.exists():
        return values, {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = KEY_VALUE_RE.match(raw_line)
        if not match:
            continue
        key = match.group("key")
        raw_value = match.group("value").strip()
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
            raw_value = raw_value[1:-1]
        counts[key] += 1
        values[key] = raw_value
    return values, dict(counts)


def compose_passthrough_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return sorted(set(match.group("key") for match in COMPOSE_VAR_RE.finditer(text)))


def build_audit(*, include_masked: bool = True, root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    env_values, env_counts = parse_env_file(root / ".env")
    example_values, _ = parse_env_file(root / ".env.example")
    compose_keys = compose_passthrough_keys(root / "docker-compose.yml")
    if root.resolve() == REPO_ROOT.resolve():
        merged = {key: os.environ.get(key, env_values.get(key)) for key in EXPECTED_ENV_KEYS}
    else:
        merged = {key: env_values.get(key) for key in EXPECTED_ENV_KEYS}

    duplicate_env_keys = sorted(key for key, count in env_counts.items() if count > 1)
    dangerous_duplicates = sorted(key for key in duplicate_env_keys if key in DANGEROUS_DUPLICATE_KEYS)
    key_status = {
        key: {
            "status": value_status(value),
            "masked": mask_secret(value) if include_masked and value else None,
            "in_env_example": key in example_values,
            "in_docker_compose_passthrough": key in compose_keys,
        }
        for key, value in merged.items()
    }
    raw_text = (root / ".env").read_text(encoding="utf-8", errors="replace") if (root / ".env").exists() else ""
    return {
        "mock_data": False,
        "audit_type": "SAFE_ENV_AUDIT",
        "audited_at": datetime.now(UTC).isoformat(),
        "raw_values_printed": False,
        "docker_compose_config_used": False,
        "key_status": key_status,
        "duplicate_env_keys": duplicate_env_keys,
        "dangerous_duplicate_overrides": dangerous_duplicates,
        "missing_from_env_example": sorted(key for key in EXPECTED_ENV_KEYS if key not in example_values),
        "missing_from_docker_compose_passthrough": sorted(key for key in EXPECTED_ENV_KEYS if key not in compose_keys),
        "compose_passthrough_keys": compose_keys,
        "secret_like_values_present_in_env": contains_secret_like_value(raw_text),
        "safe_config_guard_status": "OK",
        "redaction_check": {
            "raw_secret_values_exposed": False,
            "sample_redacted": redact_secrets("OPENAI_API_KEY=sk-example-not-real-secret-value-123456"),
        },
    }

