import asyncio
from datetime import UTC, datetime
from typing import cast

import pytest

from tests.fakes.fake_event_publisher import FakeEventPublisher
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortener.application.commands.publish_pending_events import (
    PublishPendingEventsCommandHandler,
)
from url_shortener.bootstrap.container import WorkerContainer
from url_shortener.config import Settings
from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.events.url_created import URLCreated
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode
from url_shortener.interface.worker.outbox_relay import run_outbox_relay


class FlakyOutbox(FakeUrlRepository):
    """Falha na primeira leitura, como um Mongo que ainda está subindo."""

    def __init__(self) -> None:
        super().__init__()
        self.failures_left = 1

    async def pending(self, limit: int) -> list[URLCreated]:
        if self.failures_left:
            self.failures_left -= 1
            raise ConnectionError("mongo indisponível")
        return await super().pending(limit)


class FakeRelayContainer:
    def __init__(self, outbox: FakeUrlRepository) -> None:
        self.settings = Settings(outbox_poll_interval_seconds=0.01, outbox_batch_size=2)
        self.url_created_outbox = outbox
        self.publisher = FakeEventPublisher()
        self.publish_pending_events_handler = PublishPendingEventsCommandHandler(
            outbox=outbox, event_publisher=self.publisher
        )


async def _save(repo: FakeUrlRepository, *codes: str) -> None:
    for code in codes:
        await repo.save(
            ShortUrl(
                code=ShortCode(code),
                original_url=OriginalUrl(f"https://example.com/{code}"),
                created_at=datetime.now(UTC),
            )
        )


async def _run_until_drained(container: FakeRelayContainer) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(run_outbox_relay(cast(WorkerContainer, container), stop))
    for _ in range(100):
        if not container.url_created_outbox.pending_codes:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_publishes_every_pending_event_across_batches() -> None:
    repo = FakeUrlRepository()
    await _save(repo, "a", "b", "c", "d", "e")
    container = FakeRelayContainer(repo)

    await _run_until_drained(container)

    assert sorted(e.code for e in container.publisher.published) == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
async def test_keeps_running_after_a_failure() -> None:
    outbox = FlakyOutbox()
    await _save(outbox, "a")
    container = FakeRelayContainer(outbox)

    await _run_until_drained(container)

    assert [e.code for e in container.publisher.published] == ["a"]
