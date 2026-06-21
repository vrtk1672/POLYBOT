from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.intelligence_sources.contracts import CredentialCheck, IntelligenceSourceDefinition, ProviderReadiness


class IntelligenceSourceReadinessRepository:
    def table_exists(self, conn: Connection, table_name: str) -> bool:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()
        return bool(row and row["table_name"])

    def upsert_source(self, conn: Connection, source: IntelligenceSourceDefinition, *, status: str, health_status: str) -> None:
        conn.execute(
            """
            INSERT INTO intelligence_source_registry (
                source_id, source_type, provider_name, provider_category,
                requires_api_key, required_env_vars, optional_env_vars,
                status, health_status, setup_url_or_notes, cost_model,
                priority, enabled_by_default, neural_event_type, awareness_domain,
                supports_mock, target_tables_json, metadata_json, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, now()
            )
            ON CONFLICT (source_id) DO UPDATE
            SET source_type = EXCLUDED.source_type,
                provider_name = EXCLUDED.provider_name,
                provider_category = EXCLUDED.provider_category,
                requires_api_key = EXCLUDED.requires_api_key,
                required_env_vars = EXCLUDED.required_env_vars,
                optional_env_vars = EXCLUDED.optional_env_vars,
                status = EXCLUDED.status,
                health_status = EXCLUDED.health_status,
                setup_url_or_notes = EXCLUDED.setup_url_or_notes,
                cost_model = EXCLUDED.cost_model,
                priority = EXCLUDED.priority,
                enabled_by_default = EXCLUDED.enabled_by_default,
                neural_event_type = EXCLUDED.neural_event_type,
                awareness_domain = EXCLUDED.awareness_domain,
                supports_mock = EXCLUDED.supports_mock,
                target_tables_json = EXCLUDED.target_tables_json,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = now()
            """,
            (
                source.source_id,
                source.source_type,
                source.provider_name,
                source.provider_category,
                source.requires_api_key,
                Jsonb(list(source.required_env_vars)),
                Jsonb(list(source.optional_env_vars)),
                status,
                health_status,
                source.setup_url_or_notes,
                source.cost_model,
                source.priority,
                source.enabled_by_default,
                source.neural_event_type,
                source.awareness_domain,
                source.supports_mock,
                Jsonb(list(source.target_tables)),
                Jsonb(source.metadata),
            ),
        )

    def upsert_readiness(self, conn: Connection, readiness: ProviderReadiness) -> None:
        source = readiness.source
        self.upsert_source(
            conn,
            source,
            status=_registry_status(readiness),
            health_status=readiness.health_status,
        )
        conn.execute(
            "UPDATE intelligence_source_registry SET last_checked_at = now() WHERE source_id = %s",
            (source.source_id,),
        )
        existing_env_vars = list(source.required_env_vars) + list(source.optional_env_vars)
        if existing_env_vars:
            conn.execute(
                "DELETE FROM intelligence_source_credentials_status WHERE source_id = %s AND NOT (env_var = ANY(%s))",
                (source.source_id, existing_env_vars),
            )
        for check in readiness.credential_checks:
            self.upsert_credential_check(conn, source.source_id, check)
        conn.execute(
            """
            INSERT INTO intelligence_provider_health (
                source_id, health_status, credential_status, readiness_status,
                message, metadata_json, last_checked_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (source_id) DO UPDATE
            SET health_status = EXCLUDED.health_status,
                credential_status = EXCLUDED.credential_status,
                readiness_status = EXCLUDED.readiness_status,
                message = EXCLUDED.message,
                metadata_json = EXCLUDED.metadata_json,
                last_checked_at = now()
            """,
            (
                source.source_id,
                readiness.health_status,
                readiness.credential_status,
                readiness.readiness_status,
                readiness.next_action,
                Jsonb(
                    {
                        "provider_category": source.provider_category,
                        "missing_required_env_vars": readiness.missing_required_env_vars,
                        "missing_optional_env_vars": readiness.missing_optional_env_vars,
                        "secrets_exposed": False,
                    }
                ),
            ),
        )
        self.refresh_missing_requirements(conn, readiness)

    def upsert_credential_check(self, conn: Connection, source_id: str, check: CredentialCheck) -> None:
        conn.execute(
            """
            INSERT INTO intelligence_source_credentials_status (
                source_id, env_var, required, present, validity_status,
                last_checked_at, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, now(), %s)
            ON CONFLICT (source_id, env_var) DO UPDATE
            SET required = EXCLUDED.required,
                present = EXCLUDED.present,
                validity_status = EXCLUDED.validity_status,
                last_checked_at = now(),
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                source_id,
                check.env_var,
                check.required,
                check.present,
                check.validity_status,
                Jsonb({"secret_value": "redacted"}),
            ),
        )

    def refresh_missing_requirements(self, conn: Connection, readiness: ProviderReadiness) -> None:
        source_id = readiness.source.source_id
        conn.execute(
            "UPDATE intelligence_missing_requirements SET resolved_at = now() WHERE source_id = %s AND resolved_at IS NULL",
            (source_id,),
        )
        for env_var in readiness.missing_required_env_vars:
            conn.execute(
                """
                INSERT INTO intelligence_missing_requirements (
                    source_id, env_var, severity, next_action, created_at
                )
                VALUES (%s, %s, 'REQUIRED', %s, now())
                ON CONFLICT (source_id, env_var) WHERE resolved_at IS NULL DO NOTHING
                """,
                (source_id, env_var, f"Set {env_var} in .env after obtaining provider credentials."),
            )
        for env_var in readiness.missing_optional_env_vars:
            conn.execute(
                """
                INSERT INTO intelligence_missing_requirements (
                    source_id, env_var, severity, next_action, created_at
                )
                VALUES (%s, %s, 'OPTIONAL', %s, now())
                ON CONFLICT (source_id, env_var) WHERE resolved_at IS NULL DO NOTHING
                """,
                (source_id, env_var, f"Optional: set {env_var} if this provider is selected."),
            )

    def list_sources(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_source_registry
            ORDER BY source_type, priority, provider_name
            """
        ).fetchall()

    def list_credentials(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_source_credentials_status
            ORDER BY source_id, required DESC, env_var
            """
        ).fetchall()

    def list_health(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_provider_health
            ORDER BY last_checked_at DESC, source_id
            """
        ).fetchall()

    def list_missing(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_missing_requirements
            WHERE resolved_at IS NULL
            ORDER BY severity, source_id, env_var
            """
        ).fetchall()


def _registry_status(readiness: ProviderReadiness) -> str:
    if readiness.health_status == "BLOCKED_MISSING_CREDENTIALS":
        return "MISSING_CREDENTIALS"
    if not readiness.source.enabled_by_default and not readiness.source.required_env_vars:
        return "DISABLED_BY_DEFAULT"
    if readiness.health_status == "READY_NO_KEY":
        return "READY_NO_KEY"
    if readiness.health_status == "READY":
        return "READY"
    return "CONFIGURED"
