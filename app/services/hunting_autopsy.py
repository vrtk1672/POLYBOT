from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.utils.json_safety import json_safe


class HuntingAutopsyService:
    """Read-only Full Mesh hunting continuity and re-hunt forensic view."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_autopsy(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "runtime_continuity_verdict": "UNKNOWN"}
        with self._factory.connect() as conn:
            tables = _tables(conn)
            active_session = _active_session(conn, tables)
            cycles = _latest_cycles(conn, tables, limit=10)
            runtime_truth = _runtime_truth(conn, tables)
            windows = _window_deltas(conn, tables, active_session)
            organs = _organ_heartbeats(conn, tables)
            diversity = _decision_diversity(conn, tables)
            enter = _enter_lifecycle(conn, tables, active_session)
            post_trade = _post_trade_rehunt(conn, tables, active_session)
            errors = _latest_errors(conn, tables)
            verdicts = _verdicts(runtime_truth, windows, diversity, enter, post_trade, errors)
            return json_safe(
                {
                    "status": "OK",
                    "generated_at": datetime.now(UTC),
                    "active_paper_session_id": (active_session or {}).get("paper_session_id"),
                    "runtime_continuity_verdict": verdicts["runtime_continuity_verdict"],
                    "hunting_verdict": verdicts["hunting_verdict"],
                    "trade_lifecycle_verdict": verdicts["trade_lifecycle_verdict"],
                    "primary_bottleneck": verdicts["primary_bottleneck"],
                    "repair_needed": verdicts["repair_needed"],
                    "repair_scope": verdicts["repair_scope"],
                    "evidence_for_bottleneck": verdicts["evidence_for_bottleneck"],
                    "runtime_truth": runtime_truth,
                    "last_10_cycles": cycles,
                    "organ_heartbeats": organs,
                    "hunting_progression": windows,
                    "decision_diversity": diversity,
                    "enter_lifecycle": enter,
                    "post_trade_rehunt": post_trade,
                    "latest_errors": errors,
                    "recommended_next_action": _recommended_next_action(verdicts),
                    "safety": _safety(conn, tables),
                }
            )


def _runtime_truth(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "runtime_cycles_v2" not in tables:
        return {"current_active_cycle_id": None, "open_cycles": 0, "stale_open_cycles": 0}
    row = conn.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE finished_at IS NULL AND status IN ('RUNNING','STARTING')) AS open_cycles,
            COUNT(*) FILTER (
                WHERE finished_at IS NULL
                  AND status IN ('RUNNING','STARTING')
                  AND started_at < now() - interval '10 minutes'
            ) AS stale_open_cycles,
            COUNT(*) FILTER (WHERE status='STALE_ABANDONED') AS stale_abandoned_cycles,
            AVG(EXTRACT(EPOCH FROM (finished_at-started_at))) FILTER (
                WHERE finished_at IS NOT NULL
                  AND started_at >= now() - interval '30 minutes'
            ) AS avg_completed_cycle_seconds
        FROM runtime_cycles_v2
        """
    ).fetchone()
    active = conn.execute(
        """
        SELECT cycle_id, mode, status, started_at, finished_at, metadata_json
        FROM runtime_cycles_v2
        WHERE finished_at IS NULL
          AND status IN ('RUNNING','STARTING')
          AND started_at >= now() - interval '10 minutes'
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    latest_completed = conn.execute(
        """
        SELECT cycle_id, mode, status, started_at, finished_at, metadata_json
        FROM runtime_cycles_v2
        WHERE finished_at IS NOT NULL
          AND status IN ('COMPLETED','DEGRADED','STOPPED','SAFE_STOPPED')
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "current_active_cycle_id": active["cycle_id"] if active else None,
        "current_active_cycle": dict(active) if active else None,
        "latest_completed_cycle_id": latest_completed["cycle_id"] if latest_completed else None,
        "latest_completed_cycle": dict(latest_completed) if latest_completed else None,
        "open_cycles": _int((row or {}).get("open_cycles")),
        "stale_open_cycles": _int((row or {}).get("stale_open_cycles")),
        "stale_abandoned_cycles": _int((row or {}).get("stale_abandoned_cycles")),
        "avg_completed_cycle_seconds": _float((row or {}).get("avg_completed_cycle_seconds")),
    }


