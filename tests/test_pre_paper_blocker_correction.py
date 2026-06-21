from __future__ import annotations

from app.control_center import pre_paper_active_truth as active_truth
from app.services import lifecycle_governance as lifecycle


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, *, tables=None, columns=None, duplicate_rows=None, open_positions=0, capital_row=None):
        self.tables = set(tables or [])
        self.columns = {table: set(cols) for table, cols in (columns or {}).items()}
        self.duplicate_rows = duplicate_rows or []
        self.open_positions = open_positions
        self.capital_row = capital_row
        self.queries: list[str] = []

    def execute(self, query, params=()):
        text = str(query)
        self.queries.append(text)
        if "to_regclass" in text:
            value = params[0] if params and params[0] in self.tables else None
            return _Result([{"reg": value, "table_name": value}])
        if "information_schema.columns" in text:
            table, column = params
            return _Result([{"?column?": 1}] if column in self.columns.get(table, set()) else [])
        if "FROM paper_intents" in text and "GROUP BY market_id, side" in text:
            return _Result(self.duplicate_rows)
        if "FROM paper_positions" in text and "COUNT(*) AS count" in text:
            return _Result([{"count": self.open_positions}])
        if "FROM brain_outputs" in text:
            return _Result([self.capital_row] if self.capital_row else [])
        return _Result([])


def test_duplicate_intent_truth_uses_intent_status_and_excludes_consumed_lineage() -> None:
    conn = _FakeConn(
        tables={"paper_intents", "paper_fills", "paper_positions"},
        columns={
            "paper_intents": {"intent_status"},
            "paper_fills": {"source_intent_id"},
            "paper_positions": {"payload_json"},
        },
        duplicate_rows=[],
    )

    assert active_truth.duplicate_active_intent_risk_count(conn) == 0
    query = "\n".join(conn.queries)
    assert "intent_status" in query
    assert "paper_intents.status" not in query
    assert "paper_fills" in query
    assert "paper_positions" in query


def test_active_same_market_intents_still_block() -> None:
    conn = _FakeConn(
        tables={"paper_intents"},
        columns={"paper_intents": {"intent_status"}},
        duplicate_rows=[{"market_id": "m1", "side": "YES", "count": 2}],
    )

    assert active_truth.duplicate_active_intent_risk_count(conn) == 1


def test_quarantined_excluded_positions_do_not_count_as_open() -> None:
    conn = _FakeConn(
        tables={"paper_positions"},
        columns={"paper_positions": {"current_status", "closed_at", "excluded_from_active_paper_truth"}},
        open_positions=0,
    )

    assert active_truth.active_open_position_count(conn) == 0
    query = "\n".join(conn.queries)
    assert "current_status" in query
    assert "excluded_from_active_paper_truth" in query


def test_true_active_open_positions_still_block() -> None:
    conn = _FakeConn(
        tables={"paper_positions"},
        columns={"paper_positions": {"current_status", "closed_at", "excluded_from_active_paper_truth"}},
        open_positions=1,
    )

    assert active_truth.active_open_position_count(conn) == 1


def test_fresh_event_native_capital_truth_is_usable_for_lifecycle() -> None:
    conn = _FakeConn(
        tables={"brain_outputs"},
        capital_row={
            "brain_output_id": "bo_capital",
            "market_id": "m1",
            "correlation_id": "corr1",
            "metadata_json": {
                "capital_opinion_state": "CAPITAL_OK",
                "available_capital": 100,
                "locked_capital": 0,
                "open_exposure": 0,
                "blockers": [],
                "warnings": [],
            },
            "age_seconds": 30,
        },
    )

    truth = lifecycle._event_native_capital_truth(
        conn,
        {"subject_type": "PAPER_CANDIDATE", "subject_id": "cand1", "market_id": "m1", "side": "YES", "token_id": "tok1"},
    )

    assert truth["fresh"] is True
    assert truth["capital_opinion_state"] == "CAPITAL_OK"
    assert truth["reason"] == "FRESH_EVENT_NATIVE_CAPITAL"


def test_stale_event_native_capital_truth_does_not_clear_lifecycle_blocker() -> None:
    conn = _FakeConn(
        tables={"brain_outputs"},
        capital_row={
            "brain_output_id": "bo_capital",
            "market_id": "m1",
            "correlation_id": "corr1",
            "metadata_json": {"capital_opinion_state": "CAPITAL_OK"},
            "age_seconds": 900,
        },
    )

    truth = lifecycle._event_native_capital_truth(
        conn,
        {"subject_type": "PAPER_CANDIDATE", "subject_id": "cand1", "market_id": "m1"},
    )

    assert truth["fresh"] is False
    assert truth["reason"] == "EVENT_NATIVE_CAPITAL_STALE"


def test_lifecycle_force_build_rebuilds_existing_candidate_plan(monkeypatch) -> None:
    service = lifecycle.LifecycleGovernanceGateService()
    calls = {"build": 0}

    class _FakeLifecycle:
        def latest_for_subject(self, conn, *, subject_type, subject_id):
            return {
                "plan_id": "plan_fresh" if calls["build"] else "plan_stale",
                "subject_type": subject_type,
                "subject_id": subject_id,
            }

        def build_subject_with_conn(self, conn, *, subject_type, subject_id, dry_run=False):
            calls["build"] += 1
            return {"status": "OK", "subject_type": subject_type, "subject_id": subject_id}

    service._lifecycle = _FakeLifecycle()

    def _fake_evaluate_plan(conn, plan, *, request_action="OBSERVE", write_decision=True, metadata=None):
        return {"plan_id": plan["plan_id"], "request_action": request_action}

    monkeypatch.setattr(service, "evaluate_plan_with_conn", _fake_evaluate_plan)

    result = service.evaluate_subject_with_conn(
        object(),
        subject_type="PAPER_CANDIDATE",
        subject_id="candidate_force_build",
        request_action="PAPER_INTENT",
        allow_build=True,
        force_build=True,
    )

    assert calls["build"] == 1
    assert result["plan_id"] == "plan_fresh"
