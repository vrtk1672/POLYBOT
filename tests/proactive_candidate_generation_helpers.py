from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from targeted_revalidation_helpers import artifact_counts, insert_event_link, insert_fresh_orderbook, insert_market, setup_revalidation_tables


def setup_proactive_seed_source(
    market_id: str,
    *,
    direction: str = "YES",
    token_side_state: str = "SIDE_DIRECTIONAL_YES",
    token_state: str = "TOKENS_VERIFIED",
    identity_state: str = "VERIFIED",
    market_status: str = "ACTIVE",
    stale_orderbook: bool = False,
    already_priced_in: str = "UNKNOWN",
) -> dict[str, object]:
    setup_revalidation_tables()
    insert_market(market_id, token_state=token_state, identity_state=identity_state, status=market_status)
    insert_event_link(
        f"event-{market_id}",
        market_id,
        link_type="DIRECT_LINK",
        confidence=0.92,
        token_side_state=token_side_state,
        direction=direction,
    )
    if not stale_orderbook:
        side = "NO" if direction == "NO" else "YES"
        insert_fresh_orderbook(market_id, side=side)
    else:
        insert_fresh_orderbook(market_id, side="YES", stale=True)
    TargetedMarketRevalidationService().refresh(force=True, limit=10, skipped_sample_limit=0)
    if already_priced_in != "UNKNOWN":
        with DatabaseConnectionFactory().connect() as conn, conn.transaction():
            conn.execute(
                "UPDATE targeted_market_revalidations SET already_priced_in_state=%s WHERE market_id=%s",
                (already_priced_in, market_id),
            )
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM targeted_market_revalidations WHERE market_id=%s ORDER BY id DESC LIMIT 1", (market_id,)).fetchone()
        return dict(row)


def seed_artifact_counts() -> dict[str, int]:
    return artifact_counts()
