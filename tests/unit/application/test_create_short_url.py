import pytest

from tests.fakes.fake_cache import FakeCache
from tests.fakes.fake_code_generator import FakeCodeGenerator
from tests.fakes.fake_event_publisher import FakeEventPublisher
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortner.application.commands.create_short_url import (
    CreateShortUrlCommand,
    CreateShortUrlCommandHandler,
)
from url_shortner.domain.events.url_created import URLCreated
from url_shortner.domain.exceptions import InvalidUrlError


def make_handler() -> tuple[
    CreateShortUrlCommandHandler, FakeUrlRepository, FakeCache, FakeEventPublisher
]:
    repo = FakeUrlRepository()
    cache = FakeCache()
    publisher = FakeEventPublisher()
    handler = CreateShortUrlCommandHandler(
        url_repository=repo,
        cache=cache,
        code_generator=FakeCodeGenerator(start=1),
        event_publisher=publisher,
    )
    return handler, repo, cache, publisher


@pytest.mark.asyncio
async def test_creates_and_persists_short_url() -> None:
    handler, repo, _cache, _publisher = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com/page"))

    assert str(result.original_url) == "https://example.com/page"
    stored = await repo.find_by_code(result.code)
    assert stored is not None
    assert stored.click_count == 0


@pytest.mark.asyncio
async def test_populates_cache_after_create() -> None:
    handler, _repo, cache, _publisher = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com"))

    cached = await cache.get(result.code)
    assert cached is not None
    assert str(cached) == "https://example.com"


@pytest.mark.asyncio
async def test_publishes_url_created_event() -> None:
    handler, _repo, _cache, publisher = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com"))

    assert len(publisher.published) == 1
    event = publisher.published[0]
    assert isinstance(event, URLCreated)
    assert event.code == str(result.code)
    assert event.original_url == "https://example.com"


@pytest.mark.asyncio
async def test_rejects_invalid_url() -> None:
    handler, _repo, _cache, _publisher = make_handler()

    with pytest.raises(InvalidUrlError):
        await handler.handle(CreateShortUrlCommand(url="not-a-url"))