def _latest_cycles(conn: Any, tables: dict[str, set[str]], *, limit: int) -> list[dict[str, Any]]:
    if "runtime_cycles_v2" not in tables:
        return []
    rows = conn.execute(
        """
        SELECT cycle_id, mode, status, started_at, finished_at,
               EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))::int AS duration_seconds,
               error_count, warning_count, metadata_json
        FROM runtime_cycles_v2
        ORDER BY started_at DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _window_deltas(conn: Any, tables: dict[str, set[str]], active_session: dict[str, Any] | None) -> list[dict[str, Any]]:
    windows: list[tuple[str, Any]] = [
        ("10m", "now() - interval '10 minutes'"),
        ("30m", "now() - interval '30 minutes'"),
    ]
    if active_session and active_session.get("started_at"):
        windows.append(("active_session", "%s"))
    out: list[dict[str, Any]] = []
    for label, since_expr in windows:
        params: tuple[Any, ...] = (active_session["started_at"],) if since_expr == "%s" and active_session else ()
        since_sql = since_expr
        item = {
            "window": label,
            "new_markets": _count_since(conn, tables, "market_universe_memory", "created_at", since_sql, params),
            "events_touched": _count_since(conn, tables, "source_event_memory", "COALESCE(ingested_at, first_seen_at, updated_at)", since_sql, params),
            "linked_events_touched": _count_since(conn, tables, "event_to_market_recall", "COALESCE(updated_at, created_at)", since_sql, params),
            "triggers_touched": _count_since(conn, tables, "multi_trigger_candidate_triggers", "COALESCE(updated_at, created_at)", since_sql, params),
            "candidates_touched": _count_since(conn, tables, "proactive_candidate_seeds", "COALESCE(updated_at, created_at)", since_sql, params),
            "mesh_reviews_touched": _count_since(conn, tables, "proactive_seed_mesh_results", "COALESCE(updated_at, created_at)", since_sql, params),
            "policy_reviews_touched": _count_since(conn, tables, "paper_observation_policy_reviews", "COALESCE(updated_at, created_at)", since_sql, params),
            "runtime_decision_runs": _count_since(conn, tables, "paper_runtime_decision_runs", "created_at", since_sql, params),
            "runtime_decisions_touched": _count_since(conn, tables, "paper_runtime_decisions", "COALESCE(updated_at, created_at)", since_sql, params),
            "enter_decisions_touched": _count_since_where(conn, tables, "paper_runtime_decisions", "COALESCE(updated_at, created_at)", since_sql, "decision='ENTER'", params),
            "no_trade_touched": _count_since(conn, tables, "no_trade_log", "COALESCE(updated_at, created_at)", since_sql, params),
            "intent_gate_runs": _count_since(conn, tables, "paper_intent_runs", "created_at", since_sql, params),
            "execution_runs": _count_since(conn, tables, "paper_execution_runs", "created_at", since_sql, params),
            "exit_runs": _count_since(conn, tables, "paper_exit_loop_runs", "created_at", since_sql, params),
            "paper_intents_created": _count_since(conn, tables, "paper_intents", "created_at", since_sql, params),
            "paper_orders_created": _count_since(conn, tables, "paper_orders", "created_at", since_sql, params),
            "paper_fills_created": _count_since(conn, tables, "paper_fills", "created_at", since_sql, params),
            "paper_positions_touched": _count_since(conn, tables, "paper_positions", "COALESCE(updated_at, opened_at)", since_sql, params),
            "paper_closes_created": _count_since(conn, tables, "paper_position_closes", "created_at", since_sql, params),
        }
        out.append(item)
    return out


def _decision_diversity(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "paper_runtime_decisions" not in tables:
        return {}
    current = "is_current_batch IS TRUE" if "is_current_batch" in tables["paper_runtime_decisions"] else "true"
    summary = conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT market_id) AS unique_markets,
               COUNT(DISTINCT side) AS unique_sides,
               COUNT(DISTINCT market_id || ':' || side) AS unique_market_sides,
               COUNT(*) FILTER (WHERE decision='ENTER') AS enter_count,
               COUNT(DISTINCT market_id) FILTER (WHERE decision='ENTER') AS enter_unique_markets
        FROM paper_runtime_decisions
        WHERE {current}
        """
    ).fetchone()
    top_pairs = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT decision, market_id, side, COUNT(*) AS count,
                   MAX(opportunity_score) AS max_score,
                   MAX(updated_at) AS latest_updated_at
            FROM paper_runtime_decisions
            WHERE {current}
            GROUP BY decision, market_id, side
            ORDER BY count DESC, max_score DESC, market_id, side
            LIMIT 20
            """
        ).fetchall()
    ]
    opposing_enters = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT market_id, array_agg(DISTINCT side ORDER BY side) AS sides,
                   COUNT(*) AS enter_count, MAX(opportunity_score) AS max_score
            FROM paper_runtime_decisions
            WHERE {current} AND decision='ENTER'
            GROUP BY market_id
            HAVING COUNT(DISTINCT side) > 1
            ORDER BY enter_count DESC, max_score DESC
            """
        ).fetchall()
    ]
    blockers = _json_counter(conn, "paper_runtime_decisions", "blockers_json", current, limit=12)
    total = max(1, _int((summary or {}).get("total")))
    largest = max([_int(item.get("count")) for item in top_pairs] or [0])
    return {
        "total_runtime_decisions": _int((summary or {}).get("total")),
        "unique_markets": _int((summary or {}).get("unique_markets")),
        "unique_sides": _int((summary or {}).get("unique_sides")),
        "unique_market_sides": _int((summary or {}).get("unique_market_sides")),
        "enter_count": _int((summary or {}).get("enter_count")),
        "enter_unique_markets": _int((summary or {}).get("enter_unique_markets")),
        "concentration_score": round(largest / total, 4),
        "top_market_sides": top_pairs,
        "opposing_enter_markets": opposing_enters,
        "top_blockers": blockers,
    }


