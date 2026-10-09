import asyncio
import signal
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortener.application.commands.register_click import RegisterClickCommandHandler
from url_shortener.bootstrap.container import WorkerContainer
from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode
from url_shortener.interface.worker import click_consumer


class FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.outcome: str | None = None

    async def ack(self) -> None:
        self.outcome = "ack"

    async def nack(self, requeue: bool = True) -> None:
        self.outcome = "requeue" if requeue else "dead-letter"

    async def reject(self, requeue: bool = False) -> None:
        self.outcome = "requeue" if requeue else "dead-letter"


class BrokenRepository(FakeUrlRepository):
    async def increment_clicks(self, code: ShortCode) -> None:
        raise ConnectionError("mongo indisponível")


class FakeWorkerContainer:
    def __init__(self, repository: FakeUrlRepository) -> None:
        self.register_click_handler = RegisterClickCommandHandler(repository)


async def _handle(body: bytes, repository: FakeUrlRepository) -> FakeMessage:
    message = FakeMessage(body)
    await click_consumer._handle_message(
        cast(Any, message), cast(WorkerContainer, FakeWorkerContainer(repository))
    )
    return message


@pytest.mark.asyncio
async def test_acks_valid_message_and_increments_clicks() -> None:
    repository = FakeUrlRepository()
    await repository.save(
        ShortUrl(
            code=ShortCode("abc"),
            original_url=OriginalUrl("https://example.com"),
            created_at=datetime.now(UTC),
        )
    )

    message = await _handle(b'{"code": "abc"}', repository)

    assert message.outcome == "ack"
    stored = await repository.find_by_code(ShortCode("abc"))
    assert stored is not None and stored.click_count == 1


@pytest.mark.parametrize(
    "body",
    [b"not json", b"{}", b'{"code": 123}', b'{"code": "has-dash"}', b"[]"],
)
@pytest.mark.asyncio
async def test_dead_letters_permanently_invalid_messages(body: bytes) -> None:
    message = await _handle(body, FakeUrlRepository())

    assert message.outcome == "dead-letter"


@pytest.mark.asyncio
async def test_requeues_on_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(click_consumer, "_TRANSIENT_ERROR_BACKOFF_SECONDS", 0)

    message = await _handle(b'{"code": "abc"}', BrokenRepository())

    assert message.outcome == "requeue"


class FakeQueue:
    def __init__(self) -> None:
        self.consuming = asyncio.Event()
        self.cancelled = False

    async def consume(self, callback: Any) -> str:
        self.consuming.set()
        return "consumer-tag"

    async def cancel(self, consumer_tag: str) -> None:
        self.cancelled = True


class FakeChannel:
    async def set_qos(self, prefetch_count: int) -> None:
        pass


class FakeRunnableWorkerContainer:
    def __init__(self) -> None:
        self.url_clicked_queue = FakeQueue()
        self.rabbitmq_channel = FakeChannel()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_run_shuts_down_gracefully_on_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeRunnableWorkerContainer()

    async def fake_create() -> FakeRunnableWorkerContainer:
        return container

    monkeypatch.setattr(click_consumer.WorkerContainer, "create", fake_create)

    task = asyncio.create_task(click_consumer.run())
    # O consume só é chamado depois que os handlers de sinal estão instalados.
    await asyncio.wait_for(container.url_clicked_queue.consuming.wait(), timeout=1)
    signal.raise_signal(signal.SIGTERM)
    await asyncio.wait_for(task, timeout=1)

    assert container.url_clicked_queue.cancelled
    assert container.closed
