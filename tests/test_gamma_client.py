import httpx
import pytest

from app.config import Settings
from app.ingestion.gamma_client import GammaClient


@pytest.mark.asyncio
async def test_gamma_client_retries_on_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json=[{"id": "event-1", "markets": []}])

    async def fast_sleep(_: float) -> None:
        return None

    settings = Settings(request_max_retries=1, gamma_max_pages=1, gamma_page_limit=100)
    client = GammaClient(settings=settings)
    client._client = httpx.AsyncClient(
        base_url=settings.gamma_api_base_url,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("app.ingestion.gamma_client.asyncio.sleep", fast_sleep)

    events = await client.fetch_active_events()
    await client.aclose()

    assert len(events) == 1
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_gamma_client_raises_after_non_retryable_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    settings = Settings(request_max_retries=2, gamma_max_pages=1)
    client = GammaClient(settings=settings)
    client._client = httpx.AsyncClient(
        base_url=settings.gamma_api_base_url,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_active_events()

    await client.aclose()


@pytest.mark.asyncio
async def test_gamma_client_keeps_collected_pages_when_late_offset_is_rejected() -> None:
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        offsets.append(offset)
        if offset >= 4:
            return httpx.Response(422, json={"error": "offset too high"})
        return httpx.Response(200, json=[{"id": f"event-{offset}-a", "markets": []}, {"id": f"event-{offset}-b", "markets": []}])

    settings = Settings(request_max_retries=0, gamma_max_pages=3, gamma_page_limit=2)
    client = GammaClient(settings=settings)
    client._client = httpx.AsyncClient(
        base_url=settings.gamma_api_base_url,
        transport=httpx.MockTransport(handler),
    )

    events = await client.fetch_active_events()
    await client.aclose()

    assert offsets == [0, 2, 4]
    assert [event["id"] for event in events] == ["event-0-a", "event-0-b", "event-2-a", "event-2-b"]
