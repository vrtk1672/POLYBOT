from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.whale_event import WhaleEventContract
from app.domain.contracts.whale_registry_entry import WhaleRegistryEntryContract
from app.domain.contracts.whale_scan_run import WhaleScanRunCloseContract, WhaleScanRunOpenContract
from app.repositories.whale_events_repository import WhaleEventsRepository
from app.repositories.whale_registry_repository import WhaleRegistryRepository
from app.repositories.whale_scan_runs_repository import WhaleScanRunsRepository
from app.services.recorders.whale_event_recorder import WhaleEventRecorder
from app.services.recorders.whale_registry_recorder import WhaleRegistryRecorder
from app.services.recorders.whale_scan_run_recorder import WhaleScanRunRecorder

logger = logging.getLogger(__name__)

SCANNER_VERSION = "phase5a-whale-scanner-v1"
EVENT_DIRECTION_CLASSES = {"ENTRY", "EXIT", "REVERSAL_CANDIDATE", "UNKNOWN"}
REGISTRY_STATUSES = {"ACTIVE", "WATCHLIST", "DORMANT", "IGNORE"}
WHALE_SIZE_THRESHOLD = 1000.0
WHALE_NOTIONAL_THRESHOLD = 10000.0
RECENT_WINDOW = timedelta(hours=24)


@dataclass(slots=True)
class ManualWhaleEventItem:
    wallet_address: str
    market_id: str
    event_timestamp: datetime
    side_or_outcome: str | None
    size: float
    notional: float | None
    price: float | None
    transaction_ref: str | None
    source_type: str
    position_effect: str | None
    previous_side_or_outcome: str | None
    source_payload_json: dict[str, object]


