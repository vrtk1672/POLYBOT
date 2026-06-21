from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def summarize_market_side_diversity(rows: list[dict[str, Any]], *, limit: int = 12) -> dict[str, Any]:
    market_side = Counter((str(row.get("market_id") or "UNKNOWN"), str(row.get("side") or "UNKNOWN")) for row in rows)
    market_counts = Counter(str(row.get("market_id") or "UNKNOWN") for row in rows)
    side_counts = Counter(str(row.get("side") or "UNKNOWN") for row in rows)
    blockers: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = f"{row.get('market_id') or 'UNKNOWN'}:{row.get('side') or 'UNKNOWN'}"
        for blocker in _list(row.get("blockers") or row.get("blockers_json") or row.get("policy_blockers_json")):
            blockers[key][str(blocker)] += 1
    total = len(rows)
    largest_group = max(market_side.values(), default=0)
    return {
        "total": total,
        "unique_markets": len({key[0] for key in market_side}),
        "unique_sides": len({key[1] for key in market_side}),
        "unique_market_sides": len(market_side),
        "concentration_score": round(largest_group / max(1, total), 4),
        "top_market_sides": [
            {"market_id": market, "side": side, "count": count}
            for (market, side), count in market_side.most_common(limit)
        ],
        "by_market": dict(market_counts.most_common(limit)),
        "by_side": dict(side_counts.most_common(limit)),
        "blockers_by_market_side": {
            key: dict(counter.most_common(limit))
            for key, counter in sorted(blockers.items(), key=lambda item: sum(item[1].values()), reverse=True)[:limit]
        },
    }


def top_non_selected_market_sides(rows: list[dict[str, Any]], selected_keys: set[tuple[str, str]], *, limit: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("market_id") or "UNKNOWN"), str(row.get("side") or "UNKNOWN"))
        if key in selected_keys:
            continue
        out.append(
            {
                "market_id": key[0],
                "side": key[1],
                "score": row.get("opportunity_score"),
                "blockers": _list(row.get("blockers") or row.get("blockers_json") or row.get("policy_blockers_json")),
            }
        )
        if len(out) >= limit:
            break
    return out


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
