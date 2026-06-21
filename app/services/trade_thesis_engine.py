from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


SUBJECT_TYPES = {"PAPER_POSITION", "PAPER_CANDIDATE", "PAPER_INTENT", "FRESH_SEED"}

THESIS_TYPES = {
    "HOLD_TO_RESOLUTION",
    "CATALYST_EARLY_EXIT",
    "NEWS_REACTION",
    "EVENT_WINDOW_TRADE",
    "MISPRICING_REVERSION",
    "ORDERBOOK_PRESSURE_TRADE",
    "MOMENTUM_CONTINUATION",
    "REVERSAL_OVERREACTION",
    "WHALE_FOLLOW",
    "LIQUIDITY_SPREAD_OPPORTUNITY",
    "NO_VALID_THESIS",
    "UNKNOWN",
}

EXIT_INTENTS = {
    "HOLD_TO_RESOLUTION",
    "EARLY_EXIT",
    "PRICE_TARGET_EXIT",
    "TIME_STOP_EXIT",
    "CATALYST_REACTION_EXIT",
    "EVENT_WINDOW_EXIT",
    "MOMENTUM_EXIT",
    "REVERSAL_EXIT",
    "WHALE_FOLLOW_EXIT",
    "LIQUIDITY_EXIT",
    "UNKNOWN_EXIT",
}

EARLY_EXIT_HOLD_HOURS = {
    "NEWS_REACTION": Decimal("6"),
    "CATALYST_EARLY_EXIT": Decimal("24"),
    "EVENT_WINDOW_TRADE": Decimal("12"),
    "MISPRICING_REVERSION": Decimal("48"),
    "ORDERBOOK_PRESSURE_TRADE": Decimal("3"),
    "MOMENTUM_CONTINUATION": Decimal("4"),
    "REVERSAL_OVERREACTION": Decimal("12"),
    "WHALE_FOLLOW": Decimal("72"),
    "LIQUIDITY_SPREAD_OPPORTUNITY": Decimal("3"),
}


