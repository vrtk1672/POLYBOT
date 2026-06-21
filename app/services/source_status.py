from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.db.connection import DatabaseConnectionFactory
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.neuron_signals import NeuronSignalService


RUNTIME_ACTIVE = "ACTIVE"
RUNTIME_DEGRADED = "DEGRADED"
RUNTIME_MISSING = "MISSING"
RUNTIME_DISABLED = "DISABLED"
FRESH = "FRESH"
UNKNOWN = "UNKNOWN"

DEFAULT_CLOB_BASE_URL = "https://clob.polymarket.com"
DEFAULT_DATA_API_BASE_URL = "https://data-api.polymarket.com"


class JsonHttpClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        ...


class HttpxJsonClient:
    def __init__(self, *, timeout_seconds: float, user_agent: str) -> None:
        self._timeout_seconds = timeout_seconds
        self._headers = {"User-Agent": user_agent}

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, int]:
        merged_headers = dict(self._headers)
        if headers:
            merged_headers.update(headers)
        started = time.perf_counter()
        with httpx.Client(timeout=self._timeout_seconds, headers=merged_headers) as client:
            response = client.get(url, params=params)
            latency_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            return response.json(), latency_ms


@dataclass
class SourceCheck:
    source_name: str
    source_type: str
    configured: bool
    key_required: bool
    key_present: bool
    endpoint_url: str | None
    runtime_status: str
    freshness_status: str = UNKNOWN
    notes: str = ""
    key_name: str | None = None
    latency_ms: int | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None
    details_json: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    mutation_allowed: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "configured": self.configured,
            "key_required": self.key_required,
            "key_present": self.key_present,
            "key_name": self.key_name,
            "endpoint_url": self.endpoint_url,
            "runtime_status": self.runtime_status,
            "freshness_status": self.freshness_status,
            "read_only": self.read_only,
            "mutation_allowed": self.mutation_allowed,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "latency_ms": self.latency_ms,
            "details_json": self.details_json,
            "notes": self.notes,
        }


