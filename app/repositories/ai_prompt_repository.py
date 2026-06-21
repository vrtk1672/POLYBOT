from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class AIPromptRepository:
    def get_active_prompt(self, conn: Connection, prompt_type: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT *
            FROM ai_prompt_versions
            WHERE prompt_type = %s AND active = true
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (prompt_type,),
        ).fetchone()

    def register_prompt_version(
        self,
        conn: Connection,
        *,
        prompt_version_id: str,
        prompt_name: str,
        prompt_type: str,
        version: str,
        template_text: str,
        model_family: str | None = None,
        schema_json: dict[str, Any] | None = None,
        active: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_prompt_versions (
                prompt_version_id, prompt_name, prompt_type, model_family, version,
                template_text, schema_json, active, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (prompt_version_id) DO UPDATE SET
                template_text = EXCLUDED.template_text,
                schema_json = EXCLUDED.schema_json,
                active = EXCLUDED.active,
                updated_at = now(),
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                prompt_version_id,
                prompt_name,
                prompt_type,
                model_family,
                version,
                template_text,
                Jsonb(schema_json or {}),
                active,
                Jsonb(metadata or {}),
            ),
        )

    def deactivate_prompt_version(self, conn: Connection, prompt_version_id: str) -> None:
        conn.execute(
            "UPDATE ai_prompt_versions SET active = false, updated_at = now() WHERE prompt_version_id = %s",
            (prompt_version_id,),
        )
