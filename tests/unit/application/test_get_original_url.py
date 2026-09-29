from datetime import UTC, datetime

import pytest

from tests.fakes.fake_cache import FakeCache, UnavailableCache
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortner.application.queries.get_original_url import (
    GetOriginalUrlQuery,
    GetOriginalUrlQueryHandler,
)
from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.exceptions import UrlNotFoundError
from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode


async def _repo_with(code: str, url: str) -> FakeUrlRepository:
    repo = FakeUrlRepository()
    await repo.save(
        ShortUrl(code=ShortCode(code), original_url=OriginalUrl(url), created_at=datetime.now(UTC))
    )
    return repo


@pytest.mark.asyncio
async def test_returns_url_from_cache_without_touching_repository() -> None:
    repo = FakeUrlRepository()
    cache = FakeCache()
    await cache.set(ShortCode("abc"), OriginalUrl("https://cached.example.com"))
    handler = GetOriginalUrlQueryHandler(repo, cache)

    result = await handler.handle(GetOriginalUrlQuery(code="abc"))

    assert str(result) == "https://cached.example.com"
    assert repo.saved == {}


@pytest.mark.asyncio
async def test_falls_back_to_repository_and_repopulates_cache_on_miss() -> None:
    repo = await _repo_with("xyz", "https://from-db.example.com")
    cache = FakeCache()
    handler = GetOriginalUrlQueryHandler(repo, cache)

    result = await handler.handle(GetOriginalUrlQuery(code="xyz"))

    assert str(result) == "https://from-db.example.com"
    cached = await cache.get(ShortCode("xyz"))
    assert cached is not None and str(cached) == "https://from-db.example.com"


@pytest.mark.asyncio
async def test_falls_back_to_repository_when_cache_is_unavailable() -> None:
    repo = await _repo_with("xyz", "https://from-db.example.com")
    handler = GetOriginalUrlQueryHandler(repo, UnavailableCache())

    result = await handler.handle(GetOriginalUrlQuery(code="xyz"))

    assert str(result) == "https://from-db.example.com"


@pytest.mark.asyncio
async def test_raises_not_found_when_code_unknown() -> None:
    handler = GetOriginalUrlQueryHandler(FakeUrlRepository(), FakeCache())

    with pytest.raises(UrlNotFoundError):
        await handler.handle(GetOriginalUrlQuery(code="ghost"))
