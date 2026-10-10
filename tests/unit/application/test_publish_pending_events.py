from datetime import UTC, datetime

import pytest

from tests.fakes.fake_event_publisher import FakeEventPublisher
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortener.application.commands.publish_pending_events import (
    PublishPendingEventsCommand,
    PublishPendingEventsCommandHandler,
)
from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.events.url_created import URLCreated
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode


async def _repo_with_pending(*codes: str) -> FakeUrlRepository:
    repo = FakeUrlRepository()
    for code in codes:
        await repo.save(
            ShortUrl(
                code=ShortCode(code),
                original_url=OriginalUrl(f"https://example.com/{code}"),
                created_at=datetime.now(UTC),
            )
        )
    return repo


@pytest.mark.asyncio
async def test_publishes_pending_events_and_marks_them_published() -> None:
    repo = await _repo_with_pending("a", "b")
    publisher = FakeEventPublisher()
    handler = PublishPendingEventsCommandHandler(outbox=repo, event_publisher=publisher)

    published = await handler.handle(PublishPendingEventsCommand(batch_size=10))

    assert published == 2
    assert [e.code for e in publisher.published if isinstance(e, URLCreated)] == ["a", "b"]
    assert await repo.pending(limit=10) == []


@pytest.mark.asyncio
async def test_respects_batch_size() -> None:
    repo = await _repo_with_pending("a", "b", "c")
    handler = PublishPendingEventsCommandHandler(outbox=repo, event_publisher=FakeEventPublisher())

    published = await handler.handle(PublishPendingEventsCommand(batch_size=2))

    assert published == 2
    assert [e.code for e in await repo.pending(limit=10)] == ["c"]


@pytest.mark.asyncio
async def test_keeps_events_pending_when_publish_fails() -> None:
    repo = await _repo_with_pending("a", "b")
    handler = PublishPendingEventsCommandHandler(
        outbox=repo, event_publisher=FakeEventPublisher(fail_after=1)
    )

    with pytest.raises(ConnectionError):
        await handler.handle(PublishPendingEventsCommand(batch_size=10))

    assert [e.code for e in await repo.pending(limit=10)] == ["b"]
