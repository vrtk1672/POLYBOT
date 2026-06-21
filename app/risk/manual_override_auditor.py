from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.risk.risk_errors import ManualOverrideRejected


class ManualOverrideAuditor:
    def validate(self, payload: dict[str, Any], *, governor_status: str | None = None) -> dict[str, Any]:
        actor = str(payload.get("actor") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        scope = str(payload.get("scope") or "").strip().upper()
        override_type = str(payload.get("override_type") or "").strip().upper()
        if not actor or not reason or not scope or not override_type:
            raise ManualOverrideRejected("manual override requires actor, reason, scope, and override_type")
        if governor_status == "KILL" or override_type == "BYPASS_KILL":
            raise ManualOverrideRejected("manual override cannot bypass KILL")
        return {
            "override_id": f"risk_override_{uuid4().hex}",
            "actor": actor,
            "reason": reason,
            "scope": scope,
            "scope_key": payload.get("scope_key"),
            "override_type": override_type,
            "expires_at": payload.get("expires_at"),
            "created_at": datetime.utcnow().isoformat(),
        }