class TradeThesisEngine:
    """DATA_ONLY classifier for trade type, exit intent, and hold-time basis.

    The engine only shortens hold time when existing source records support a
    concrete early-exit thesis. It does not create trading intents, orders,
    fills, positions, capital reservations, or fabricated source evidence.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def evaluate_recent(self, *, limit: int = 100, subject_type: str | None = "PAPER_CANDIDATE", dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        subject = str(subject_type).upper() if subject_type else None
        if subject and subject not in SUBJECT_TYPES:
            return {"mock_data": False, "status": "INVALID_SUBJECT_TYPE", "evaluations_created": 0}
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evaluations_created": 0}
        with self._factory.connect() as conn, conn.transaction():
            self.ensure_tables(conn)
            before = _count_table(conn, "trade_thesis_evaluations")
            records = _records(conn, subject_type=subject, limit=limit)
            outcomes = [self.evaluate_subject_with_conn(conn, subject_type=item["subject_type"], subject_id=item["subject_id"], dry_run=dry_run) for item in records]
            after = _count_table(conn, "trade_thesis_evaluations")
        counts = Counter(str(item.get("status") or "UNKNOWN") for item in outcomes)
        types = Counter(str(item.get("trade_thesis_type") or "UNKNOWN") for item in outcomes)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "subjects_checked": len(records),
                "evaluations_created": 0 if dry_run else max(0, after - before),
                "outcomes_by_status": dict(counts),
                "thesis_type_distribution": dict(types),
                "latest_outcomes": outcomes[:20],
                "trading_mutation": False,
            }
        )

    def evaluate_subject_with_conn(self, conn: Any, *, subject_type: str, subject_id: str, dry_run: bool = False) -> dict[str, Any]:
        self.ensure_tables(conn)
        record = _record_by_subject(conn, subject_type=str(subject_type).upper(), subject_id=str(subject_id))
        if record is None:
            return {"status": "SUBJECT_NOT_FOUND", "subject_type": subject_type, "subject_id": subject_id}
        evidence = _collect_evidence(conn, record)
        thesis = build_trade_thesis(record, evidence)
        if not dry_run:
            _upsert(conn, thesis)
        return _json_safe(
            {
                "thesis_id": thesis["thesis_id"],
                "subject_type": thesis["subject_type"],
                "subject_id": thesis["subject_id"],
                "trade_thesis_type": thesis["trade_thesis_type"],
                "exit_intent": thesis["exit_intent"],
                "status": thesis["status"],
                "blocker_code": thesis["blocker_code"],
                "expected_hold_time_hours": thesis["expected_hold_time_hours"],
                "dry_run": dry_run,
            }
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "trade_thesis_evaluations"):
            return None
        aliases = _subject_aliases(subject_id)
        return _fetchone(
            conn,
            """
            SELECT * FROM trade_thesis_evaluations
            WHERE subject_type=%s AND subject_id = ANY(%s)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (str(subject_type).upper(), aliases),
        )

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty_dashboard("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            self.ensure_tables(conn)
            totals = _fetchone(
                conn,
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status='THESIS_SUPPORTED') AS supported_count,
                  COUNT(*) FILTER (WHERE status='THESIS_WATCH') AS watch_count,
                  COUNT(*) FILTER (WHERE status IN ('THESIS_REJECTED','THESIS_MISSING')) AS rejected_count,
                  COUNT(*) FILTER (WHERE exit_intent <> 'HOLD_TO_RESOLUTION' AND status='THESIS_SUPPORTED') AS early_exit_supported_count,
                  COUNT(*) FILTER (WHERE ai_review_state='UNAVAILABLE') AS ai_unavailable_count
                FROM trade_thesis_evaluations
                """,
            ) or {}
            latest = _latest_rows(conn, limit=limit)
            type_rows = _fetchall(conn, "SELECT trade_thesis_type, COUNT(*) AS count FROM trade_thesis_evaluations GROUP BY trade_thesis_type ORDER BY trade_thesis_type")
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "total_evaluations": _int(totals.get("total")),
                "supported_count": _int(totals.get("supported_count")),
                "watch_count": _int(totals.get("watch_count")),
                "rejected_count": _int(totals.get("rejected_count")),
                "early_exit_supported_count": _int(totals.get("early_exit_supported_count")),
                "ai_unavailable_count": _int(totals.get("ai_unavailable_count")),
                "thesis_type_distribution": {str(row["trade_thesis_type"]): _int(row["count"]) for row in type_rows},
                "latest_evaluations": latest,
            }
        )

    @staticmethod
    def ensure_tables(conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_thesis_evaluations (
                id BIGSERIAL PRIMARY KEY,
                thesis_id TEXT NOT NULL UNIQUE,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                candidate_id TEXT NULL,
                market_id TEXT NULL,
                condition_id TEXT NULL,
                side TEXT NULL,
                token_id TEXT NULL,
                source_refresh_cycle_id TEXT NULL,
                edge_thesis_id TEXT NULL,
                risk_evidence_id TEXT NULL,
                trade_thesis_type TEXT NOT NULL,
                exit_intent TEXT NOT NULL,
                entry_reason TEXT NOT NULL,
                primary_catalyst TEXT NULL,
                supporting_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                opposing_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                entry_price NUMERIC NULL,
                target_exit_price NUMERIC NULL,
                stop_or_invalidation_price NUMERIC NULL,
                expected_hold_time_hours NUMERIC NULL,
                max_hold_time_hours NUMERIC NULL,
                hold_time_source TEXT NOT NULL,
                expected_price_move NUMERIC NULL,
                expected_reward NUMERIC NULL,
                reward_source TEXT NULL,
                exit_trigger TEXT NULL,
                invalidation_condition TEXT NULL,
                time_stop_condition TEXT NULL,
                thesis_confidence NUMERIC NULL,
                exit_confidence NUMERIC NULL,
                ai_review_state TEXT NOT NULL,
                ai_thesis TEXT NULL,
                ai_counter_thesis TEXT NULL,
                status TEXT NOT NULL,
                blocker_code TEXT NULL,
                required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def build_trade_thesis(record: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    edge = _dict(evidence.get("edge"))
    risk = _dict(evidence.get("risk"))
    payout = _dict(evidence.get("payout"))
    exit_hold = _dict(evidence.get("exit_hold"))
    orderbook = _dict(evidence.get("orderbook"))
    movement = _dict(evidence.get("market_movement"))
    news = _dict(evidence.get("news"))
    whale = _dict(evidence.get("whale"))
    source_refs = _source_refs(evidence)
    supporting = _supporting_sources(source_refs)
    required: list[str] = []
    status = "THESIS_MISSING"
    blocker = "THESIS_REQUIRES_EDGE_SUPPORTED"
    thesis_type = "NO_VALID_THESIS"
    exit_intent = "UNKNOWN_EXIT"
    hold_source = "UNKNOWN"
    expected_hours: Decimal | None = None
    max_hours: Decimal | None = None
    primary = None
    entry_reason = "No supported trade thesis was found from current Mesh evidence."
    exit_trigger = None
    invalidation = None
    confidence = Decimal("0.0")
    exit_confidence = Decimal("0.0")

    edge_state = str(edge.get("edge_state") or "").upper()
    source_backed = bool(edge.get("source_backed"))
    risk_usable = bool(edge.get("risk_usable"))
    if edge_state == "EDGE_SUPPORTED" and source_backed and risk_usable:
        risk_reward = _decimal_or_none(payout.get("risk_reward"))
        price = _decimal_or_none(record.get("entry_price")) or _decimal_or_none(orderbook.get("best_ask")) or _decimal_or_none(orderbook.get("ask_price"))
        exit_price = _decimal_or_none(exit_hold.get("exit_now_price")) or _decimal_or_none(orderbook.get("best_bid")) or _decimal_or_none(orderbook.get("bid_price"))
        spread = _decimal_or_none(orderbook.get("spread"))
        liquidity = str(exit_hold.get("liquidity_exit_quality") or "").upper()
        exit_path = exit_price is not None and spread is not None and liquidity in {"GOOD", "FAIR"}
        if news and _fresh(news, "created_at", ttl_seconds=6 * 3600):
            thesis_type = "NEWS_REACTION"
            exit_intent = "CATALYST_REACTION_EXIT"
            hold_source = "CATALYST_REACTION_WINDOW"
            expected_hours = EARLY_EXIT_HOLD_HOURS[thesis_type]
            max_hours = Decimal("12")
            primary = "fresh candidate-linked news context"
            entry_reason = "Fresh news context supports an early reaction thesis."
            exit_trigger = "Exit on catalyst reaction, target fill, or time stop."
            invalidation = "Invalidate if news direction conflicts or price reaction fails."
            confidence = Decimal("0.72")
        elif whale and _fresh(whale, "event_time", ttl_seconds=12 * 3600):
            thesis_type = "WHALE_FOLLOW"
            exit_intent = "WHALE_FOLLOW_EXIT"
            hold_source = "WHALE_HOLDING_WINDOW"
            expected_hours = EARLY_EXIT_HOLD_HOURS[thesis_type]
            max_hours = Decimal("72")
            primary = "fresh whale flow context"
            entry_reason = "Fresh whale context supports a tactical follow thesis."
            exit_trigger = "Exit when whale-follow window expires or orderbook support fades."
            invalidation = "Invalidate on opposing flow, stale wallet signal, or price failure."
            confidence = Decimal("0.66")
        elif risk_reward is not None and risk_reward >= Decimal("1.0") and payout:
            thesis_type = "MISPRICING_REVERSION"
            exit_intent = "PRICE_TARGET_EXIT"
            hold_source = "REVERSION_WINDOW"
            expected_hours = EARLY_EXIT_HOLD_HOURS[thesis_type]
            max_hours = Decimal("72")
            primary = "source-backed payout asymmetry"
            entry_reason = "Source-backed payout asymmetry supports a reversion thesis."
            exit_trigger = "Exit when price converges toward payout-implied asymmetry or time stop."
            invalidation = "Invalidate if payout asymmetry disappears, liquidity weakens, or source conflict appears."
            confidence = Decimal("0.74")
        elif movement:
            thesis_type = "MOMENTUM_CONTINUATION"
            exit_intent = "MOMENTUM_EXIT"
            hold_source = "MOMENTUM_WINDOW"
            expected_hours = EARLY_EXIT_HOLD_HOURS[thesis_type]
            max_hours = Decimal("4")
            primary = "fresh derived movement context"
            entry_reason = "Fresh derived movement context supports a tactical momentum watch."
            exit_trigger = "Exit on momentum exhaustion, target fill, or short time stop."
            invalidation = "Invalidate on reversal signal or orderbook pressure fade."
            confidence = Decimal("0.58")
            status = "THESIS_WATCH"
            blocker = "DERIVED_SIGNALS_WATCH_ONLY"
            required.append("Add independent directional source backing beyond derived/orderbook movement.")
        else:
            thesis_type = "HOLD_TO_RESOLUTION"
            exit_intent = "HOLD_TO_RESOLUTION"
            hold_source = "MARKET_RESOLUTION"
            expected_hours = _resolution_hours(exit_hold)
            max_hours = expected_hours
            primary = "hold-to-resolution source-backed edge"
            entry_reason = "Source-backed edge exists, but no early-exit catalyst was found."
            exit_trigger = "Hold until resolution or until standard exit logic triggers."
            invalidation = "Invalidate if source-backed edge, risk, or exit evidence deteriorates."
            confidence = Decimal("0.55")
        if status != "THESIS_WATCH":
            if not exit_path and exit_intent != "HOLD_TO_RESOLUTION":
                status = "THESIS_WATCH"
                blocker = "EXIT_INTENT_NOT_CURRENTLY_SUPPORTED"
                required.append("Provide fresh exit price, spread, and FAIR/GOOD exit liquidity for early-exit thesis.")
            else:
                status = "THESIS_SUPPORTED"
                blocker = None
        exit_confidence = Decimal("0.68") if exit_path else Decimal("0.35")
        if not supporting:
            status = "THESIS_MISSING"
            blocker = "SOURCE_RECORDS_MISSING"
            required.append("Provide source records backing the thesis.")
    else:
        required.append("Candidate must have EDGE_SUPPORTED, source_backed=true, and risk_usable=true before thesis classification.")

    thesis_id = _thesis_id(record, evidence, thesis_type, status)
    expected_reward = _decimal_or_none(exit_hold.get("hold_to_resolution_profit_if_win")) or _decimal_or_none(payout.get("profit_if_win"))
    entry_price = _decimal_or_none(record.get("entry_price")) or _decimal_or_none(orderbook.get("best_ask"))
    target_exit = _decimal_or_none(exit_hold.get("exit_now_price")) or _decimal_or_none(orderbook.get("best_bid"))
    expected_move = None
    if entry_price is not None and target_exit is not None:
        expected_move = target_exit - entry_price
    return {
        "thesis_id": thesis_id,
        "subject_type": record["subject_type"],
        "subject_id": record["subject_id"],
        "candidate_id": record["subject_id"] if record["subject_type"] == "PAPER_CANDIDATE" else record.get("candidate_id"),
        "market_id": record.get("market_id") or payout.get("market_id") or exit_hold.get("market_id"),
        "condition_id": record.get("condition_id") or payout.get("condition_id") or exit_hold.get("condition_id"),
        "side": record.get("side") or payout.get("side") or exit_hold.get("side"),
        "token_id": record.get("token_id") or payout.get("token_id") or exit_hold.get("token_id"),
        "source_refresh_cycle_id": edge.get("source_refresh_cycle_id") or (_dict(risk.get("metadata_json")).get("source_refresh_cycle_id")),
        "edge_thesis_id": edge.get("edge_thesis_id"),
        "risk_evidence_id": risk.get("evaluation_id"),
        "trade_thesis_type": thesis_type,
        "exit_intent": exit_intent,
        "entry_reason": entry_reason,
        "primary_catalyst": primary,
        "supporting_sources_json": supporting,
        "opposing_sources_json": edge.get("opposing_neurons") or [],
        "entry_price": entry_price,
        "target_exit_price": target_exit if status == "THESIS_SUPPORTED" else None,
        "stop_or_invalidation_price": None,
        "expected_hold_time_hours": expected_hours if status == "THESIS_SUPPORTED" else None,
        "max_hold_time_hours": max_hours if status == "THESIS_SUPPORTED" else None,
        "hold_time_source": hold_source,
        "expected_price_move": expected_move,
        "expected_reward": expected_reward,
        "reward_source": "PAYOUT_ODDS_OR_EXIT_HOLD" if expected_reward is not None else None,
        "exit_trigger": exit_trigger,
        "invalidation_condition": invalidation,
        "time_stop_condition": f"Exit or re-evaluate after {max_hours} hours." if max_hours is not None else None,
        "thesis_confidence": confidence,
        "exit_confidence": exit_confidence,
        "ai_review_state": "UNAVAILABLE",
        "ai_thesis": None,
        "ai_counter_thesis": "Deterministic fallback only; AI did not add sources, probabilities, or targets.",
        "status": status,
        "blocker_code": blocker,
        "required_to_pass_json": required,
        "source_refs_json": source_refs,
        "metadata_json": {
            "deterministic_fallback": True,
            "no_ai_sources_added": True,
            "no_probability_fabricated": True,
            "original_edge_state": edge_state,
            "dynamic_hold_time_allowed": status == "THESIS_SUPPORTED" and exit_intent != "UNKNOWN_EXIT",
        },
    }


def _records(conn: Any, *, subject_type: str | None, limit: int) -> list[dict[str, Any]]:
    wanted = [subject_type] if subject_type else ["PAPER_CANDIDATE"]
    rows: list[dict[str, Any]] = []
    if "PAPER_CANDIDATE" in wanted and _table_exists(conn, "paper_eligibility_candidates"):
        rows.extend(
            _fetchall(
                conn,
                """
                SELECT 'PAPER_CANDIDATE' AS subject_type, eligibility_id AS subject_id,
                       market_id, NULL::text AS condition_id, side, expected_token_id AS token_id, evidence, updated_at AS opened_at
                FROM paper_eligibility_candidates
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
        )
    return [_shape_record(row) for row in rows]


