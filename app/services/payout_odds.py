from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
SUBJECT_TYPES = {"FRESH_SEED", "PAPER_CANDIDATE", "PAPER_INTENT", "PAPER_POSITION", "PAPER_CLOSE"}
DEFAULT_STAKE = Decimal("100")


@dataclass(frozen=True)
class PayoutOddsMath:
    price: Decimal
    stake_usd: Decimal
    quantity: Decimal
    shares_if_buy: Decimal
    payout_if_win: Decimal
    profit_if_win: Decimal
    max_loss: Decimal
    risk_reward: Decimal
    implied_probability: Decimal
    break_even_probability: Decimal

    def to_row(self) -> dict[str, Decimal]:
        return {
            "price": self.price,
            "stake_usd": self.stake_usd,
            "quantity": self.quantity,
            "shares_if_buy": self.shares_if_buy,
            "payout_if_win": self.payout_if_win,
            "profit_if_win": self.profit_if_win,
            "max_loss": self.max_loss,
            "risk_reward": self.risk_reward,
            "implied_probability": self.implied_probability,
            "break_even_probability": self.break_even_probability,
        }


class PayoutOddsService:
    """Derived payout, odds, and hold-to-resolution value truth.

    This service never creates intents, orders, fills, positions, or capital
    movements. It writes only payout/odds evaluation rows with source links.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def compute_candidate_math(self, *, price: Decimal, stake_usd: Decimal | None = None) -> PayoutOddsMath:
        p = _valid_price(price)
        stake = _decimal(stake_usd if stake_usd is not None else self._default_stake())
        if stake <= 0:
            raise ValueError("INVALID_STAKE")
        shares = stake / p
        payout = shares
        profit = payout - stake
        return PayoutOddsMath(
            price=p,
            stake_usd=stake,
            quantity=shares,
            shares_if_buy=shares,
            payout_if_win=payout,
            profit_if_win=profit,
            max_loss=stake,
            risk_reward=profit / stake,
            implied_probability=p,
            break_even_probability=p,
        )

    def compute_position_math(self, *, entry_price: Decimal, quantity: Decimal) -> PayoutOddsMath:
        p = _valid_price(entry_price)
        qty = _decimal(quantity)
        if qty <= 0:
            raise ValueError("INVALID_QUANTITY")
        cost = p * qty
        payout = qty
        profit = payout - cost
        return PayoutOddsMath(
            price=p,
            stake_usd=cost,
            quantity=qty,
            shares_if_buy=qty,
            payout_if_win=payout,
            profit_if_win=profit,
            max_loss=cost,
            risk_reward=profit / cost if cost > 0 else Decimal("0"),
            implied_probability=p,
            break_even_probability=p,
        )

    def evaluate_recent(self, *, limit: int = 100, subject_type: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        subject = str(subject_type).upper() if subject_type else None
        if subject and subject not in SUBJECT_TYPES:
            return {"mock_data": False, "status": "INVALID_SUBJECT_TYPE", "generated_at": generated_at, "evaluations_created": 0}
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "generated_at": generated_at, "evaluations_created": 0}
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "generated_at": generated_at, "evaluations_created": 0}
            safety_before = _safety_counts(conn)
            before = _count_table(conn, "payout_odds_evaluations")
            records = self._candidate_records(conn, limit=limit, subject_type=subject)
            outcomes = [self._evaluate_record(conn, record, dry_run=dry_run) for record in records]
            after = _count_table(conn, "payout_odds_evaluations")
            safety_after = _safety_counts(conn)
        counts = Counter(item["status"] for item in outcomes)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "subjects_checked": len(records),
                "evaluations_created": 0 if dry_run else max(0, after - before),
                "outcomes_by_status": dict(counts),
                "latest_outcomes": outcomes[:20],
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": _trading_mutation(safety_before, safety_after),
            }
        )

    def evaluate_subject_with_conn(self, conn: Any, *, subject_type: str, subject_id: str, dry_run: bool = False) -> dict[str, Any]:
        if not _tables_ready(conn):
            return {"status": "MISSING_TABLES", "subject_type": subject_type, "subject_id": subject_id}
        record = self._record_by_subject(conn, subject_type=subject_type, subject_id=subject_id)
        if record is None:
            return {"status": "SUBJECT_NOT_FOUND", "subject_type": subject_type, "subject_id": subject_id}
        return self._evaluate_record(conn, record, dry_run=dry_run)

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty_dashboard("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "payout_odds_evaluations"):
                return _empty_dashboard("MISSING_TABLES", generated_at)
            totals = _fetchone(
                conn,
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE settlement_value_status = 'MISSING_PRICE') AS missing_price_count,
                    COALESCE(AVG(risk_reward) FILTER (WHERE risk_reward IS NOT NULL), 0) AS avg_risk_reward,
                    COUNT(*) FILTER (WHERE price >= 0.75 AND risk_reward < 0.5) AS high_price_low_reward_count,
                    COUNT(*) FILTER (WHERE price <= 0.25 AND risk_reward >= 3) AS low_price_high_reward_count
                FROM payout_odds_evaluations
                """,
            ) or {}
            by_type = _fetchall(
                conn,
                """
                SELECT subject_type, COUNT(*) AS count
                FROM payout_odds_evaluations
                GROUP BY subject_type
                ORDER BY subject_type
                """,
            )
            latest_candidates = _latest_rows(conn, "subject_type IN ('FRESH_SEED','PAPER_CANDIDATE','PAPER_INTENT')", limit)
            latest_positions = _latest_rows(conn, "subject_type IN ('PAPER_POSITION','PAPER_CLOSE')", limit)
            top_reward = _fetchall(
                conn,
                """
                SELECT evaluation_id, subject_type, subject_id, market_id, side, price,
                       price_source, stake_usd, shares_if_buy, payout_if_win,
                       profit_if_win, max_loss, risk_reward, implied_probability,
                       break_even_probability, settlement_value_status, created_at
                FROM payout_odds_evaluations
                WHERE risk_reward IS NOT NULL
                  AND subject_type IN ('FRESH_SEED','PAPER_CANDIDATE','PAPER_INTENT')
                ORDER BY risk_reward DESC, created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_evaluations": _int(totals.get("total")),
                "evaluations_by_subject_type": {str(row["subject_type"]): _int(row["count"]) for row in by_type},
                "latest_candidate_evaluations": latest_candidates,
                "latest_position_evaluations": latest_positions,
                "missing_price_count": _int(totals.get("missing_price_count")),
                "avg_risk_reward": _float(totals.get("avg_risk_reward")),
                "top_reward_candidates": top_reward,
                "high_price_low_reward_count": _int(totals.get("high_price_low_reward_count")),
                "low_price_high_reward_count": _int(totals.get("low_price_high_reward_count")),
            }
        )

    def detail(self, evaluation_id: str) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evaluation_id": evaluation_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "payout_odds_evaluations"):
                return {"mock_data": False, "status": "MISSING_TABLES", "evaluation_id": evaluation_id}
            evaluation = _fetchone(conn, "SELECT * FROM payout_odds_evaluations WHERE evaluation_id = %s", (evaluation_id,))
            if evaluation is None:
                return {"mock_data": False, "status": "NOT_FOUND", "evaluation_id": evaluation_id}
            sources = _fetchall(conn, "SELECT * FROM payout_odds_sources WHERE evaluation_id = %s ORDER BY linked_at ASC, id ASC", (evaluation_id,))
            related = self._related_subject(conn, evaluation)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "evaluation": evaluation,
                "sources": sources,
                "related_subject": related,
                "forensics_link": _forensics_link(evaluation),
            }
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "payout_odds_evaluations"):
            return None
        row = _fetchone(
            conn,
            """
            SELECT *
            FROM payout_odds_evaluations
            WHERE subject_type = %s AND subject_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (subject_type, subject_id),
        )
        return row

    def observational_summary_for_market(self, conn: Any, *, market_id: str | None = None, position_id: str | None = None, limit: int = 5) -> dict[str, Any]:
        if not _table_exists(conn, "payout_odds_evaluations"):
            return {"status": "MISSING_TABLES", "latest_evaluations": []}
        clauses: list[str] = []
        params: list[Any] = []
        if market_id:
            clauses.append("market_id = %s")
            params.append(str(market_id))
        if position_id:
            clauses.append("(subject_type = 'PAPER_POSITION' AND subject_id = %s)")
            params.append(str(position_id))
        where = " OR ".join(clauses) if clauses else "TRUE"
        params.append(limit)
        rows = _fetchall(
            conn,
            f"""
            SELECT evaluation_id, subject_type, subject_id, market_id, side, price,
                   stake_usd, payout_if_win, profit_if_win, max_loss, risk_reward,
                   implied_probability, settlement_value_status, created_at
            FROM payout_odds_evaluations
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return _json_safe({"status": "OK", "latest_evaluations": rows, "observational_only": True})

    def _candidate_records(self, conn: Any, *, limit: int, subject_type: str | None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        wanted = [subject_type] if subject_type else ["FRESH_SEED", "PAPER_CANDIDATE", "PAPER_INTENT", "PAPER_POSITION", "PAPER_CLOSE"]
        if "FRESH_SEED" in wanted:
            records.extend(_fresh_seed_records(conn, limit=limit))
        if "PAPER_CANDIDATE" in wanted:
            records.extend(_paper_candidate_records(conn, limit=limit))
        if "PAPER_INTENT" in wanted:
            records.extend(_paper_intent_records(conn, limit=limit))
        if "PAPER_POSITION" in wanted:
            records.extend(_paper_position_records(conn, limit=limit))
        if "PAPER_CLOSE" in wanted:
            records.extend(_paper_close_records(conn, limit=limit))
        return records[: max(1, limit) * len(wanted)]

    def _record_by_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        subject = subject_type.upper()
        if subject == "FRESH_SEED":
            rows = _fresh_seed_records(conn, limit=1000, subject_id=subject_id)
        elif subject == "PAPER_CANDIDATE":
            rows = _paper_candidate_records(conn, limit=1000, subject_id=subject_id)
        elif subject == "PAPER_INTENT":
            rows = _paper_intent_records(conn, limit=1000, subject_id=subject_id)
        elif subject == "PAPER_POSITION":
            rows = _paper_position_records(conn, limit=1000, subject_id=subject_id)
        elif subject == "PAPER_CLOSE":
            rows = _paper_close_records(conn, limit=1000, subject_id=subject_id)
        else:
            rows = []
        return rows[0] if rows else None

    def _evaluate_record(self, conn: Any, record: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        status = "OK"
        try:
            if record["subject_type"] in {"PAPER_POSITION", "PAPER_CLOSE"}:
                math = self.compute_position_math(entry_price=record["price"], quantity=record["quantity"])
            else:
                math = self.compute_candidate_math(price=record["price"], stake_usd=record.get("stake_usd"))
            row = {**math.to_row(), "settlement_value_status": record.get("settlement_value_status") or "OK"}
        except MissingPriceError:
            row = _null_math("MISSING_PRICE")
            status = "MISSING_PRICE"
        except ValueError as exc:
            row = _null_math(str(exc))
            status = str(exc)

        evaluation_id = _evaluation_id(record, status=status)
        evaluation = {
            "evaluation_id": evaluation_id,
            "subject_type": record["subject_type"],
            "subject_id": record["subject_id"],
            "market_id": record.get("market_id"),
            "condition_id": record.get("condition_id"),
            "side": record.get("side"),
            "token_id": record.get("token_id"),
            "price_source": record.get("price_source"),
            "fair_probability": None,
            "expected_value": None,
            "source_refs_json": record.get("source_refs") or {},
            "metadata_json": {
                **(record.get("metadata") or {}),
                "fair_probability_policy": "NULL_UNLESS_SOURCE_BACKED",
                "expected_value_policy": "NULL_UNLESS_FAIR_PROBABILITY_EXISTS",
                "observational_only": True,
            },
            **row,
        }
        sources = record.get("sources") or []
        if not dry_run:
            self._upsert_evaluation(conn, evaluation, sources)
        return _json_safe(
            {
                "status": status,
                "evaluation_id": evaluation_id,
                "subject_type": record["subject_type"],
                "subject_id": record["subject_id"],
                "market_id": record.get("market_id"),
                "side": record.get("side"),
                "price": evaluation.get("price"),
                "stake_usd": evaluation.get("stake_usd"),
                "payout_if_win": evaluation.get("payout_if_win"),
                "profit_if_win": evaluation.get("profit_if_win"),
                "risk_reward": evaluation.get("risk_reward"),
                "dry_run": dry_run,
            }
        )

    def _upsert_evaluation(self, conn: Any, evaluation: dict[str, Any], sources: list[dict[str, Any]]) -> None:
        conn.execute(
            """
            INSERT INTO payout_odds_evaluations (
                evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
                price, price_source, stake_usd, quantity, shares_if_buy, payout_if_win,
                profit_if_win, max_loss, risk_reward, implied_probability,
                break_even_probability, fair_probability, expected_value,
                settlement_value_status, source_refs_json, metadata_json
            )
            VALUES (
                %(evaluation_id)s, %(subject_type)s, %(subject_id)s, %(market_id)s, %(condition_id)s, %(side)s, %(token_id)s,
                %(price)s, %(price_source)s, %(stake_usd)s, %(quantity)s, %(shares_if_buy)s, %(payout_if_win)s,
                %(profit_if_win)s, %(max_loss)s, %(risk_reward)s, %(implied_probability)s,
                %(break_even_probability)s, %(fair_probability)s, %(expected_value)s,
                %(settlement_value_status)s, %(source_refs_json)s, %(metadata_json)s
            )
            ON CONFLICT (evaluation_id) DO UPDATE SET
                source_refs_json = EXCLUDED.source_refs_json,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = now()
            """,
            {**evaluation, "source_refs_json": Jsonb(_json_safe(evaluation["source_refs_json"])), "metadata_json": Jsonb(_json_safe(evaluation["metadata_json"]))},
        )
        for source in sources:
            conn.execute(
                """
                INSERT INTO payout_odds_sources (
                    evaluation_id, source_table, source_record_id, source_type, contribution_summary
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (evaluation_id, source_table, source_record_id, source_type) DO NOTHING
                """,
                (
                    evaluation["evaluation_id"],
                    source["source_table"],
                    str(source["source_record_id"]),
                    source["source_type"],
                    source["contribution_summary"],
                ),
            )

    def _related_subject(self, conn: Any, evaluation: dict[str, Any]) -> dict[str, Any] | None:
        table_map = {
            "FRESH_SEED": ("fresh_candidate_seeds", "seed_id"),
            "PAPER_CANDIDATE": ("paper_eligibility_candidates", "eligibility_id"),
            "PAPER_INTENT": ("paper_intents", "paper_intent_id"),
            "PAPER_POSITION": ("paper_positions", "id::text"),
            "PAPER_CLOSE": ("paper_position_closes", "close_id"),
        }
        table, column = table_map.get(str(evaluation.get("subject_type")), (None, None))
        if not table or not _table_exists(conn, table):
            return None
        return _fetchone(conn, f"SELECT * FROM {table} WHERE {column} = %s LIMIT 1", (str(evaluation["subject_id"]),))

    def _default_stake(self) -> Decimal:
        return _decimal(os.getenv("PAYOUT_EVAL_DEFAULT_STAKE_USD") or DEFAULT_STAKE)


class MissingPriceError(ValueError):
    pass


def _fresh_seed_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fresh_candidate_seeds"):
        return []
    where = "WHERE fcs.seed_id = %s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(
        conn,
        f"""
        SELECT fcs.*, obs.best_ask, obs.best_bid, obs.mid_price, obs.token_id AS orderbook_token_id,
               obs.snapshot_status, obs.is_stale
        FROM fresh_candidate_seeds fcs
        LEFT JOIN orderbook_snapshots obs ON obs.id = fcs.orderbook_snapshot_id
        {where}
        ORDER BY fcs.updated_at DESC, fcs.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [_source_record("FRESH_SEED", str(row["seed_id"]), row, source_table="fresh_candidate_seeds") for row in rows]


def _paper_candidate_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    where = "WHERE pec.eligibility_id = %s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(
        conn,
        f"""
        SELECT pec.*, obs.best_ask, obs.best_bid, obs.mid_price, obs.token_id AS orderbook_token_id,
               obs.snapshot_status, obs.is_stale
        FROM paper_eligibility_candidates pec
        LEFT JOIN orderbook_snapshots obs ON obs.id = pec.orderbook_snapshot_id
        {where}
        ORDER BY pec.updated_at DESC, pec.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [_source_record("PAPER_CANDIDATE", str(row["eligibility_id"]), row, source_table="paper_eligibility_candidates") for row in rows]


def _paper_intent_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_intents"):
        return []
    where = "WHERE pi.paper_intent_id = %s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(
        conn,
        f"""
        SELECT pi.*, obs.best_ask, obs.best_bid, obs.mid_price, obs.token_id AS orderbook_token_id,
               obs.snapshot_status, obs.is_stale
        FROM paper_intents pi
        LEFT JOIN orderbook_snapshots obs ON obs.id = pi.orderbook_snapshot_id
        {where}
        ORDER BY pi.created_at DESC, pi.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [_source_record("PAPER_INTENT", str(row["paper_intent_id"]), row, source_table="paper_intents") for row in rows]


def _paper_position_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    where = "WHERE pp.id::text = %s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(
        conn,
        f"""
        SELECT pp.*, obs.best_bid AS current_best_bid, obs.id AS current_orderbook_snapshot_id
        FROM paper_positions pp
        LEFT JOIN LATERAL (
            SELECT id, best_bid
            FROM orderbook_snapshots
            WHERE market_id = pp.market_id
              AND side = pp.intended_outcome
              AND COALESCE(is_stale, false) = false
            ORDER BY snapshot_at DESC NULLS LAST, collected_at DESC NULLS LAST, id DESC
            LIMIT 1
        ) obs ON true
        {where}
        ORDER BY pp.opened_at DESC NULLS LAST, pp.updated_at DESC NULLS LAST
        LIMIT %s
        """,
        tuple(params),
    )
    return [_position_record(row) for row in rows]


def _paper_close_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_position_closes"):
        return []
    where = "WHERE pc.close_id = %s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(
        conn,
        f"""
        SELECT *
        FROM paper_position_closes pc
        {where}
        ORDER BY pc.created_at DESC, pc.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [_close_record(row) for row in rows]


def _source_record(subject_type: str, subject_id: str, row: dict[str, Any], *, source_table: str) -> dict[str, Any]:
    evidence = _dict(row.get("evidence"))
    source_evidence = _dict(evidence.get("source_evidence"))
    price, price_source = _best_candidate_price(row, evidence, source_evidence)
    stake = _decimal_or_none(evidence.get("intended_notional") or evidence.get("notional"))
    quantity = _decimal_or_none(evidence.get("quantity") or evidence.get("size") or evidence.get("intended_size"))
    if stake is None and price is not None and quantity is not None:
        stake = price * quantity
    source_id_field = "id"
    if subject_type == "FRESH_SEED":
        source_id_field = "seed_id"
    elif subject_type == "PAPER_CANDIDATE":
        source_id_field = "eligibility_id"
    elif subject_type == "PAPER_INTENT":
        source_id_field = "paper_intent_id"
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "market_id": row.get("market_id"),
        "condition_id": row.get("condition_id"),
        "side": row.get("side"),
        "token_id": row.get("expected_token_id") or row.get("orderbook_token_id"),
        "price": price,
        "price_source": price_source,
        "stake_usd": stake,
        "settlement_value_status": "OK" if price is not None else "MISSING_PRICE",
        "source_refs": {
            "source_table": source_table,
            "source_record_id": str(row.get(source_id_field) or row.get("id")),
            "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
            "price_source": price_source,
        },
        "sources": [
            {
                "source_table": source_table,
                "source_record_id": str(row.get(source_id_field) or row.get("id")),
                "source_type": subject_type,
                "contribution_summary": f"{subject_type} source for payout/odds evaluation",
            }
        ],
        "metadata": {
            "quantity_source": "source_evidence" if quantity is not None else "evaluation_default",
            "current_best_bid": row.get("best_bid"),
            "current_mid_price": row.get("mid_price"),
        },
    }


def _position_record(row: dict[str, Any]) -> dict[str, Any]:
    entry = _decimal_or_none(row.get("avg_entry"))
    quantity = _decimal_or_none(row.get("size"))
    status = "OK" if entry is not None else "MISSING_PRICE"
    metadata = {"current_exit_value": None, "current_exit_price_status": "EXIT_PRICE_UNAVAILABLE"}
    bid = _decimal_or_none(row.get("current_best_bid"))
    if bid is not None and quantity is not None:
        metadata = {
            "current_exit_value": bid * quantity,
            "current_exit_price": bid,
            "current_exit_price_status": "OK",
            "current_orderbook_snapshot_id": row.get("current_orderbook_snapshot_id"),
        }
    return {
        "subject_type": "PAPER_POSITION",
        "subject_id": str(row["id"]),
        "market_id": row.get("market_id"),
        "side": row.get("intended_outcome"),
        "price": entry,
        "price_source": "paper_positions.avg_entry",
        "quantity": quantity,
        "settlement_value_status": status if metadata["current_exit_price_status"] == "OK" else "EXIT_PRICE_UNAVAILABLE",
        "source_refs": {"source_table": "paper_positions", "source_record_id": str(row["id"])},
        "sources": [{"source_table": "paper_positions", "source_record_id": str(row["id"]), "source_type": "PAPER_POSITION", "contribution_summary": "position entry price and quantity"}],
        "metadata": metadata,
    }


def _close_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject_type": "PAPER_CLOSE",
        "subject_id": str(row["close_id"]),
        "market_id": row.get("market_id"),
        "side": row.get("side"),
        "price": _decimal_or_none(row.get("entry_price")),
        "price_source": "paper_position_closes.entry_price",
        "quantity": _decimal_or_none(row.get("quantity")),
        "settlement_value_status": "CLOSED",
        "source_refs": {"source_table": "paper_position_closes", "source_record_id": str(row["close_id"])},
        "sources": [{"source_table": "paper_position_closes", "source_record_id": str(row["close_id"]), "source_type": "PAPER_CLOSE", "contribution_summary": "closed position entry price and quantity"}],
        "metadata": {"exit_price": row.get("exit_price"), "realized_pnl": row.get("realized_pnl")},
    }


def _best_candidate_price(row: dict[str, Any], evidence: dict[str, Any], source_evidence: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    candidates = [
        (row.get("intended_price"), "paper_intents.intended_price"),
        (evidence.get("orderbook_best_ask"), "evidence.orderbook_best_ask"),
        (source_evidence.get("orderbook_best_ask"), "evidence.source_evidence.orderbook_best_ask"),
        (row.get("best_ask"), "orderbook_snapshots.best_ask"),
        (_dict(row.get("metadata_json")).get("verified_price"), "fresh_candidate_seeds.metadata_json.verified_price"),
        (evidence.get("orderbook_mid_price"), "evidence.orderbook_mid_price"),
        (row.get("mid_price"), "orderbook_snapshots.mid_price"),
    ]
    for value, source in candidates:
        price = _decimal_or_none(value)
        if price is not None:
            return price, source
    return None, None


def _null_math(status: str) -> dict[str, Any]:
    return {
        "price": None,
        "stake_usd": None,
        "quantity": None,
        "shares_if_buy": None,
        "payout_if_win": None,
        "profit_if_win": None,
        "max_loss": None,
        "risk_reward": None,
        "implied_probability": None,
        "break_even_probability": None,
        "settlement_value_status": status,
    }


def _valid_price(value: Any) -> Decimal:
    if value is None:
        raise MissingPriceError("MISSING_PRICE")
    price = _decimal(value)
    if price <= 0 or price >= 1:
        raise ValueError("INVALID_PRICE")
    return price


def _evaluation_id(record: dict[str, Any], *, status: str) -> str:
    raw = "|".join(
        [
            str(record.get("subject_type")),
            str(record.get("subject_id")),
            str(record.get("price_source")),
            str(record.get("price")),
            str(record.get("quantity")),
            status,
        ]
    )
    return f"payout_odds_{uuid5(NAMESPACE_URL, raw).hex}"


def _forensics_link(evaluation: dict[str, Any]) -> str | None:
    if evaluation.get("subject_type") == "PAPER_POSITION":
        return f"/dashboard/api/v2/paper/trade-forensics/{evaluation.get('subject_id')}"
    return None


def _latest_rows(conn: Any, where: str, limit: int) -> list[dict[str, Any]]:
    return _fetchall(
        conn,
        f"""
        SELECT evaluation_id, subject_type, subject_id, market_id, side, price,
               price_source, stake_usd, quantity, shares_if_buy, payout_if_win,
               profit_if_win, max_loss, risk_reward, implied_probability,
               break_even_probability, settlement_value_status, created_at
        FROM payout_odds_evaluations
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (limit,),
    )


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "payout_odds_evaluations") and _table_exists(conn, "payout_odds_sources")


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()
    return bool(row and row["table_name"])


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return _int(row["count"] if row else 0)


