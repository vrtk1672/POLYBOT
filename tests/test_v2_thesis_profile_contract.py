from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.neural_mesh.thesis_profiles import ThesisProfile, ThesisProfileRun


def test_thesis_profile_requires_market_id_for_complete() -> None:
    with pytest.raises(ValueError):
        ThesisProfile(
            thesis_id="thesis-contract",
            status="COMPLETE",
            thesis_type="RUNTIME_COORDINATOR_THESIS",
            why_now="Runtime coordinator evidence is present.",
            confidence=0.8,
        )


def test_thesis_profile_blocks_paper_candidate_allowed() -> None:
    with pytest.raises(ValueError):
        ThesisProfile(
            thesis_id="thesis-paper",
            market_id="market-1",
            status="INCOMPLETE",
            thesis_type="HOLD_FOR_MORE_EVIDENCE",
            why_now="Paper must stay blocked.",
            confidence=0.5,
            paper_candidate_allowed=True,
        )


def test_thesis_run_enforces_non_executing() -> None:
    with pytest.raises(ValueError):
        ThesisProfileRun(
            run_id="run-1",
            status="OK",
            orders_created=1,
            started_at=datetime.now(UTC),
        )

