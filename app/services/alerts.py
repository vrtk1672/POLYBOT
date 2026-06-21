from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from app.config import Settings, get_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.alert_event import AlertEventContract
from app.repositories.alert_events_repository import AlertEventsRepository


@dataclass(slots=True)
class AlertEmitResult:
    alert_event_id: str
    emitted: bool
    delivery_status_class: str


class AlertEventService:
    def __init__(
        self,
        settings: Settings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._alerts = AlertEventsRepository()

    def emit_alert(
        self,
        *,
        event_class: str,
        severity_class: str,
        title: str,
        body_text: str,
        dedupe_key: str | None = None,
        source_ref: str | None = None,
        payload_json: dict[str, object] | None = None,
    ) -> AlertEmitResult:
        payload_json = payload_json or {}
        status_class = "PENDING"
        emitted = True
        if dedupe_key:
            cutoff = datetime.now(UTC) - timedelta(seconds=self._settings.alert_dedupe_window_seconds)
            with self._factory.connect() as conn:
                existing = self._alerts.get_recent_by_dedupe_key(conn, dedupe_key=dedupe_key, since=cutoff)
            if existing is not None:
                status_class = "SKIPPED"
                emitted = False

        alert_id = str(uuid4())
        delivered_at = None
        if emitted and self._settings.telegram_bot_token and self._settings.telegram_default_chat_id:
            try:
                TelegramDeliveryService(self._settings).send_message(
                    chat_id=self._settings.telegram_default_chat_id,
                    text=f"[{severity_class}] {title}\n{body_text}",
                )
                status_class = "DELIVERED"
                delivered_at = datetime.now(UTC)
            except Exception:
                status_class = "FAILED"

        with self._factory.connect() as conn, conn.transaction():
            self._alerts.insert(
                conn,
                AlertEventContract(
                    id=alert_id,
                    event_class=event_class,
                    severity_class=severity_class,
                    title=title,
                    body_text=body_text,
                    dedupe_key=dedupe_key,
                    source_ref=source_ref,
                    delivery_status_class=status_class,
                    payload_json=payload_json,
                    delivered_at=delivered_at,
                ),
            )
        return AlertEmitResult(alert_event_id=alert_id, emitted=emitted, delivery_status_class=status_class)

    def list_recent_alerts(self, limit: int = 20) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._alerts.list_recent(conn, limit)
        return [dict(row) for row in rows]


class TelegramDeliveryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def send_message(self, *, chat_id: str, text: str) -> None:
        if not self._settings.telegram_bot_token:
            raise RuntimeError("POLYBOT_TELEGRAM_BOT_TOKEN is not configured")
        httpx.post(
            f"https://api.telegram.org/bot{self._settings.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        ).raise_for_status()
