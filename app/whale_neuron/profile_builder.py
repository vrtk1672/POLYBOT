from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_event_repository import WhaleEventRepository
from app.repositories.whale_performance_repository import WhalePerformanceRepository
from app.repositories.whale_profile_repository import WhaleProfileRepository
from app.whale_neuron.contracts import WhaleEventClassification, WhaleProfile, bounded
from app.whale_neuron.redaction import redact_dict


class WhaleProfileBuilder:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._events = WhaleEventRepository()
        self._profiles = WhaleProfileRepository()
        self._performance = WhalePerformanceRepository()

    def rebuild_whale_profile(self, whale_id: str) -> WhaleProfile:
        if not self._factory.enabled:
            return WhaleProfile(whale_id=whale_id, confidence=0.05)
        with self._factory.connect() as conn:
            events = self._events.list_recent(conn, whale_id=whale_id, limit=500)
            perf = self._performance.list_for_whale(conn, whale_id, limit=500)
        profile = self._build_from_rows(whale_id, events, perf)
        self.persist_profile(profile)
        return profile

    def update_profile_from_event(self, event: Any) -> WhaleProfile:
        return self.rebuild_whale_profile(str(getattr(event, "whale_id", None) or event.get("whale_id")))

    def compute_hit_rate(self, performance_rows: list[dict[str, Any]]) -> float | None:
        useful = [row for row in performance_rows if row.get("follow_result") in {"GOOD_FOLLOW", "BAD_FOLLOW"}]
        if not useful:
            return None
        return bounded(sum(1 for row in useful if row.get("follow_result") == "GOOD_FOLLOW") / len(useful))

    def compute_timing_quality(self, performance_rows: list[dict[str, Any]]) -> float:
        values = [float(row["timing_quality"]) for row in performance_rows if row.get("timing_quality") is not None]
        return bounded(sum(values) / len(values)) if values else 0.25

    def compute_average_trade_size(self, event_rows: list[dict[str, Any]]) -> float | None:
        sizes = [float(row["size_usd"]) for row in event_rows if row.get("size_usd") is not None]
        return sum(sizes) / len(sizes) if sizes else None

    def compute_market_specialties(self, event_rows: list[dict[str, Any]]) -> list[str]:
        families: dict[str, int] = {}
        for row in event_rows:
            family = ((row.get("metadata_json") or {}).get("market_family") if isinstance(row.get("metadata_json"), dict) else None) or "unknown"
            families[str(family)] = families.get(str(family), 0) + 1
        return [family for family, _ in sorted(families.items(), key=lambda item: item[1], reverse=True)[:5] if family != "unknown"]

    def compute_win_consistency(self, performance_rows: list[dict[str, Any]]) -> float | None:
        hit_rate = self.compute_hit_rate(performance_rows)
        return None if hit_rate is None else bounded(1.0 - abs(0.5 - hit_rate) * 2)

    def compute_average_hold_time(self, performance_rows: list[dict[str, Any]]) -> float | None:
        values = [(row.get("metadata_json") or {}).get("hold_time_seconds") for row in performance_rows if isinstance(row.get("metadata_json"), dict)]
        values = [float(value) for value in values if value is not None]
        return sum(values) / len(values) if values else None

    def persist_profile(self, profile: WhaleProfile) -> dict[str, Any]:
        if not self._factory.enabled:
            return profile.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._profiles.insert_profile(conn, profile)
        self._event_bus.publish(EventType.WHALE_PROFILE_UPDATED.value, redact_dict(profile.model_dump(mode="json")), "whale_neuron", aggregate_type="whale", aggregate_id=profile.whale_id)
        return row

    def _build_from_rows(self, whale_id: str, events: list[dict[str, Any]], performance: list[dict[str, Any]]) -> WhaleProfile:
        sample_size = len(events)
        avg_size = self.compute_average_trade_size(events)
        hit_rate = self.compute_hit_rate(performance)
        late_count = sum(1 for row in events if row.get("event_classification") == WhaleEventClassification.LATE_CHASE.value)
        noise = bounded(0.2 + (late_count / max(1, sample_size)) * 0.5 + (0.25 if sample_size < 3 else 0))
        timing = self.compute_timing_quality(performance)
        follow = bounded((timing * 0.45) + ((hit_rate or 0.5) * 0.3) + ((1 - noise) * 0.25)) if sample_size >= 3 else 0.25
        copy = bounded(follow * (1 - noise)) if sample_size >= 3 else 0.0
        return WhaleProfile(
            whale_id=whale_id,
            hit_rate=hit_rate,
            timing_quality=timing,
            average_trade_size_usd=avg_size,
            average_hold_time_seconds=self.compute_average_hold_time(performance),
            win_consistency=self.compute_win_consistency(performance),
            market_specialties=self.compute_market_specialties(events),
            follow_value=follow,
            noise_score=noise,
            momentum_chase_score=bounded(late_count / max(1, sample_size)),
            reversal_risk_score=bounded(sum(1 for row in events if row.get("event_classification") in {"EXIT", "DISTRIBUTION", "REVERSAL"}) / max(1, sample_size)),
            copy_worthy_score=copy,
            confidence=bounded(min(1.0, sample_size / 10)),
            sample_size=sample_size,
        )