def _enter_lifecycle(conn: Any, tables: dict[str, set[str]], active_session: dict[str, Any] | None) -> dict[str, Any]:
    if "paper_runtime_decisions" not in tables:
        return {"items": []}
    session_id = (active_session or {}).get("paper_session_id")
    rows = conn.execute(
        """
        SELECT *
        FROM paper_runtime_decisions
        WHERE decision='ENTER'
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 20
        """
    ).fetchall()
    items = []
    for row_obj in rows:
        row = dict(row_obj)
        decision_id = row.get("decision_id")
        intent = None
        if "paper_intents" in tables:
            intent = conn.execute(
                """
                SELECT *
                FROM paper_intents
                WHERE evidence->>'paper_runtime_decision_id'=%s
                  AND (%s::text IS NULL OR paper_session_id=%s::text)
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (decision_id, session_id, session_id),
            ).fetchone()
        no_trade = None
        if "no_trade_log" in tables:
            no_trade = conn.execute(
                """
                SELECT *
                FROM no_trade_log
                WHERE market_id=%s
                  AND COALESCE(side,'')=COALESCE(%s,'')
                  AND (%s::text IS NULL OR evidence->>'paper_session_id'=%s::text)
                ORDER BY updated_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (row.get("market_id"), row.get("side"), session_id, session_id),
            ).fetchone()
        blockers = _list(row.get("blockers_json"))
        skip = _skip_reason(blockers, dict(no_trade) if no_trade else None)
        items.append(
            {
                "decision_id": decision_id,
                "market_id": row.get("market_id"),
                "side": row.get("side"),
                "score": _float(row.get("opportunity_score")),
                "paper_session_id": session_id,
                "selected_by_gate": True,
                "intent_created": bool(intent),
                "intent_id": intent["paper_intent_id"] if intent else None,
                "skip_reason": skip,
                "bug_suspect": not bool(intent) and not bool(skip),
                "blockers": blockers,
                "updated_at": row.get("updated_at"),
            }
        )
    return {
        "items": items,
        "enter_count": len(items),
        "bug_suspect_count": sum(1 for item in items if item["bug_suspect"]),
        "expected_skip_count": sum(1 for item in items if item["skip_reason"]),
    }


