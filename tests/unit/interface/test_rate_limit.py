from collections import Counter

import httpx
import pytest
from fastapi import FastAPI

from tests.fakes.fake_cache import FakeCache
from tests.fakes.fake_code_generator import FakeCodeGenerator
from tests.fakes.fake_event_publisher import FakeEventPublisher
from tests.fakes.fake_url_repository import FakeUrlRepository
from tests.metrics_helpers import sample
from url_shortener.application.commands.create_short_url import CreateShortUrlCommandHandler
from url_shortener.application.commands.track_click import TrackClickCommandHandler
from url_shortener.application.queries.get_original_url import GetOriginalUrlQueryHandler
from url_shortener.config import Settings
from url_shortener.infrastructure.rate_limit.redis_rate_limiter import RateLimitDecision
from url_shortener.interface.api.routers import redirect, urls


class FakeRateLimiter:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self.hits: Counter[str] = Counter()

    async def hit(self, key: str) -> RateLimitDecision:
        self.hits[key] += 1
        return RateLimitDecision(allowed=self.hits[key] <= self._limit, retry_after_seconds=42)

    async def peek(self, key: str) -> RateLimitDecision:
        return RateLimitDecision(allowed=self.hits[key] < self._limit, retry_after_seconds=42)


class UnavailableRateLimiter:
    async def hit(self, key: str) -> RateLimitDecision:
        raise ConnectionError("redis indisponível")

    async def peek(self, key: str) -> RateLimitDecision:
        raise ConnectionError("redis indisponível")


RateLimiter = FakeRateLimiter | UnavailableRateLimiter


class FakeApiContainer:
    def __init__(self, rate_limiter: RateLimiter, miss_limiter: RateLimiter) -> None:
        self.settings = Settings()
        self.create_rate_limiter = rate_limiter
        self.redirect_miss_rate_limiter = miss_limiter
        repo = FakeUrlRepository()
        cache = FakeCache()
        self.create_short_url_handler = CreateShortUrlCommandHandler(
            url_repository=repo, cache=cache, code_generator=FakeCodeGenerator()
        )
        self.get_original_url_handler = GetOriginalUrlQueryHandler(url_repository=repo, cache=cache)
        self.track_click_handler = TrackClickCommandHandler(event_publisher=FakeEventPublisher())


def _client(
    rate_limiter: RateLimiter, miss_limiter: RateLimiter | None = None
) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(urls.router)
    app.include_router(redirect.router)
    app.state.container = FakeApiContainer(rate_limiter, miss_limiter or rate_limiter)
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
        create_response = await _create(client)
        redirect_response = await client.get("/naoexiste")

    assert create_response.status_code == 201
    assert redirect_response.status_code == 404


@pytest.mark.asyncio
async def test_blocks_redirect_after_too_many_missing_codes() -> None:
    async with _client(FakeRateLimiter(limit=2)) as client:
        misses = [(await client.get(f"/naoexiste{i}")).status_code for i in range(2)]
        blocked = await client.get("/naoexiste9")

    assert misses == [404, 404]
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "42"


@pytest.mark.asyncio
async def test_successful_redirects_do_not_count_towards_miss_limit() -> None:
    miss_limiter = FakeRateLimiter(limit=1)
    async with _client(FakeRateLimiter(limit=100), miss_limiter) as client:
        code = (await _create(client)).json()["code"]
        statuses = [(await client.get(f"/{code}")).status_code for _ in range(3)]

    assert statuses == [307, 307, 307]
    assert miss_limiter.hits["127.0.0.1"] == 0


@pytest.mark.asyncio
async def test_counts_rejections_per_scope() -> None:
    def rejected(scope: str) -> float:
        return sample("url_shortener_rate_limited_requests_total", scope=scope)

    create_before, miss_before = rejected("create_url"), rejected("redirect_miss")
    async with _client(FakeRateLimiter(limit=1), FakeRateLimiter(limit=1)) as client:
        for _ in range(2):
            await _create(client)
        for i in range(2):
            await client.get(f"/naoexiste{i}")

    assert rejected("create_url") == create_before + 1
    assert rejected("redirect_miss") == miss_before + 1