def _safety_counts(conn: Any) -> dict[str, Any]:
    counts = {
        "paper_intents": _count_table(conn, "paper_intents"),
        "paper_orders": _count_table(conn, "paper_orders"),
        "paper_fills": _count_table(conn, "paper_fills"),
        "paper_positions": _count_table(conn, "paper_positions"),
        "paper_position_closes": _count_table(conn, "paper_position_closes"),
        "paper_capital_ledger": _count_table(conn, "paper_capital_ledger"),
        "live_orders": _count_table(conn, "live_orders"),
        "orders_v2": _count_table(conn, "orders_v2"),
        "fills_v2": _count_table(conn, "fills_v2"),
        "positions": _count_table(conn, "positions"),
    }
    account = _fetchone(conn, "SELECT current_balance, available_balance, locked_balance, open_exposure, realized_pnl, unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'") if _table_exists(conn, "paper_accounts") else None
    if account:
        counts["capital_balances"] = account
    return _json_safe(counts)


def _trading_mutation(before: dict[str, Any], after: dict[str, Any]) -> bool:
    keys = ["paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions", "capital_balances"]
    return any(before.get(key) != after.get(key) for key in keys)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _empty_dashboard(status: str, generated_at: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "generated_at": generated_at,
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "total_evaluations": 0,
        "evaluations_by_subject_type": {},
        "latest_candidate_evaluations": [],
        "latest_position_evaluations": [],
        "missing_price_count": 0,
        "avg_risk_reward": 0.0,
        "top_reward_candidates": [],
        "high_price_low_reward_count": 0,
        "low_price_high_reward_count": 0,
    }