class SourceStatusService:
    def __init__(
        self,
        *,
        http_client: JsonHttpClient | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        settings = get_settings()
        self._settings = settings
        self._http = http_client or HttpxJsonClient(
            timeout_seconds=min(settings.request_timeout_seconds, 10.0),
            user_agent=settings.user_agent,
        )
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = SourceStatusRepository()
        self._gamma_base_url = settings.gamma_api_base_url.rstrip("/")
        self._clob_base_url = (
            os.getenv("POLYMARKET_CLOB_HOST")
            or os.getenv("POLYBOT_CLOB_API_BASE_URL")
            or os.getenv("POLY_CLOB_HOST")
            or DEFAULT_CLOB_BASE_URL
        ).rstrip("/")
        self._data_api_base_url = (
            os.getenv("POLYBOT_POLYMARKET_DATA_API_BASE_URL") or DEFAULT_DATA_API_BASE_URL
        ).rstrip("/")

    def get_dashboard_source_status(self, *, persist: bool = True) -> dict[str, Any]:
        updated_at = _now_iso()
        checks = self.collect_source_status()
        if persist:
            self._persist_safely(checks)
            self._record_signals_safely(checks)
        critical = {
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
        }
        degraded = [
            item.source_name
            for item in checks
            if item.source_name in critical and item.runtime_status != RUNTIME_ACTIVE
        ]
        return {
            "status": "DEGRADED" if degraded else "OK",
            "mock_data": False,
            "stale": False,
            "updated_at": updated_at,
            "sources": [item.to_api_dict() for item in checks],
            "degraded_sources": degraded,
        }

    def collect_source_status(self) -> list[SourceCheck]:
        gamma, token_candidates = self._check_gamma()
        clob_checks = self._check_clob_book(
            token_candidates=token_candidates,
            gamma_status=gamma.runtime_status,
        )
        return [
            gamma,
            *clob_checks,
            self._check_activity_readonly(),
            self._check_ollama_status(),
            self._placeholder(
                source_name="news_provider",
                source_type="news",
                key_name="NEWS_API_KEY",
                notes="News provider is intentionally disabled for V2.21; no real calls made.",
            ),
            self._placeholder(
                source_name="reddit_or_social_provider",
                source_type="social",
                key_name="REDDIT_CLIENT_ID",
                notes="Social provider is intentionally disabled for V2.21; no real calls made.",
            ),
        ]

    def _check_gamma(self) -> tuple[SourceCheck, list[tuple[str, str | None]]]:
        endpoint = f"{self._gamma_base_url}{self._settings.gamma_events_path}"
        params = {
            "active": "true",
            "closed": "false",
            "limit": 10,
            "order": "volume_24hr",
            "ascending": "false",
        }
        try:
            payload, latency_ms = self._http.get_json(endpoint, params=params)
            events = payload if isinstance(payload, list) else payload.get("events", [])
            token_candidates = _extract_token_candidates_from_gamma_events(events)
            return (
                self._active(
                    source_name="polymarket_gamma",
                    source_type="market_discovery",
                    endpoint_url=endpoint,
                    latency_ms=latency_ms,
                    notes="Gamma active events check succeeded.",
                    details={
                        "event_count": len(events) if isinstance(events, list) else 0,
                        "sample_market_id": token_candidates[0][1] if token_candidates else None,
                        "sample_token_available": bool(token_candidates),
                        "token_candidates": len(token_candidates),
                    },
                ),
                token_candidates,
            )
        except Exception as exc:
            return (
                self._degraded(
                    source_name="polymarket_gamma",
                    source_type="market_discovery",
                    endpoint_url=endpoint,
                    notes="Gamma active events check failed.",
                    error=exc,
                ),
                [],
            )

    def _check_clob_book(
        self,
        *,
        token_candidates: list[tuple[str, str | None]],
        gamma_status: str,
    ) -> list[SourceCheck]:
        endpoint = f"{self._clob_base_url}/book"
        if not token_candidates:
            status = RUNTIME_MISSING if gamma_status == RUNTIME_ACTIVE else RUNTIME_DEGRADED
            check = SourceCheck(
                source_name="polymarket_clob_orderbook",
                source_type="orderbook",
                configured=True,
                key_required=False,
                key_present=False,
                endpoint_url=endpoint,
                runtime_status=status,
                freshness_status=UNKNOWN,
                notes="No sample token was available for a read-only CLOB book check.",
                last_error_at=_now_iso(),
                details_json={},
            )
            return [
                check,
                self._derived_missing("polymarket_clob_prices", "prices", "No orderbook sample available."),
                self._derived_missing("polymarket_clob_spreads", "spreads", "No orderbook sample available."),
            ]

        last_error: Exception | None = None
        attempted = 0
        for token_id, market_id in token_candidates[:10]:
            attempted += 1
            try:
                payload, latency_ms = self._http.get_json(endpoint, params={"token_id": token_id})
                metrics = _orderbook_metrics(payload)
                if not metrics["has_book"]:
                    raise ValueError("CLOB book response did not include bid/ask depth")
            except Exception as exc:
                last_error = exc
                continue
            details = {
                "sample_market_id": market_id,
                "sample_token_id": token_id,
                "attempted_tokens": attempted,
                "best_bid": metrics["best_bid"],
                "best_ask": metrics["best_ask"],
                "spread": metrics["spread"],
                "depth_1c": metrics["depth_1c"],
                "last_trade_price_present": metrics["last_trade_price_present"],
            }
            return [
                self._active(
                    source_name="polymarket_clob_orderbook",
                    source_type="orderbook",
                    endpoint_url=endpoint,
                    latency_ms=latency_ms,
                    notes="CLOB /book read-only check succeeded.",
                    details=details,
                ),
                self._active(
                    source_name="polymarket_clob_prices",
                    source_type="prices",
                    endpoint_url="CLOB /book derived best bid/ask/last_trade_price",
                    latency_ms=latency_ms,
                    notes="Price truth derived from read-only CLOB book response.",
                    details=details,
                ),
                self._active(
                    source_name="polymarket_clob_spreads",
                    source_type="spreads",
                    endpoint_url="CLOB /book derived spread/depth",
                    latency_ms=latency_ms,
                    notes="Spread and depth truth derived from read-only CLOB book response.",
                    details=details,
                ),
            ]

        error = last_error or RuntimeError("No CLOB token candidates were checked")
        details = {"attempted_tokens": attempted}
        return [
            self._degraded(
                source_name="polymarket_clob_orderbook",
                source_type="orderbook",
                endpoint_url=endpoint,
                notes="CLOB /book read-only check failed for bounded Gamma token candidates.",
                error=error,
                details=details,
            ),
            self._degraded(
                source_name="polymarket_clob_prices",
                source_type="prices",
                endpoint_url="CLOB /book derived best bid/ask/last_trade_price",
                notes="CLOB price truth unavailable because /book failed.",
                error=error,
                details=details,
            ),
            self._degraded(
                source_name="polymarket_clob_spreads",
                source_type="spreads",
                endpoint_url="CLOB /book derived spread/depth",
                notes="CLOB spread truth unavailable because /book failed.",
                error=error,
                details=details,
            ),
        ]

    def _check_activity_readonly(self) -> SourceCheck:
        endpoint = f"{self._data_api_base_url}/trades"
        try:
            payload, latency_ms = self._http.get_json(endpoint, params={"limit": 1, "offset": 0})
            if not isinstance(payload, list):
                raise ValueError("Data API trades response was not a list")
            return self._active(
                source_name="polymarket_activity_readonly",
                source_type="activity",
                endpoint_url=endpoint,
                latency_ms=latency_ms,
                notes="Data API /trades read-only discovery check succeeded.",
                details={"sample_count": len(payload)},
            )
        except Exception as exc:
            return self._degraded(
                source_name="polymarket_activity_readonly",
                source_type="activity",
                endpoint_url=endpoint,
                notes="Data API /trades read-only discovery check failed.",
                error=exc,
            )

    def _check_ollama_status(self) -> SourceCheck:
        base_url = os.getenv("OLLAMA_BASE_URL")
        if not base_url:
            return SourceCheck(
                source_name="ollama_local_model",
                source_type="local_ai",
                configured=False,
                key_required=False,
                key_present=False,
                endpoint_url=None,
                runtime_status=RUNTIME_DISABLED,
                freshness_status=UNKNOWN,
                notes="OLLAMA_BASE_URL is not configured; model routing is outside V2.21.",
            )
        endpoint = f"{base_url.rstrip('/')}/api/tags"
        last_error: Exception | None = None
        attempted: list[str] = []
        try:
            for candidate_endpoint in _ollama_tag_endpoints(base_url):
                attempted.append(candidate_endpoint)
                try:
                    payload, latency_ms = self._http.get_json(candidate_endpoint)
                except Exception as exc:
                    last_error = exc
                    continue
                models = payload.get("models", []) if isinstance(payload, dict) else []
                model_names = [str(item.get("name")) for item in models if isinstance(item, dict)]
                configured_models = [
                    value
                    for value in (
                        os.getenv("OLLAMA_MODEL_FAST"),
                        os.getenv("OLLAMA_MODEL_PRIMARY"),
                        os.getenv("OLLAMA_MODEL_REASONING"),
                    )
                    if value
                ]
                missing_configured = [model for model in dict.fromkeys(configured_models) if model not in model_names]
                return self._active(
                    source_name="ollama_local_model",
                    source_type="local_ai",
                    endpoint_url=candidate_endpoint,
                    latency_ms=latency_ms,
                    notes="Ollama tag check succeeded; model routing remains outside V2.21.",
                    details={
                        "model_count": len(model_names),
                        "configured_models": configured_models,
                        "missing_configured_models": missing_configured,
                        "qwen3_4b_present": "qwen3:4b" in model_names,
                        "attempted_endpoints": attempted,
                    },
                )
        except Exception as exc:
            last_error = exc
        error = last_error or RuntimeError("Ollama tag check failed")
        return self._degraded(
            source_name="ollama_local_model",
            source_type="local_ai",
            endpoint_url=endpoint,
            notes="Ollama tag check failed; model routing remains outside V2.21.",
            error=error,
            details={"attempted_endpoints": attempted},
        )

    def _placeholder(
        self,
        *,
        source_name: str,
        source_type: str,
        key_name: str,
        notes: str,
    ) -> SourceCheck:
        return SourceCheck(
            source_name=source_name,
            source_type=source_type,
            configured=False,
            key_required=True,
            key_present=bool(os.getenv(key_name)),
            key_name=key_name,
            endpoint_url=None,
            runtime_status=RUNTIME_DISABLED,
            freshness_status=UNKNOWN,
            notes=notes,
        )

    def _active(
        self,
        *,
        source_name: str,
        source_type: str,
        endpoint_url: str | None,
        latency_ms: int | None,
        notes: str,
        details: dict[str, Any] | None = None,
    ) -> SourceCheck:
        return SourceCheck(
            source_name=source_name,
            source_type=source_type,
            configured=True,
            key_required=False,
            key_present=False,
            endpoint_url=endpoint_url,
            runtime_status=RUNTIME_ACTIVE,
            freshness_status=FRESH,
            latency_ms=latency_ms,
            last_success_at=_now_iso(),
            details_json=details or {},
            notes=notes,
        )

    def _degraded(
        self,
        *,
        source_name: str,
        source_type: str,
        endpoint_url: str | None,
        notes: str,
        error: Exception,
        details: dict[str, Any] | None = None,
    ) -> SourceCheck:
        safe_details = dict(details or {})
        safe_details["error_type"] = type(error).__name__
        safe_details["error"] = _safe_error(error)
        return SourceCheck(
            source_name=source_name,
            source_type=source_type,
            configured=True,
            key_required=False,
            key_present=False,
            endpoint_url=endpoint_url,
            runtime_status=RUNTIME_DEGRADED,
            freshness_status=UNKNOWN,
            last_error_at=_now_iso(),
            details_json=safe_details,
            notes=notes,
        )

    def _derived_missing(self, source_name: str, source_type: str, notes: str) -> SourceCheck:
        return SourceCheck(
            source_name=source_name,
            source_type=source_type,
            configured=True,
            key_required=False,
            key_present=False,
            endpoint_url="CLOB /book derived",
            runtime_status=RUNTIME_MISSING,
            freshness_status=UNKNOWN,
            notes=notes,
            last_error_at=_now_iso(),
        )

    def _persist_safely(self, checks: list[SourceCheck]) -> None:
        if not self._factory.enabled:
            return
        try:
            with self._factory.connect() as conn, conn.transaction():
                for check in checks:
                    self._repository.upsert_status(conn, check.to_api_dict())
        except Exception:
            return

    def _record_signals_safely(self, checks: list[SourceCheck]) -> None:
        if not self._factory.enabled:
            return
        try:
            NeuronSignalService(connection_factory=self._factory).record_source_status_signals(
                [check.to_api_dict() for check in checks]
            )
        except Exception:
            return


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _ollama_tag_endpoints(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    endpoints = [f"{normalized}/api/tags"]
    if normalized in {"http://localhost:11434", "http://127.0.0.1:11434"}:
        endpoints.append("http://host.docker.internal:11434/api/tags")
    return endpoints


def _safe_error(error: Exception) -> str:
    text = str(error)
    if len(text) > 240:
        return f"{text[:237]}..."
    return text


def _extract_token_candidates_from_gamma_events(events: Any) -> list[tuple[str, str | None]]:
    candidates: list[tuple[str, str | None]] = []
    if not isinstance(events, list):
        return candidates
    for event in events:
        if not isinstance(event, dict):
            continue
        markets = event.get("markets")
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            if not _is_readonly_orderbook_candidate(market):
                continue
            market_id = str(market.get("id") or market.get("conditionId") or "")
            token_ids = _coerce_token_ids(market.get("clobTokenIds"))
            for token_id in token_ids:
                candidates.append((token_id, market_id or None))
    return candidates


def _is_readonly_orderbook_candidate(market: dict[str, Any]) -> bool:
    """Keep the source-status CLOB probe on markets that should expose books."""
    if market.get("active") is False or market.get("closed") is True:
        return False
    if market.get("acceptingOrders") is False:
        return False
    if market.get("enableOrderBook") is False:
        return False
    return True


def _coerce_token_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            import json

            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return []
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item)]
        return [stripped]
    return []


