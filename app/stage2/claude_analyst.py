"""
app/stage2/claude_analyst.py — Claude market analyst.

Sends all top-N markets to claude-opus-4-6 in a single batched call.
Returns a list of MarketRecommendation objects with:
  - confidence (0.0-1.0)
  - action     (BUY_YES | BUY_NO | SKIP)
  - reason     (≤ 120 chars)

Uses:
  - Prompt caching on the stable system prompt (~1.25x write, ~0.1x read on repeats)
  - Adaptive thinking with effort=medium (quality + cost balance)
  - Manual JSON parsing (compatible with thinking blocks in response)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from pydantic import BaseModel

from app.models.score import ScoredMarket
from gamma_crawler import edge_cents, hours_remaining, liquidity_bucket

LOGS_DIR = Path("logs")
AI_LOG_FILE = LOGS_DIR / "ai_recommendations.jsonl"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable system prompt — cached after first call (~0.1x cost on subsequent)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an expert Polymarket prediction market analyst. You combine:
- Deep knowledge of sports, politics, finance, and world events
- Understanding of prediction market pricing and market efficiency
- Risk-adjusted trading logic: only recommend when there is clear evidence of mispricing

For each market you receive:
- question: what is being predicted
- yes_price / no_price: current market prices (0.0 = 0%, 1.0 = 100% probability)
- hours_to_close: time until market resolves
- volume_24h_usd: recent liquidity signal
- edge_cents: profit in cents per $1 of shares if cheap side wins
- opportunity_score: 0-100 composite signal from our quantitative model
- score_breakdown: components of the quantitative score

Your job: determine if the market is MISPRICED relative to true probability.

Rules:
1. Only recommend BUY_YES or BUY_NO when you have high confidence the price is wrong
2. SKIP when evidence is ambiguous, price seems fair, or you lack domain knowledge
3. confidence = your probability that the recommended action is correct (0.0-1.0)
4. Be calibrated: 0.9 means you are very sure, 0.6 means slight edge

Return ONLY a JSON object. No explanation outside the JSON. No markdown. No preamble.
"""


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class MarketRecommendation(BaseModel):
    rank: int
    question: str
    confidence: float   # 0.0–1.0
    action: str         # BUY_YES | BUY_NO | SKIP
    reason: str         # ≤ 120 chars
    yes_price: float | None
    no_price: float | None
    score: float
    computed_at: str


# ---------------------------------------------------------------------------
# Main analyst function
# ---------------------------------------------------------------------------

def _build_market_payload(markets: list[ScoredMarket]) -> str:
    """Serialize top-N markets as a JSON array for the Claude prompt."""
    items = []
    for i, item in enumerate(markets, 1):
        m = item.market
        h = hours_remaining(m)
        if h is None:
            h_str = "unknown"
        elif h < 48:
            h_str = f"{h:.1f}h"
        else:
            h_str = f"{h / 24:.1f}d"

        items.append({
            "rank": i,
            "question": m.question,
            "yes_price": m.yes_price,
            "no_price": m.no_price,
            "hours_to_close": h_str,
            "volume_24h_usd": round(m.volume_24h or 0),
            "liquidity_usd": round(m.liquidity or 0),
            "edge_cents": edge_cents(m),
            "bucket": liquidity_bucket(m),
            "opportunity_score": item.score,
            "score_breakdown": {
                "price_attractiveness": item.breakdown.price_attractiveness,
                "time_to_close": item.breakdown.time_to_close,
                "liquidity_volume": item.breakdown.liquidity_volume,
                "market_activity": item.breakdown.market_activity,
            },
        })
    return json.dumps(items, indent=2, ensure_ascii=False)


def _extract_json_from_response(response: anthropic.types.Message) -> dict:
    """Pull JSON out of the text blocks (ignoring thinking blocks)."""
    text_parts = [b.text for b in response.content if hasattr(b, "text") and b.text]
    full_text = "\n".join(text_parts).strip()

    # Try direct parse first
    try:
        return json.loads(full_text)
    except json.JSONDecodeError:
        pass

    # Find the first {...} block
    match = re.search(r'\{[\s\S]*\}', full_text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in response. Text: {full_text[:300]}")


async def analyze_markets(
    markets: list[ScoredMarket],
    client: anthropic.AsyncAnthropic,
    cycle: int = 1,
) -> list[MarketRecommendation]:
    """
    Send all markets to Claude in one call. Returns sorted recommendations.

    Uses prompt caching on the system prompt — first call writes cache (~1.25x),
    subsequent calls within 5 min read it back (~0.1x).
    """
    if not markets:
        return []

    market_payload = _build_market_payload(markets)
    user_message = f"""\
Analyze these {len(markets)} Polymarket prediction markets and return your recommendations.

Markets:
{market_payload}

Return a JSON object with this exact structure:
{{
  "recommendations": [
    {{
      "rank": 1,
      "confidence": 0.XX,
      "action": "BUY_YES" | "BUY_NO" | "SKIP",
      "reason": "short explanation under 120 characters"
    }},
    ...one entry per market...
  ]
}}

Include one entry for EVERY market in the input (ranks 1 through {len(markets)}).
"""

    logger.info("claude_analyze cycle=%s markets=%s", cycle, len(markets))

    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},  # cached after first call
        }],
        messages=[{"role": "user", "content": user_message}],
    )

    # Log usage
    u = response.usage
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
    logger.info(
        "claude_usage in=%s out=%s cache_read=%s cache_write=%s",
        u.input_tokens, u.output_tokens, cache_read, cache_write,
    )

    # Parse response
    data = _extract_json_from_response(response)
    raw_recs = data.get("recommendations", [])

    # Build typed objects
    market_by_rank = {i + 1: item for i, item in enumerate(markets)}
    computed_at = datetime.now(UTC).isoformat()
    recommendations: list[MarketRecommendation] = []

    for rec in raw_recs:
        rank = int(rec.get("rank", 0))
        item = market_by_rank.get(rank)
        recommendations.append(
            MarketRecommendation(
                rank=rank,
                question=item.market.question if item else f"Market #{rank}",
                confidence=float(rec.get("confidence", 0.0)),
                action=str(rec.get("action", "SKIP")),
                reason=str(rec.get("reason", ""))[:120],
                yes_price=item.market.yes_price if item else None,
                no_price=item.market.no_price if item else None,
                score=item.score if item else 0.0,
                computed_at=computed_at,
            )
        )

    # Persist to JSONL
    _save_recommendations(recommendations, cycle, computed_at, u)

    return sorted(recommendations, key=lambda r: r.rank)


def _save_recommendations(
    recs: list[MarketRecommendation],
    cycle: int,
    computed_at: str,
    usage: anthropic.types.Usage,
) -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    entry = {
        "cycle": cycle,
        "computed_at": computed_at,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "recommendations": [r.model_dump() for r in recs],
    }
    with open(AI_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
