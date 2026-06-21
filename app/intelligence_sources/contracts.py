from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class IntelligenceSourceDefinition:
    source_id: str
    source_type: str
    provider_name: str
    provider_category: str
    required_env_vars: tuple[str, ...] = ()
    optional_env_vars: tuple[str, ...] = ()
    setup_url_or_notes: str = ""
    cost_model: str = "unknown"
    priority: int = 50
    enabled_by_default: bool = False
    neural_event_type: str | None = None
    awareness_domain: str | None = None
    supports_mock: bool = True
    target_tables: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_api_key(self) -> bool:
        return bool(self.required_env_vars)


@dataclass(slots=True)
class CredentialCheck:
    env_var: str
    required: bool
    present: bool
    validity_status: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "env_var": self.env_var,
            "required": self.required,
            "present": self.present,
            "validity_status": self.validity_status,
        }


@dataclass(slots=True)
class ProviderReadiness:
    source: IntelligenceSourceDefinition
    credential_checks: list[CredentialCheck]
    credential_status: str
    readiness_status: str
    health_status: str
    missing_required_env_vars: list[str]
    missing_optional_env_vars: list[str]
    next_action: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source.source_id,
            "source_type": self.source.source_type,
            "provider_name": self.source.provider_name,
            "provider_category": self.source.provider_category,
            "requires_api_key": self.source.requires_api_key,
            "required_env_vars": list(self.source.required_env_vars),
            "optional_env_vars": list(self.source.optional_env_vars),
            "credential_status": self.credential_status,
            "readiness_status": self.readiness_status,
            "health_status": self.health_status,
            "enabled_by_default": self.source.enabled_by_default,
            "cost_model": self.source.cost_model,
            "priority": self.source.priority,
            "neural_event_type": self.source.neural_event_type,
            "awareness_domain": self.source.awareness_domain,
            "target_tables": list(self.source.target_tables),
            "credential_checks": [check.to_api_dict() for check in self.credential_checks],
            "missing_required_env_vars": self.missing_required_env_vars,
            "missing_optional_env_vars": self.missing_optional_env_vars,
            "setup_url_or_notes": self.source.setup_url_or_notes,
            "next_action": self.next_action,
            "metadata": self.source.metadata,
        }


class IntelligenceProviderContract(Protocol):
    source_id: str

    def validate_credentials(self) -> ProviderReadiness:
        ...

    def health_check(self) -> dict[str, Any]:
        ...
