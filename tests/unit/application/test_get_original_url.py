import asyncio
from datetime import UTC, datetime

import pytest

from tests.fakes.fake_cache import FakeCache
from tests.fakes.fake_event_publisher import FakeEventPublisher
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortner.application.queries.get_original_url import (
    GetOriginalUrlQuery,
    GetOriginalUrlQueryHandler,
)
from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.events.url_clicked import URLClicked
from url_shortner.domain.exceptions import UrlNotFoundError
from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode


async def _drain_background_tasks(handler: GetOriginalUrlQueryHandler) -> None:
    tasks = list(handler._background_tasks)
    if tasks:
        await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_returns_url_from_cache_without_touching_repository() -> None:
    repo = FakeUrlRepository()
    cache = FakeCache()
    await cache.set(ShortCode("abc"), OriginalUrl("https://cached.example.com"))
    publisher = FakeEventPublisher()
    handler = GetOriginalUrlQueryHandler(repo, cache, publisher)

    result = await handler.handle(GetOriginalUrlQuery(code="abc"))
    await _drain_background_tasks(handler)

    assert str(result) == "https://cached.example.com"
    assert repo.saved == {}


@pytest.mark.asyncio
async def test_falls_back_to_repository_and_repopulates_cache_on_miss() -> None:
    repo = FakeUrlRepository()
    code = ShortCode("xyz")
    original = OriginalUrl("https://from-db.example.com")
    await repo.save(ShortUrl(code=code, original_url=original, created_at=datetime.now(UTC)))
    cache = FakeCache()
    publisher = FakeEventPublisher()
    handler = GetOriginalUrlQueryHandler(repo, cache, publisher)

    result = await handler.handle(GetOriginalUrlQuery(code="xyz"))
    await _drain_background_tasks(handler)

    assert str(result) == "https://from-db.example.com"
    cached = await cache.get(code)
    assert cached is not None and str(cached) == "https://from-db.example.com"


@pytest.mark.asyncio
async def test_raises_not_found_when_code_unknown() -> None:
    handler = GetOriginalUrlQueryHandler(FakeUrlRepository(), FakeCache(), FakeEventPublisher())

    with pytest.raises(UrlNotFoundError):
        await handler.handle(GetOriginalUrlQuery(code="ghost"))


@pytest.mark.asyncio
async def test_publishes_url_clicked_event_on_success() -> None:
    repo = FakeUrlRepository()
    cache = FakeCache()
    await cache.set(ShortCode("abc"), OriginalUrl("https://cached.example.com"))
    publisher = FakeEventPublisher()
    handler = GetOriginalUrlQueryHandler(repo, cache, publisher)

    await handler.handle(GetOriginalUrlQuery(code="abc"))
    await _drain_background_tasks(handler)

    assert len(publisher.published) == 1
    assert isinstance(publisher.published[0], URLClicked)
    assert publisher.published[0].code == "abc"
