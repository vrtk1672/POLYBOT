from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.intelligence_sources.catalog import PROVIDER_CATALOG
from app.intelligence_sources.contracts import CredentialCheck, IntelligenceSourceDefinition, ProviderReadiness
from app.intelligence_sources.repository import IntelligenceSourceReadinessRepository


class IntelligenceSourceReadinessService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: IntelligenceSourceReadinessRepository | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repo = repository or IntelligenceSourceReadinessRepository()
        self._env = env

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        readiness = self.validate_credentials(persist=True)
        persisted = self._persisted_snapshot()
        sources = persisted.get("sources") or [item.to_api_dict() for item in readiness]
        health = persisted.get("health") or []
        missing = persisted.get("missing") or self._missing_from_readiness(readiness)
        counts_by_type = Counter(str(item.get("source_type")) for item in sources)
        readiness_by_type: dict[str, Counter] = defaultdict(Counter)
        for item in sources:
            readiness_by_type[str(item.get("source_type"))][str(item.get("status") or item.get("readiness_status"))] += 1
        missing_env_vars = sorted({str(row.get("env_var")) for row in missing if row.get("env_var")})
        free_now = [
            _source_public(row)
            for row in sources
            if not bool(row.get("requires_api_key")) and str(row.get("cost_model")) in {"free", "internal", "local_compute", "test_only"}
        ]
        paid_recommended = [
            _source_public(row)
            for row in sources
            if "paid" in str(row.get("cost_model") or "").lower()
        ]
        required_accounts = [
            _requirement_public(row)
            for row in sources
            if bool(row.get("requires_api_key"))
        ]
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": _now_iso(),
            "total_sources": len(sources),
            "news_readiness": _type_readiness("NEWS", readiness_by_type, counts_by_type),
            "whale_readiness": _type_readiness("WHALE", readiness_by_type, counts_by_type),
            "social_readiness": _type_readiness("SOCIAL", readiness_by_type, counts_by_type),
            "ai_readiness": _type_readiness("AI_CONTEXT", readiness_by_type, counts_by_type),
            "market_memory_readiness": _type_readiness("MARKET_MEMORY", readiness_by_type, counts_by_type),
            "missing_env_vars": missing_env_vars,
            "missing_required_count": sum(1 for row in missing if str(row.get("severity")) == "REQUIRED"),
            "missing_optional_count": sum(1 for row in missing if str(row.get("severity")) == "OPTIONAL"),
            "required_accounts": required_accounts,
            "optional_providers": [_source_public(row) for row in sources if not bool(row.get("enabled_by_default"))],
            "free_providers_available_now": free_now,
            "paid_providers_recommended": paid_recommended,
            "health_status": _health_summary(health, sources),
            "next_operator_actions": self._next_actions(missing, sources),
            "sources": [_source_public(row) for row in sources[:limit]],
            "secrets_exposed": False,
        }

    def requirements_report(self) -> dict[str, Any]:
        readiness = self.validate_credentials(persist=True)
        missing = self._missing_from_readiness(readiness)
        required = [item.to_api_dict() for item in readiness if item.source.required_env_vars]
        optional = [item.to_api_dict() for item in readiness if item.source.optional_env_vars and not item.source.required_env_vars]
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": _now_iso(),
            "required_providers": [_redact_source_payload(item) for item in required],
            "optional_keyed_or_configurable_providers": [_redact_source_payload(item) for item in optional],
            "missing_requirements": missing,
            "minimum_viable_source_set": self.minimum_viable_source_set(),
            "full_professional_source_set": self.full_professional_source_set(),
            "secrets_exposed": False,
        }

    def health_report(self) -> dict[str, Any]:
        readiness = self.validate_credentials(persist=True)
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": _now_iso(),
            "health": [_redact_source_payload(item.to_api_dict()) for item in readiness],
            "secrets_exposed": False,
        }

    def validate_endpoint(self) -> dict[str, Any]:
        readiness = self.validate_credentials(persist=True)
        return {
            "status": "OK",
            "mock_data": False,
            "updated_at": _now_iso(),
            "validated_sources": len(readiness),
            "available_sources": sum(1 for item in readiness if item.readiness_status in {"READY", "READY_NO_KEY", "READY_FOR_CONNECTOR_TEST"}),
            "blocked_sources": sum(1 for item in readiness if item.health_status == "BLOCKED_MISSING_CREDENTIALS"),
            "providers": [_redact_source_payload(item.to_api_dict()) for item in readiness],
            "missing_env_vars": sorted({env for item in readiness for env in item.missing_required_env_vars}),
            "optional_missing_env_vars": sorted({env for item in readiness for env in item.missing_optional_env_vars}),
            "secrets_exposed": False,
        }

    def validate_credentials(self, *, persist: bool = True) -> list[ProviderReadiness]:
        readiness = self.evaluate_catalog()
        if persist:
            self._persist_readiness(readiness)
        return readiness

    def ensure_registry(self) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not self._repo.table_exists(conn, "intelligence_source_registry"):
                return
            for source in PROVIDER_CATALOG:
                self._repo.upsert_source(
                    conn,
                    source,
                    status="READY_NO_KEY" if not source.required_env_vars else "CONFIGURED",
                    health_status="READY_NO_KEY" if not source.required_env_vars else "UNTESTED",
                )

    def evaluate_catalog(self) -> list[ProviderReadiness]:
        return [self._evaluate_source(source) for source in PROVIDER_CATALOG]

    def minimum_viable_source_set(self) -> list[dict[str, Any]]:
        source_ids = {
            "news_rss_public",
            "gdelt_public",
            "polymarket_gamma_public",
            "polymarket_clob_public_trades",
            "whale_profile_builder_internal",
            "manual_social_ingestion",
            "ollama_local",
            "ai_budget_cache_internal",
            "market_memory_outcomes",
        }
        return [_source_definition_public(source) for source in PROVIDER_CATALOG if source.source_id in source_ids]

    def full_professional_source_set(self) -> list[dict[str, Any]]:
        source_ids = {
            "news_rss_public",
            "gdelt_public",
            "newsapi",
            "cryptopanic",
            "polymarket_gamma_public",
            "polymarket_clob_public_trades",
            "polymarket_clob_authenticated_readonly",
            "whale_profile_builder_internal",
            "x_twitter_api",
            "reddit_api",
            "telegram_public_channels",
            "ollama_local",
            "openai_api",
            "anthropic_api",
            "ai_budget_cache_internal",
            "market_memory_outcomes",
        }
        return [_source_definition_public(source) for source in PROVIDER_CATALOG if source.source_id in source_ids]

    def _evaluate_source(self, source: IntelligenceSourceDefinition) -> ProviderReadiness:
        env = self._env if self._env is not None else os.environ
        checks: list[CredentialCheck] = []
        missing_required: list[str] = []
        missing_optional: list[str] = []
        for env_var in source.required_env_vars:
            present = _env_present(env, env_var)
            if not present:
                missing_required.append(env_var)
            checks.append(
                CredentialCheck(
                    env_var=env_var,
                    required=True,
                    present=present,
                    validity_status="PRESENT" if present else "MISSING",
                )
            )
        for env_var in source.optional_env_vars:
            present = _env_present(env, env_var)
            if not present:
                missing_optional.append(env_var)
            checks.append(
                CredentialCheck(
                    env_var=env_var,
                    required=False,
                    present=present,
                    validity_status="PRESENT" if present else "OPTIONAL_MISSING",
                )
            )

        if missing_required:
            return ProviderReadiness(
                source=source,
                credential_checks=checks,
                credential_status="MISSING_CREDENTIALS",
                readiness_status="BLOCKED",
                health_status="BLOCKED_MISSING_CREDENTIALS",
                missing_required_env_vars=missing_required,
                missing_optional_env_vars=missing_optional,
                next_action=f"Set required env vars: {', '.join(missing_required)}.",
            )
        if source.required_env_vars:
            return ProviderReadiness(
                source=source,
                credential_checks=checks,
                credential_status="CREDENTIALS_PRESENT",
                readiness_status="READY_FOR_CONNECTOR_TEST",
                health_status="READY",
                missing_required_env_vars=[],
                missing_optional_env_vars=missing_optional,
                next_action="Credentials are present; run provider-specific connector test before enabling ingestion.",
            )
        if not source.enabled_by_default and source.source_id != "mock_intelligence_provider":
            return ProviderReadiness(
                source=source,
                credential_checks=checks,
                credential_status="NOT_REQUIRED",
                readiness_status="AVAILABLE_DISABLED_BY_DEFAULT",
                health_status="DISABLED",
                missing_required_env_vars=[],
                missing_optional_env_vars=missing_optional,
                next_action="Provider contract exists; enable only after operator selects this source.",
            )
        return ProviderReadiness(
            source=source,
            credential_checks=checks,
            credential_status="NOT_REQUIRED",
            readiness_status="READY_NO_KEY",
            health_status="READY_NO_KEY",
            missing_required_env_vars=[],
            missing_optional_env_vars=missing_optional,
            next_action="No credentials required; configure source targets before production ingestion.",
        )

    def _persist_readiness(self, readiness: list[ProviderReadiness]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not self._repo.table_exists(conn, "intelligence_source_registry"):
                return
            for item in readiness:
                self._repo.upsert_readiness(conn, item)

    def _persisted_snapshot(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"sources": [], "credentials": [], "health": [], "missing": []}
        try:
            with self._factory.connect() as conn:
                if not self._repo.table_exists(conn, "intelligence_source_registry"):
                    return {"sources": [], "credentials": [], "health": [], "missing": []}
                return {
                    "sources": [_serialize_row(row) for row in self._repo.list_sources(conn)],
                    "credentials": [_serialize_row(row) for row in self._repo.list_credentials(conn)],
                    "health": [_serialize_row(row) for row in self._repo.list_health(conn)],
                    "missing": [_serialize_row(row) for row in self._repo.list_missing(conn)],
                }
        except Exception:
            return {"sources": [], "credentials": [], "health": [], "missing": []}

    def _missing_from_readiness(self, readiness: list[ProviderReadiness]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in readiness:
            for env_var in item.missing_required_env_vars:
                rows.append(
                    {
                        "source_id": item.source.source_id,
                        "provider_name": item.source.provider_name,
                        "env_var": env_var,
                        "severity": "REQUIRED",
                        "next_action": f"Set {env_var} in .env after obtaining provider credentials.",
                    }
                )
            for env_var in item.missing_optional_env_vars:
                rows.append(
                    {
                        "source_id": item.source.source_id,
                        "provider_name": item.source.provider_name,
                        "env_var": env_var,
                        "severity": "OPTIONAL",
                        "next_action": f"Optional: set {env_var} if this provider is selected.",
                    }
                )
        return rows

    def _next_actions(self, missing: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[str]:
        required = sorted({str(row.get("env_var")) for row in missing if str(row.get("severity")) == "REQUIRED"})
        actions = []
        if required:
            actions.append(f"Obtain and configure required external credentials: {', '.join(required)}.")
        if any(str(row.get("source_id")) == "news_rss_public" for row in sources):
            actions.append("Choose operator-approved RSS feeds and set NEWS_RSS_FEEDS or register them in news_sources.")
        actions.append("Run POST /intelligence-sources/validate after updating .env.")
        actions.append("Keep production ingestion disabled until provider health checks pass.")
        return actions


def _env_present(env: dict[str, str], env_var: str) -> bool:
    value = env.get(env_var)
    return bool(value is not None and str(value).strip())


def _type_readiness(source_type: str, readiness_by_type: dict[str, Counter], counts_by_type: Counter) -> dict[str, Any]:
    statuses = dict(readiness_by_type.get(source_type, Counter()))
    return {
        "total": int(counts_by_type.get(source_type, 0)),
        "ready": int(statuses.get("READY", 0) + statuses.get("READY_NO_KEY", 0)),
        "missing_credentials": int(statuses.get("MISSING_CREDENTIALS", 0)),
        "disabled_by_default": int(statuses.get("DISABLED_BY_DEFAULT", 0)),
        "statuses": statuses,
    }


def _health_summary(health: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not health:
        status_counts = Counter(str(row.get("health_status") or "UNTESTED") for row in sources)
    else:
        status_counts = Counter(str(row.get("health_status") or "UNTESTED") for row in health)
    return {
        "status_counts": dict(status_counts),
        "blocked_missing_credentials": int(status_counts.get("BLOCKED_MISSING_CREDENTIALS", 0)),
        "ready_no_key": int(status_counts.get("READY_NO_KEY", 0)),
        "ready": int(status_counts.get("READY", 0)),
    }


def _requirement_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": row.get("source_id"),
        "provider_name": row.get("provider_name"),
        "source_type": row.get("source_type"),
        "required_env_vars": row.get("required_env_vars") or [],
        "optional_env_vars": row.get("optional_env_vars") or [],
        "cost_model": row.get("cost_model"),
        "setup_url_or_notes": row.get("setup_url_or_notes"),
    }


def _source_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": row.get("source_id"),
        "source_type": row.get("source_type"),
        "provider_name": row.get("provider_name"),
        "provider_category": row.get("provider_category"),
        "requires_api_key": row.get("requires_api_key"),
        "status": row.get("status"),
        "health_status": row.get("health_status"),
        "cost_model": row.get("cost_model"),
        "priority": row.get("priority"),
        "enabled_by_default": row.get("enabled_by_default"),
        "neural_event_type": row.get("neural_event_type"),
        "awareness_domain": row.get("awareness_domain"),
        "setup_url_or_notes": row.get("setup_url_or_notes"),
    }


def _source_definition_public(source: IntelligenceSourceDefinition) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "provider_name": source.provider_name,
        "required_env_vars": list(source.required_env_vars),
        "optional_env_vars": list(source.optional_env_vars),
        "cost_model": source.cost_model,
        "neural_event_type": source.neural_event_type,
        "awareness_domain": source.awareness_domain,
        "setup_url_or_notes": source.setup_url_or_notes,
    }


def _redact_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    for key in ("credential_checks",):
        if isinstance(redacted.get(key), list):
            redacted[key] = [
                {
                    sub_key: sub_value
                    for sub_key, sub_value in dict(item).items()
                    if sub_key not in {"value", "secret", "token"}
                }
                for item in redacted[key]
            ]
    redacted["secrets_exposed"] = False
    return redacted


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        elif isinstance(value, Decimal):
            output[key] = float(value)
        else:
            output[key] = value
    return output


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