def _record_by_subject(conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    rows = _records(conn, subject_type=subject_type, limit=500)
    for row in rows:
        if str(row.get("subject_id")) == str(subject_id):
            return row
    return None


def _shape_record(row: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(row.get("evidence"))
    source_evidence = _dict(evidence.get("source_evidence"))
    row["entry_price"] = _decimal_or_none(evidence.get("orderbook_best_ask") or source_evidence.get("orderbook_best_ask"))
    if not row.get("token_id"):
        row["token_id"] = evidence.get("token_id") or source_evidence.get("token_id")
    return row


def _collect_evidence(conn: Any, record: dict[str, Any]) -> dict[str, Any]:
    subject_type = str(record["subject_type"])
    subject_id = str(record["subject_id"])
    market_id = str(record.get("market_id") or "")
    risk = _latest_subject_row(conn, "risk_evidence_mesh_evaluations", "evaluation_id", subject_type, subject_id, None)
    edge = _dict(_dict(risk.get("metadata_json") if risk else {}).get("edge_thesis"))
    return {
        "risk": risk,
        "edge": edge,
        "payout": _latest_subject_row(conn, "payout_odds_evaluations", "evaluation_id", subject_type, subject_id, None),
        "exit_hold": _latest_subject_row(conn, "exit_hold_evaluations", "evaluation_id", subject_type, subject_id, None),
        "orderbook": _latest_orderbook(conn, record, market_id=market_id),
        "market_movement": _latest_market_row(conn, "market_technical_signals", market_id, "ts"),
        "news": _latest_market_row(conn, "news_impact_scores", market_id, "created_at"),
        "whale": _latest_market_row(conn, "whale_events", market_id, "event_time"),
    }


def _latest_subject_row(conn: Any, table: str, id_col: str, subject_type: str, subject_id: str, explicit_id: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, table):
        return None
    if explicit_id:
        row = _fetchone(conn, f"SELECT * FROM {table} WHERE {id_col}=%s LIMIT 1", (str(explicit_id),))
        if row:
            return row
    if _has_column(conn, table, "subject_type") and _has_column(conn, table, "subject_id"):
        return _fetchone(conn, f"SELECT * FROM {table} WHERE subject_type=%s AND subject_id = ANY(%s) ORDER BY created_at DESC, id DESC LIMIT 1", (subject_type, _subject_aliases(subject_id)))
    return None


def _latest_orderbook(conn: Any, record: dict[str, Any], *, market_id: str) -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, "orderbook_snapshots"):
        return None
    token_id = record.get("token_id")
    clauses = ["market_id=%s"]
    params: list[Any] = [market_id]
    if token_id and _has_column(conn, "orderbook_snapshots", "token_id"):
        clauses.append("token_id=%s")
        params.append(str(token_id))
    return _fetchone(conn, f"SELECT * FROM orderbook_snapshots WHERE {' AND '.join(clauses)} ORDER BY collected_at DESC, id DESC LIMIT 1", tuple(params))


def _latest_market_row(conn: Any, table: str, market_id: str, time_col: str) -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, table) or not _has_column(conn, table, "market_id"):
        return None
    return _fetchone(conn, f"SELECT * FROM {table} WHERE market_id=%s ORDER BY {time_col} DESC NULLS LAST, id DESC LIMIT 1", (market_id,))


