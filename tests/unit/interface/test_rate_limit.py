from collections import Counter

import httpx
import pytest
from fastapi import FastAPI

from tests.fakes.fake_cache import FakeCache
from tests.fakes.fake_code_generator import FakeCodeGenerator
from tests.fakes.fake_event_publisher import FakeEventPublisher
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortener.application.commands.create_short_url import CreateShortUrlCommandHandler
from url_shortener.config import Settings
from url_shortener.infrastructure.rate_limit.redis_rate_limiter import RateLimitDecision
from url_shortener.interface.api.routers import urls


class FakeRateLimiter:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self.hits: Counter[str] = Counter()

    async def hit(self, key: str) -> RateLimitDecision:
        self.hits[key] += 1
        return RateLimitDecision(allowed=self.hits[key] <= self._limit, retry_after_seconds=42)


class UnavailableRateLimiter:
    async def hit(self, key: str) -> RateLimitDecision:
        raise ConnectionError("redis indisponível")


class FakeApiContainer:
    def __init__(self, rate_limiter: FakeRateLimiter | UnavailableRateLimiter) -> None:
        self.settings = Settings()
        self.create_rate_limiter = rate_limiter
        self.create_short_url_handler = CreateShortUrlCommandHandler(
            url_repository=FakeUrlRepository(),
            cache=FakeCache(),
            code_generator=FakeCodeGenerator(),
            event_publisher=FakeEventPublisher(),
        )


def _client(rate_limiter: FakeRateLimiter | UnavailableRateLimiter) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(urls.router)
    app.state.container = FakeApiContainer(rate_limiter)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _create(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/urls", json={"url": "https://example.com"})


@pytest.mark.asyncio
async def test_allows_requests_within_limit() -> None:
    async with _client(FakeRateLimiter(limit=2)) as client:
        responses = [await _create(client) for _ in range(2)]

    assert [r.status_code for r in responses] == [201, 201]


@pytest.mark.asyncio
async def test_returns_429_with_retry_after_when_limit_exceeded() -> None:
    async with _client(FakeRateLimiter(limit=2)) as client:
        for _ in range(2):
            await _create(client)
        response = await _create(client)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"


@pytest.mark.asyncio
async def test_limits_per_client_ip() -> None:
    limiter = FakeRateLimiter(limit=5)
    async with _client(limiter) as client:
        await _create(client)

    assert list(limiter.hits) == ["127.0.0.1"]


@pytest.mark.asyncio
async def test_fails_open_when_rate_limiter_is_unavailable() -> None:
    async with _client(UnavailableRateLimiter()) as client:
        response = await _create(client)

    assert response.status_code == 201