@dataclass(slots=True)
class WhaleScanRunResult:
    whale_scan_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class WhaleScannerService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        scanner_version: str = SCANNER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._scanner_version = scanner_version
        self._run_recorder = WhaleScanRunRecorder()
        self._event_recorder = WhaleEventRecorder()
        self._registry_recorder = WhaleRegistryRecorder()
        self._runs = WhaleScanRunsRepository()
        self._events = WhaleEventsRepository()
        self._registry = WhaleRegistryRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def scan_manual_items(
        self,
        items: list[ManualWhaleEventItem],
        *,
        source_ref: str | None = None,
    ) -> WhaleScanRunResult | None:
        return self.scan_items(items, source_type="MANUAL_IMPORT", source_ref=source_ref)

    def scan_items(
        self,
        items: list[ManualWhaleEventItem],
        *,
        source_type: str,
        source_ref: str | None = None,
    ) -> WhaleScanRunResult | None:
        if not self.enabled:
            return None
        if not items:
            raise ValueError("at least one whale event item is required")

        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    WhaleScanRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_as_optional_str(source_ref),
                        status="OPEN",
                        scanner_version=self._scanner_version,
                        started_at=started_at,
                        input_count=len(items),
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "scanner_version": self._scanner_version,
                            "whale_size_threshold": WHALE_SIZE_THRESHOLD,
                            "whale_notional_threshold": WHALE_NOTIONAL_THRESHOLD,
                        },
                    ),
                )
                opened_run = True

                for item in items:
                    try:
                        normalized_item = _normalize_item(item)
                        classification = _classify_whale_event(normalized_item)
                        event_contract = self._build_event_contract(
                            run_id=run_id,
                            item=normalized_item,
                            source_type=source_type,
                            classification=classification,
                        )
                        self._event_recorder.record(conn, event_contract)
                        self._registry_recorder.upsert(
                            conn,
                            self._build_registry_contract(event_contract=event_contract),
                        )
                        success_count += 1
                    except Exception as exc:
                        logger.exception("whale_scanner_item_failed wallet=%s", item.wallet_address)
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    WhaleScanRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "scanner_version": self._scanner_version,
                        },
                    ),
                )

            return WhaleScanRunResult(
                whale_scan_run_id=run_id,
                status=status,
                input_count=len(items),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("whale_scan_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        WhaleScanRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_as_optional_str(source_ref),
                            status="OPEN",
                            scanner_version=self._scanner_version,
                            started_at=started_at,
                            input_count=len(items),
                            metadata_json={"source_ref": _as_optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    WhaleScanRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=max(1, len(items)),
                        metadata_json={"error": str(exc), "scanner_version": self._scanner_version},
                    ),
                )
            return WhaleScanRunResult(
                whale_scan_run_id=run_id,
                status="FAILED",
                input_count=len(items),
                success_count=success_count,
                failure_count=max(1, len(items)),
            )

    def _build_event_contract(
        self,
        *,
        run_id: str,
        item: ManualWhaleEventItem,
        source_type: str,
        classification: dict[str, str],
    ) -> WhaleEventContract:
        return WhaleEventContract(
            id=str(uuid4()),
            whale_scan_run_id=run_id,
            wallet_address=item.wallet_address,
            market_id=item.market_id,
            event_timestamp=item.event_timestamp,
            event_direction_class=classification["event_direction_class"],
            side_or_outcome=item.side_or_outcome,
            size=round(float(item.size), 6),
            notional=None if item.notional is None else round(float(item.notional), 6),
            price=None if item.price is None else round(float(item.price), 6),
            transaction_ref=item.transaction_ref,
            source_type=source_type,
            source_payload_json=_json_safe(item.source_payload_json),
            detection_reason_code=classification["reason_code"],
            detection_reason_text=classification["reason_text"],
        )

    def _build_registry_contract(self, *, event_contract: WhaleEventContract) -> WhaleRegistryEntryContract:
        return WhaleRegistryEntryContract(
            id=str(uuid4()),
            wallet_address=event_contract.wallet_address,
            first_seen_at=event_contract.event_timestamp,
            last_seen_at=event_contract.event_timestamp,
            total_events=1,
            last_market_id=event_contract.market_id,
            last_event_direction_class=event_contract.event_direction_class,
            registry_status=_derive_registry_status(
                event_direction_class=event_contract.event_direction_class,
                last_seen_at=event_contract.event_timestamp,
            ),
            metadata_json={
                "last_transaction_ref": event_contract.transaction_ref,
                "last_detection_reason_code": event_contract.detection_reason_code,
                "last_source_type": event_contract.source_type,
            },
        )


def _normalize_item(item: ManualWhaleEventItem) -> ManualWhaleEventItem:
    wallet_address = str(item.wallet_address or "").strip().lower()
    if not wallet_address:
        raise ValueError("wallet_address is required")
    market_id = str(item.market_id or "").strip()
    if not market_id:
        raise ValueError("market_id is required")
    size = float(item.size)
    notional = None if item.notional is None else float(item.notional)
    price = None if item.price is None else float(item.price)
    if size <= 0:
        raise ValueError("size must be positive")
    whale_like = size >= WHALE_SIZE_THRESHOLD or (notional is not None and notional >= WHALE_NOTIONAL_THRESHOLD)
    if not whale_like:
        raise ValueError("event does not meet whale thresholds")
    return ManualWhaleEventItem(
        wallet_address=wallet_address,
        market_id=market_id,
        event_timestamp=_normalize_timestamp(item.event_timestamp),
        side_or_outcome=_as_optional_str(item.side_or_outcome),
        size=size,
        notional=notional,
        price=price,
        transaction_ref=_as_optional_str(item.transaction_ref),
        source_type=_as_optional_str(item.source_type) or "MANUAL_IMPORT",
        position_effect=_as_optional_str(item.position_effect),
        previous_side_or_outcome=_as_optional_str(item.previous_side_or_outcome),
        source_payload_json=_json_safe(item.source_payload_json),
    )


def _classify_whale_event(item: ManualWhaleEventItem) -> dict[str, str]:
    position_effect = (item.position_effect or "").upper()
    current_side = _normalize_side(item.side_or_outcome)
    previous_side = _normalize_side(item.previous_side_or_outcome)

    if position_effect in {"OPEN", "INCREASE", "BUY", "ADD"}:
        return {
            "event_direction_class": "ENTRY",
            "reason_code": "position_effect_entry",
            "reason_text": "Position effect indicates new or growing market exposure above whale thresholds.",
        }
    if position_effect in {"CLOSE", "DECREASE", "SELL", "REDUCE"}:
        return {
            "event_direction_class": "EXIT",
            "reason_code": "position_effect_exit",
            "reason_text": "Position effect indicates reduced or closing market exposure above whale thresholds.",
        }
    if position_effect == "REVERSE" or (previous_side and current_side and previous_side != current_side):
        return {
            "event_direction_class": "REVERSAL_CANDIDATE",
            "reason_code": "side_switch_detected",
            "reason_text": "Wallet switched sides or flagged a reversal while remaining above whale thresholds.",
        }
    return {
        "event_direction_class": "UNKNOWN",
        "reason_code": "insufficient_direction_signal",
        "reason_text": "Event clears whale thresholds but lacks strong directional evidence.",
    }


def _derive_registry_status(*, event_direction_class: str, last_seen_at: datetime) -> str:
    if event_direction_class == "REVERSAL_CANDIDATE":
        return "WATCHLIST"
    if last_seen_at < datetime.now(UTC) - timedelta(days=30):
        return "DORMANT"
    return "ACTIVE"


def _normalize_side(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_json_safe(inner) for inner in value]
    if isinstance(value, datetime):
        return _normalize_timestamp(value).isoformat()
    return value


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_manual_items(path: Path) -> list[ManualWhaleEventItem]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manual whale input must be a JSON array")

    items: list[ManualWhaleEventItem] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("manual whale input rows must be objects")
        timestamp_raw = row.get("event_timestamp")
        if not isinstance(timestamp_raw, str):
            raise ValueError("event_timestamp must be an ISO8601 string")
        parsed_timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
        items.append(
            ManualWhaleEventItem(
                wallet_address=str(row.get("wallet_address") or ""),
                market_id=str(row.get("market_id") or ""),
                event_timestamp=parsed_timestamp,
                side_or_outcome=_as_optional_str(row.get("side_or_outcome")),
                size=float(row.get("size")),
                notional=None if row.get("notional") is None else float(row.get("notional")),
                price=None if row.get("price") is None else float(row.get("price")),
                transaction_ref=_as_optional_str(row.get("transaction_ref")),
                source_type=_as_optional_str(row.get("source_type")) or "MANUAL_IMPORT",
                position_effect=_as_optional_str(row.get("position_effect")),
                previous_side_or_outcome=_as_optional_str(row.get("previous_side_or_outcome")),
                source_payload_json=_json_safe(row.get("source_payload_json") or row),
            )
        )
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 5A whale scanner")
    parser.add_argument("--manual-import-json", required=True, help="path to a JSON array of whale events")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    items = _load_manual_items(Path(args.manual_import_json))
    service = WhaleScannerService()
    result = service.scan_manual_items(items, source_ref=args.source_ref or args.manual_import_json)
    if result is None:
        print("Whale scanner persistence is unavailable.")
        return 1

    print(
        f"whale_scan_run_id={result.whale_scan_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
