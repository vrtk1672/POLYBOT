from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.risk.contracts import CooldownEvent, RiskBreach


class CooldownManager:
    def from_breach(self, breach: RiskBreach, *, minutes: int = 60) -> CooldownEvent:
        return CooldownEvent(
            scope="ENGINE" if breach.engine else "GLOBAL",
            scope_key=breach.engine or breach.market_family,
            engine=breach.engine,
            market_family=breach.market_family,
            market_id=breach.market_id,
            reason=breach.breach_type,
            severity=breach.severity,
            expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
            source_breach_id=breach.breach_id,
        )

    def active_blocks(self, *, engine: str | None, market_family: str | None, cooldowns: list[dict]) -> tuple[bool, str | None]:
        now = datetime.now(UTC)
        for cooldown in cooldowns:
            if not cooldown.get("active", True):
                continue
            expires = cooldown.get("expires_at")
            if isinstance(expires, str):
                try:
                    expires = datetime.fromisoformat(expires)
                except ValueError:
                    expires = None
            if expires is not None and expires <= now:
                continue
            scope_engine = cooldown.get("engine") or cooldown.get("scope_key")
            scope_family = cooldown.get("market_family") or cooldown.get("scope_key")
            if cooldown.get("scope") == "GLOBAL" or (engine and scope_engine == engine) or (market_family and scope_family == market_family):
                return True, "active_cooldown"
        return False, None

