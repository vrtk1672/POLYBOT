import asyncio

import httpx

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)


class GammaClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.gamma_api_base_url,
            timeout=settings.request_timeout_seconds,
            headers={
                "Accept": "application/json",
                "User-Agent": settings.user_agent,
            },
        )

    async def fetch_active_events(self) -> list[dict]:
        all_events: list[dict] = []

        for page in range(self._settings.gamma_max_pages):
            offset = page * self._settings.gamma_page_limit
            params = {
                "active": "true",
                "closed": "false",
                "limit": self._settings.gamma_page_limit,
                "offset": offset,
            }
            page_items = await self._get_json(self._settings.gamma_events_path, params=params)
            if not isinstance(page_items, list):
                raise TypeError("Gamma events payload was not a list.")

            all_events.extend(page_items)
            if len(page_items) < self._settings.gamma_page_limit:
                break

        logger.info("gamma_fetch_complete events=%s", len(all_events))
        return all_events

    async def _get_json(self, path: str, params: dict) -> list[dict] | dict:
        last_error: Exception | None = None

        for attempt in range(self._settings.request_max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                is_retryable = self._is_retryable(exc)
                logger.warning(
                    "gamma_request_failed attempt=%s retryable=%s error=%s",
                    attempt + 1,
                    is_retryable,
                    exc,
                )
                if not is_retryable or attempt >= self._settings.request_max_retries:
                    break
                await asyncio.sleep(min(2**attempt, 5))

        if last_error is None:
            raise RuntimeError("Gamma request failed without an exception.")
        raise last_error

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500 or exc.response.status_code == 429
        return isinstance(exc, httpx.RequestError)

    async def aclose(self) -> None:
        await self._client.aclose()