def _orderbook_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"has_book": False}
    bids = _levels(payload.get("bids") or payload.get("buy") or [])
    asks = _levels(payload.get("asks") or payload.get("sell") or [])
    best_bid = max((level["price"] for level in bids), default=None)
    best_ask = min((level["price"] for level in asks), default=None)
    spread = round(best_ask - best_bid, 6) if best_bid is not None and best_ask is not None else None
    mid = round((best_bid + best_ask) / 2, 6) if best_bid is not None and best_ask is not None else None
    return {
        "has_book": bool(bids and asks),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "depth_1c": _depth_near(bids, asks, mid, 0.01),
        "last_trade_price_present": payload.get("last_trade_price") is not None,
    }


def _levels(value: Any) -> list[dict[str, float]]:
    output: list[dict[str, float]] = []
    if not isinstance(value, list):
        return output
    for item in value:
        try:
            price = float(item.get("price") if isinstance(item, dict) else item[0])
            size = float(item.get("size") if isinstance(item, dict) else item[1])
        except (AttributeError, IndexError, TypeError, ValueError):
            continue
        if price >= 0 and size >= 0:
            output.append({"price": price, "size": size})
    return output


def _depth_near(
    bids: list[dict[str, float]],
    asks: list[dict[str, float]],
    mid: float | None,
    band: float,
) -> float:
    if mid is None:
        return 0.0
    epsilon = 1e-9
    return round(
        sum(level["size"] for level in bids if mid - level["price"] <= band + epsilon)
        + sum(level["size"] for level in asks if level["price"] - mid <= band + epsilon),
        6,
    )