def _supporting_sources(refs: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, table, source_type in (
        ("risk_evidence_id", "risk_evidence_mesh_evaluations", "RISK_EVIDENCE"),
        ("payout_odds_evaluation_id", "payout_odds_evaluations", "PAYOUT_ODDS"),
        ("exit_hold_evaluation_id", "exit_hold_evaluations", "EXIT_HOLD"),
        ("orderbook_snapshot_id", "orderbook_snapshots", "ORDERBOOK"),
        ("news_source_id", "news_impact_scores", "NEWS"),
        ("whale_source_id", "whale_events", "WHALE"),
        ("market_movement_source_id", "market_technical_signals", "MARKET_MOVEMENT"),
    ):
        if refs.get(key):
            rows.append({"source_table": table, "source_record_id": str(refs[key]), "source_type": source_type})
    return rows


def _source_refs(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_evidence_id": (_dict(evidence.get("risk"))).get("evaluation_id"),
        "payout_odds_evaluation_id": (_dict(evidence.get("payout"))).get("evaluation_id"),
        "exit_hold_evaluation_id": (_dict(evidence.get("exit_hold"))).get("evaluation_id"),
        "orderbook_snapshot_id": (_dict(evidence.get("orderbook"))).get("orderbook_snapshot_id") or (_dict(evidence.get("orderbook"))).get("id"),
        "news_source_id": (_dict(evidence.get("news"))).get("impact_id") or (_dict(evidence.get("news"))).get("id"),
        "whale_source_id": (_dict(evidence.get("whale"))).get("whale_event_id") or (_dict(evidence.get("whale"))).get("id"),
        "market_movement_source_id": (_dict(evidence.get("market_movement"))).get("id"),
    }


def _resolution_hours(exit_hold: dict[str, Any]) -> Decimal | None:
    seconds = _int_or_none(exit_hold.get("time_to_resolution_seconds"))
    return Decimal(seconds) / Decimal(3600) if seconds is not None else None


def _fresh(row: dict[str, Any], key: str, *, ttl_seconds: int) -> bool:
    value = row.get(key)
    if not hasattr(value, "tzinfo"):
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (datetime.now(UTC) - value).total_seconds() <= ttl_seconds


def _thesis_id(record: dict[str, Any], evidence: dict[str, Any], thesis_type: str, status: str) -> str:
    refs = _source_refs(evidence)
    raw = "|".join(
        [
            str(record["subject_type"]),
            str(record["subject_id"]),
            str(refs.get("risk_evidence_id") or ""),
            str(refs.get("payout_odds_evaluation_id") or ""),
            str(refs.get("exit_hold_evaluation_id") or ""),
            thesis_type,
            status,
        ]
    )
    return f"trade_thesis_{uuid5(NAMESPACE_URL, raw).hex}"


def _subject_aliases(subject_id: str) -> list[str]:
    raw = str(subject_id)
    aliases = [raw]
    prefix = "eligibility_exit_candidate_"
    while raw.startswith(prefix):
        raw = raw[len(prefix) :]
        if raw not in aliases:
            aliases.append(raw)
    return aliases


def _upsert(conn: Any, thesis: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO trade_thesis_evaluations (
            thesis_id, subject_type, subject_id, candidate_id, market_id, condition_id, side, token_id,
            source_refresh_cycle_id, edge_thesis_id, risk_evidence_id, trade_thesis_type, exit_intent,
            entry_reason, primary_catalyst, supporting_sources_json, opposing_sources_json, entry_price,
            target_exit_price, stop_or_invalidation_price, expected_hold_time_hours, max_hold_time_hours,
            hold_time_source, expected_price_move, expected_reward, reward_source, exit_trigger,
            invalidation_condition, time_stop_condition, thesis_confidence, exit_confidence, ai_review_state,
            ai_thesis, ai_counter_thesis, status, blocker_code, required_to_pass_json, source_refs_json, metadata_json
        ) VALUES (
            %(thesis_id)s,%(subject_type)s,%(subject_id)s,%(candidate_id)s,%(market_id)s,%(condition_id)s,%(side)s,%(token_id)s,
            %(source_refresh_cycle_id)s,%(edge_thesis_id)s,%(risk_evidence_id)s,%(trade_thesis_type)s,%(exit_intent)s,
            %(entry_reason)s,%(primary_catalyst)s,%(supporting_sources_json)s,%(opposing_sources_json)s,%(entry_price)s,
            %(target_exit_price)s,%(stop_or_invalidation_price)s,%(expected_hold_time_hours)s,%(max_hold_time_hours)s,
            %(hold_time_source)s,%(expected_price_move)s,%(expected_reward)s,%(reward_source)s,%(exit_trigger)s,
            %(invalidation_condition)s,%(time_stop_condition)s,%(thesis_confidence)s,%(exit_confidence)s,%(ai_review_state)s,
            %(ai_thesis)s,%(ai_counter_thesis)s,%(status)s,%(blocker_code)s,%(required_to_pass_json)s,%(source_refs_json)s,%(metadata_json)s
        )
        ON CONFLICT (thesis_id) DO UPDATE SET updated_at=now()
        """,
        {
            **thesis,
            "supporting_sources_json": Jsonb(_json_safe(thesis["supporting_sources_json"])),
            "opposing_sources_json": Jsonb(_json_safe(thesis["opposing_sources_json"])),
            "required_to_pass_json": Jsonb(_json_safe(thesis["required_to_pass_json"])),
            "source_refs_json": Jsonb(_json_safe(thesis["source_refs_json"])),
            "metadata_json": Jsonb(_json_safe(thesis["metadata_json"])),
        },
    )


def _latest_rows(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    return _fetchall(
        conn,
        """
        SELECT thesis_id, subject_type, subject_id, candidate_id, market_id, side, token_id,
               trade_thesis_type, exit_intent, status, blocker_code, expected_hold_time_hours,
               target_exit_price, thesis_confidence, exit_confidence, ai_review_state,
               source_refresh_cycle_id, edge_thesis_id, risk_evidence_id, created_at
        FROM trade_thesis_evaluations
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    )


def _empty_dashboard(status: str, generated_at: str) -> dict[str, Any]:
    return {"mock_data": False, "status": status, "generated_at": generated_at, "total_evaluations": 0, "latest_evaluations": []}


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _has_column(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    return int(value or 0)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
