from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.news_neuron.contracts import NewsDirection, NewsMarketLink
from app.repositories.news_market_link_repository import NewsMarketLinkRepository
from app.services.full_mesh_contract import identity_from_bundle, validate_mesh_response
from app.services.full_mesh_registry import registry_by_name
from app.services.source_organ_runtime import query_source_organ_with_connection


def _identity(market_id: str = "market-news-updated-at") -> dict[str, object]:
    return identity_from_bundle(
        {
            "candidate_id": "candidate-news-updated-at",
            "market_id": market_id,
            "condition_id": "condition-news-updated-at",
            "side": "YES",
            "token_id": "token-yes",
            "correlation_id": "corr-news-updated-at",
            "event_id": "event-news-updated-at",
        }
    )


def test_news_market_links_migration_adds_updated_at_with_default(postgres_test_schema) -> None:
    run_migrations()

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        column = conn.execute(
            """
            SELECT column_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'news_market_links'
              AND column_name = 'updated_at'
            """
        ).fetchone()
        assert column is not None
        assert column["is_nullable"] == "NO"
        assert "now()" in str(column["column_default"]).lower()

        inserted = conn.execute(
            """
            INSERT INTO news_market_links (
                link_id, news_event_id, market_id, link_score, direction, confidence
            )
            VALUES ('link-default-updated-at', 'news-default-updated-at', 'market-default-updated-at', 0.71, 'YES', 0.82)
            RETURNING created_at, updated_at
            """
        ).fetchone()
        assert inserted["updated_at"] is not None
        assert inserted["updated_at"] >= inserted["created_at"] - timedelta(seconds=1)


def test_news_market_link_repository_refreshes_updated_at_on_upsert(postgres_test_schema) -> None:
    run_migrations()
    repository = NewsMarketLinkRepository()
    link = NewsMarketLink(
        link_id="link-refresh-updated-at",
        news_event_id="news-refresh-updated-at",
        market_id="market-refresh-updated-at",
        link_score=0.41,
        direction=NewsDirection.UNKNOWN,
        confidence=0.35,
        link_reason="initial weak link",
    )

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        first = repository.insert_link(conn, link)
        old_updated_at = datetime.now(UTC) - timedelta(hours=2)
        conn.execute(
            "UPDATE news_market_links SET updated_at = %s WHERE link_id = %s",
            (old_updated_at, link.link_id),
        )

        refreshed = repository.insert_link(
            conn,
            link.model_copy(
                update={
                    "link_score": 0.88,
                    "direction": NewsDirection.YES,
                    "confidence": 0.91,
                    "link_reason": "refreshed directional link",
                }
            ),
        )

    assert first["link_id"] == refreshed["link_id"]
    assert refreshed["updated_at"] > old_updated_at
    assert float(refreshed["link_score"]) == 0.88
    assert refreshed["direction"] == "YES"
    assert float(refreshed["confidence"]) == 0.91
    assert refreshed["link_reason"] == "refreshed directional link"


def test_news_source_organ_fallback_orders_links_by_updated_at(postgres_test_schema) -> None:
    run_migrations()
    market_id = "market-news-fallback-updated-at"
    older = datetime.now(UTC) - timedelta(hours=2)
    newer = datetime.now(UTC) - timedelta(minutes=5)

    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO news_market_links (
                link_id, news_event_id, market_id, link_score, link_reason,
                direction, confidence, created_at, updated_at
            )
            VALUES
                ('link-stale-updated-at', 'news-stale-updated-at', %s, 0.95, 'older but stronger stale link',
                 'NO', 0.95, %s, %s),
                ('link-fresh-updated-at', 'news-fresh-updated-at', %s, 0.70, 'newer refreshed link',
                 'YES', 0.86, %s, %s)
            """,
            (market_id, older, older, market_id, older, newer),
        )

        response = query_source_organ_with_connection(
            registry_by_name()["news"],
            identity=_identity(market_id),
            conn=conn,
        )

    validate_mesh_response(response)
    assert response["response_state"] == "SUPPORTED"
    assert response["supports_side"] == "YES"
    assert response["source_records"][0]["source_type"] == "news_market_links"
    assert response["source_records"][0]["source_record_id"] == "link-fresh-updated-at"
