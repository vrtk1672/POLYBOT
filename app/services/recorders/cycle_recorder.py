from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.domain.contracts.cycle import CycleCloseContract, CycleOpenContract
from app.repositories.cycle_repository import CycleRepository


class CycleRecorder:
    def __init__(self, repository: CycleRepository | None = None) -> None:
        self._repository = repository or CycleRepository()

    def open_cycle(
        self,
        conn,
        *,
        mode: str,
        trigger_source: str,
        top_n: int,
        pages_requested: int | None,
        session_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> tuple[str, float]:
        cycle_id = str(uuid4())
        started_at = datetime.now(UTC)
        started_perf = perf_counter()
        self._repository.open_cycle(
            conn,
            CycleOpenContract(
                id=cycle_id,
                started_at=started_at,
                status="OPEN",
                mode=mode,
                trigger_source=trigger_source,
                session_id=session_id,
                top_n=top_n,
                pages_requested=pages_requested,
                metadata=metadata or {},
            ),
        )
        return cycle_id, started_perf

    def close_cycle(
        self,
        conn,
        *,
        cycle_id: str,
        started_perf: float,
        status: str,
        markets_fetched_count: int,
        markets_scored_count: int,
        markets_ranked_count: int,
        decisions_count: int,
        selected_market_id: str | None,
        last_error: str | None = None,
    ) -> None:
        runtime_ms = round((perf_counter() - started_perf) * 1000)
        self._repository.close_cycle(
            conn,
            CycleCloseContract(
                id=cycle_id,
                status=status,
                completed_at=datetime.now(UTC),
                markets_fetched_count=markets_fetched_count,
                markets_scored_count=markets_scored_count,
                markets_ranked_count=markets_ranked_count,
                decisions_count=decisions_count,
                selected_market_id=selected_market_id,
                runtime_ms=runtime_ms,
                last_error=last_error,
            ),
        )