def _post_trade_rehunt(conn: Any, tables: dict[str, set[str]], active_session: dict[str, Any] | None) -> dict[str, Any]:
    session_id = (active_session or {}).get("paper_session_id")
    latest_position = None
    if "paper_positions" in tables:
        latest_position = conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE (%s::text IS NULL OR paper_session_id=%s::text)
            ORDER BY COALESCE(opened_at, updated_at) DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (session_id, session_id),
        ).fetchone()
    latest_close = None
    if "paper_position_closes" in tables:
        latest_close = conn.execute(
            """
            SELECT *
            FROM paper_position_closes
            WHERE (%s::text IS NULL OR paper_session_id=%s::text)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id, session_id),
        ).fetchone()
    anchor = None
    if latest_close:
        anchor = latest_close["created_at"]
    elif latest_position:
        anchor = latest_position.get("opened_at") or latest_position.get("updated_at")
    after = {}
    if anchor:
        after = {
            "candidate_generation_after_trade": _count_since(conn, tables, "proactive_candidate_seeds", "COALESCE(updated_at, created_at)", "%s", (anchor,)),
            "mesh_reviews_after_trade": _count_since(conn, tables, "proactive_seed_mesh_results", "COALESCE(updated_at, created_at)", "%s", (anchor,)),
            "runtime_decision_runs_after_trade": _count_since(conn, tables, "paper_runtime_decision_runs", "created_at", "%s", (anchor,)),
            "intent_gate_runs_after_trade": _count_since(conn, tables, "paper_intent_runs", "created_at", "%s", (anchor,)),
            "exit_runs_after_trade": _count_since(conn, tables, "paper_exit_loop_runs", "created_at", "%s", (anchor,)),
            "no_trade_after_trade": _count_since(conn, tables, "no_trade_log", "COALESCE(updated_at, created_at)", "%s", (anchor,)),
        }
    return {
        "latest_current_session_position": dict(latest_position) if latest_position else None,
        "latest_current_session_close": dict(latest_close) if latest_close else None,
        "rehunt_anchor_at": anchor,
        **after,
        "returns_to_hunting": bool(after) and (
            after.get("candidate_generation_after_trade", 0) > 0
            or after.get("runtime_decision_runs_after_trade", 0) > 0
            or after.get("intent_gate_runs_after_trade", 0) > 0
        ),
    }


def _organ_heartbeats(conn: Any, tables: dict[str, set[str]]) -> list[dict[str, Any]]:
    items = []
    if "service_health" in tables:
        rows = conn.execute(
            """
            SELECT service_name, service_type, status, last_heartbeat_at, last_success_at,
                   last_error_at, error_count, warning_count, lag_seconds, details_json, updated_at
            FROM service_health
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 50
            """
        ).fetchall()
        for row in rows:
            item = dict(row)
            last_seen = item.get("last_heartbeat_at") or item.get("last_success_at") or item.get("updated_at")
            stale = _is_stale(last_seen, seconds=900)
            items.append(
                {
                    **item,
                    "next_run_at": None,
                    "run_count": None,
                    "success_count": None,
                    "failure_count": item.get("error_count"),
                    "stale": stale,
                    "blocks_trading": False,
                }
            )
    run_tables = {
        "PaperRuntimeDecisionService": "paper_runtime_decision_runs",
        "PaperIntentGateService": "paper_intent_runs",
        "PaperExecutionAdapter": "paper_execution_runs",
        "PaperExitLoopService": "paper_exit_loop_runs",
    }
    for name, table in run_tables.items():
        if table not in tables:
            continue
        row = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        if row:
            payload = dict(row)
            status = str(payload.get("status") or "UNKNOWN").upper()
            items.append(
                {
                    "service_name": name,
                    "service_type": "paper_runtime",
                    "status": status,
                    "last_heartbeat_at": payload.get("created_at"),
                    "last_success_at": payload.get("finished_at") if status not in {"ERROR", "FAILED"} else None,
                    "last_error_at": payload.get("finished_at") if status in {"ERROR", "FAILED"} else None,
                    "last_error": payload.get("error_summary") or payload.get("error_message") or payload.get("latest_error"),
                    "run_count": _count(conn, table),
                    "success_count": _count_where(conn, table, "status NOT IN ('ERROR','FAILED')"),
                    "failure_count": _count_where(conn, table, "status IN ('ERROR','FAILED')"),
                    "stale": _is_stale(payload.get("created_at"), seconds=900),
                    "blocks_trading": False,
                }
            )
    return items


def _latest_errors(conn: Any, tables: dict[str, set[str]]) -> list[dict[str, Any]]:
    out = []
    for table, field in (
        ("paper_intent_runs", "error_summary"),
        ("paper_execution_runs", "error_message"),
        ("paper_exit_loop_runs", "error_summary"),
        ("paper_runtime_decision_runs", "latest_error"),
    ):
        if table not in tables or field not in tables[table]:
            continue
        rows = conn.execute(
            f"""
            SELECT %s AS source, status, {field} AS error, created_at
            FROM {table}
            WHERE COALESCE({field}, '') <> ''
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 5
            """,
            (table,),
        ).fetchall()
        for row in rows:
            out.append({**dict(row), "classification": "TRUE_ERROR"})
    return out[:10]


def _verdicts(
    runtime_truth: dict[str, Any],
    windows: list[dict[str, Any]],
    diversity: dict[str, Any],
    enter: dict[str, Any],
    post_trade: dict[str, Any],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    recent = next((item for item in windows if item.get("window") == "10m"), {})
    moving = any(_int(recent.get(key)) > 0 for key in ("events_touched", "triggers_touched", "candidates_touched", "mesh_reviews_touched", "runtime_decision_runs", "intent_gate_runs"))
    stale_open = _int(runtime_truth.get("stale_open_cycles"))
    runtime_verdict = "CONTINUOUS" if moving and stale_open == 0 else "PARTIAL" if moving else "STALLED"
    opposing = bool(diversity.get("opposing_enter_markets"))
    if opposing:
        hunting_verdict = "STUCK_AT_GATE"
        primary = "SAME_MARKET_OPPOSING_ENTER_CONFLICT"
        repair_needed = "YES"
        repair_scope = "B4 same-market opposing ENTER arbitration"
        evidence = "Current ENTER decisions contain both YES and NO for the same market."
    elif _int(diversity.get("unique_markets")) <= 2:
        hunting_verdict = "NARROW_REPEAT"
        primary = "DECISION_DIVERSITY_COLLAPSE"
        repair_needed = "YES"
        repair_scope = "B3 decision diversity diagnostics/selection"
        evidence = "Runtime decisions are concentrated in a small number of markets."
    elif moving:
        hunting_verdict = "BROAD_HUNTING"
        primary = "NO_BUG_CONSERVATIVE_FILTERING"
        repair_needed = "NO"
        repair_scope = "none"
        evidence = "Runtime work is moving and non-ENTER candidates are blocked by explicit blockers."
    else:
        hunting_verdict = "UNKNOWN"
        primary = "UNKNOWN"
        repair_needed = "YES"
        repair_scope = "audit scheduler"
        evidence = "Recent runtime work did not move."
    if enter.get("bug_suspect_count"):
        lifecycle = "UNKNOWN"
        primary = "PAPER_INTENT_GATE_NOT_CONTINUOUS"
        repair_needed = "YES"
        repair_scope = "B2 PaperIntentGate lifecycle"
    elif post_trade.get("returns_to_hunting") or _int(recent.get("intent_gate_runs")) > 0:
        lifecycle = "ENTER_EXECUTE_EXIT_REHUNT_OK" if post_trade.get("latest_current_session_close") else "ENTER_OK_EXIT_UNKNOWN"
    else:
        lifecycle = "UNKNOWN"
    if stale_open:
        runtime_verdict = "PARTIAL"
        if primary == "NO_BUG_CONSERVATIVE_FILTERING":
            primary = "SUPERVISOR_SCHEDULER_BUG"
            repair_needed = "YES"
            repair_scope = "B1 stale open cycle cleanup"
            evidence = f"{stale_open} stale open runtime cycle(s) remain in runtime_cycles_v2."
    return {
        "runtime_continuity_verdict": runtime_verdict,
        "hunting_verdict": hunting_verdict,
        "trade_lifecycle_verdict": lifecycle,
        "primary_bottleneck": primary,
        "repair_needed": repair_needed,
        "repair_scope": repair_scope,
        "evidence_for_bottleneck": evidence,
    }


def _recommended_next_action(verdicts: dict[str, Any]) -> str:
    if verdicts["primary_bottleneck"] == "SAME_MARKET_OPPOSING_ENTER_CONFLICT":
        return "Keep same-market guard active; arbitrate opposing ENTERs before PaperIntentGate."
    if verdicts["primary_bottleneck"] == "NO_BUG_CONSERVATIVE_FILTERING":
        return "Continue PAPER runtime; review top WATCH blockers and improve evidence organically."
    return f"Repair scope: {verdicts.get('repair_scope')}"


def _safety(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    return {
        "paper_only": True,
        "live_orders": _count(conn, "live_orders") if "live_orders" in tables else 0,
        "shadow_orders": _count(conn, "shadow_orders") if "shadow_orders" in tables else 0,
        "real_orders": _count(conn, "orders_v2") if "orders_v2" in tables else 0,
    }


def _active_session(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any] | None:
    if "paper_sessions" not in tables:
        return None
    row = conn.execute("SELECT * FROM paper_sessions WHERE status='ACTIVE' ORDER BY started_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _tables(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema=current_schema()").fetchall()
    out: dict[str, set[str]] = {}
    for row in rows:
        out.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return out


def _count_since(conn: Any, tables: dict[str, set[str]], table: str, timestamp_expr: str, since_sql: str, params: tuple[Any, ...]) -> int:
    if table not in tables:
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {timestamp_expr} >= {since_sql}", params).fetchone()
    return _int((row or {}).get("count"))


def _count_since_where(conn: Any, tables: dict[str, set[str]], table: str, timestamp_expr: str, since_sql: str, predicate: str, params: tuple[Any, ...]) -> int:
    if table not in tables:
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {timestamp_expr} >= {since_sql} AND {predicate}", params).fetchone()
    return _int((row or {}).get("count"))


def _count(conn: Any, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return _int((row or {}).get("count"))


def _count_where(conn: Any, table: str, predicate: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}").fetchone()
    return _int((row or {}).get("count"))


def _json_counter(conn: Any, table: str, field: str, predicate: str, *, limit: int) -> list[str]:
    rows = conn.execute(
        f"""
        SELECT value, COUNT(*) AS count
        FROM {table}, jsonb_array_elements_text(COALESCE({field}, '[]'::jsonb)) AS value
        WHERE {predicate}
        GROUP BY value
        ORDER BY count DESC, value
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [f"{row['value']}: {row['count']}" for row in rows]


def _skip_reason(blockers: list[str], no_trade: dict[str, Any] | None) -> str | None:
    evidence = (no_trade or {}).get("evidence") if isinstance((no_trade or {}).get("evidence"), dict) else {}
    combined = {str(item).upper() for item in [*blockers, *_list((no_trade or {}).get("blockers"))] if str(item or "").strip()}
    for code in (
        "SAME_MARKET_OPPOSING_ENTER_CONFLICT",
        "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION",
        "SAME_MARKET_BATCH_CONFLICT_BLOCK",
        "SAME_MARKET_OPPOSING_SIDE_BLOCK",
        "DUPLICATE_OPEN_PAPER_EXPOSURE",
        "DUPLICATE_ACTIVE_PAPER_INTENT",
        "ORDERBOOK_NOT_FRESH",
        "PAPER_RUNTIME_DECISION_DENIED",
    ):
        if code in combined:
            return code
    outcome = str(evidence.get("bridge_outcome") or "").upper()
    return outcome if outcome and outcome not in {"PAPER_INTENT_CREATED", "RESOLVED"} else None


def _is_stale(value: Any, *, seconds: int) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return True
    if not isinstance(value, datetime):
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (datetime.now(UTC) - value.astimezone(UTC)).total_seconds() > seconds


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
