from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.security.env_audit import build_audit
from app.security.redaction import contains_secret_like_value, redact_secrets


ROTATION_REQUIRED_CATEGORIES = (
    "ANTHROPIC_API_KEY",
    "POLYMARKET_CLOB_API_KEY",
    "POLYMARKET_CLOB_SECRET",
    "POLYMARKET_CLOB_PASSPHRASE",
    "NEWS_API_KEY_IF_RAW_CONFIG_EXPOSED",
    "OPENAI_API_KEY_IF_RAW_CONFIG_EXPOSED",
)

MAX_SCAN_BYTES = 256_000

UNSAFE_PATTERNS = (
    "docker compose config",
    "docker-compose config",
    "printenv",
    "Get-Content .env",
    "cat .env",
    "env dump",
    "config dump",
)


class SecuritySecretsService:
    def __init__(self, *, root: Path | None = None) -> None:
        self._root = root or Path(__file__).resolve().parents[2]

    def get_dashboard_summary(self, *, limit: int = 100) -> dict[str, Any]:
        audit = build_audit(include_masked=False, root=self._root)
        unsafe = self._unsafe_pattern_files(limit=limit)
        docs_scan = self.scan_docs_for_secret_like_values(limit=limit)
        return {
            "mock_data": False,
            "secret_exposure_status": "ROTATION_REQUIRED",
            "unsafe_patterns_found": unsafe,
            "last_safe_env_audit_at": audit["audited_at"],
            "duplicate_env_keys": audit["duplicate_env_keys"],
            "dangerous_duplicate_overrides": audit["dangerous_duplicate_overrides"],
            "rotation_recommended": True,
            "rotation_required_categories": list(ROTATION_REQUIRED_CATEGORIES),
            "raw_secret_values_exposed": "unknown_prior_exposure",
            "safe_config_guard_status": audit["safe_config_guard_status"],
            "docs_secret_scan": docs_scan,
            "operator_action_required": "Rotate exposed categories or explicitly accept governance risk as YELLOW/ACCEPTED_RISK.",
            "raw_values_returned": False,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def scan_docs_for_secret_like_values(self, *, limit: int = 100) -> dict[str, Any]:
        findings: list[dict[str, str]] = []
        for folder in (self._root / "docs",):
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.md")):
                if path.stat().st_size > MAX_SCAN_BYTES:
                    findings.append({"path": str(path.relative_to(self._root)), "risk": "SKIPPED_LARGE_FILE_USE_OFFLINE_SCAN"})
                    if len(findings) >= limit:
                        break
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")[:MAX_SCAN_BYTES]
                redacted = redact_secrets(text)
                if contains_secret_like_value(redacted):
                    findings.append({"path": str(path.relative_to(self._root)), "risk": "SECRET_LIKE_TEXT_AFTER_REDACTION"})
                    if len(findings) >= limit:
                        break
        return {
            "status": "OK" if not findings else "REVIEW_REQUIRED",
            "findings": findings,
            "raw_values_returned": False,
        }

    def _unsafe_pattern_files(self, *, limit: int) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        searchable = [self._root / "app", self._root / "scripts", self._root / "docs", self._root / "tests"]
        for folder in searchable:
            if not folder.exists():
                continue
            for path in sorted(folder.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in {".py", ".ps1", ".md", ".txt", ".yml", ".yaml"}:
                    continue
                if path.name == "security_secrets.py":
                    continue
                if path.stat().st_size > MAX_SCAN_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")[:MAX_SCAN_BYTES]
                lowered = text.lower()
                matches = [pattern for pattern in UNSAFE_PATTERNS if pattern.lower() in lowered]
                if matches:
                    findings.append({
                        "path": str(path.relative_to(self._root)),
                        "risk": "UNSAFE_SECRET_PRINTING_PATTERN",
                        "patterns": ",".join(matches),
                    })
                    if len(findings) >= limit:
                        return findings
        return findings
