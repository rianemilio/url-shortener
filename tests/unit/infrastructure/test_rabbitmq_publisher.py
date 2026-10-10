from datetime import UTC, datetime

import pytest

from tests.metrics_helpers import sample
from url_shortener.config import Settings
from url_shortener.domain.events.url_clicked import URLClicked
from url_shortener.infrastructure.messaging.rabbitmq_publisher import (
    EventPublisherUnavailableError,
    RabbitMQPublisher,
)

# Porta 1 em loopback: conexão recusada na hora, sem depender de rede externa.
_UNREACHABLE = Settings(
    rabbitmq_uri="amqp://guest:guest@127.0.0.1:1/",
    rabbitmq_timeout_seconds=0.5,
    rabbitmq_reconnect_interval_seconds=0.05,
)


@pytest.mark.asyncio
async def test_start_does_not_raise_when_broker_is_unreachable() -> None:
    publisher = RabbitMQPublisher(_UNREACHABLE)

    await publisher.start()

    await publisher.close()


@pytest.mark.asyncio
async def test_publish_fails_fast_while_disconnected() -> None:
    publisher = RabbitMQPublisher(_UNREACHABLE)
    await publisher.start()

    with pytest.raises(EventPublisherUnavailableError):
        await publisher.publish(URLClicked(code="abc", clicked_at=datetime.now(UTC)))

    await publisher.close()


@pytest.mark.asyncio
async def test_counts_publish_failures() -> None:
    publisher = RabbitMQPublisher(_UNREACHABLE)
    await publisher.start()
    labels = {"routing_key": URLClicked.ROUTING_KEY}
    failures = sample("url_shortener_event_publish_failures_total", **labels)
    published = sample("url_shortener_events_published_total", **labels)

    with pytest.raises(EventPublisherUnavailableError):
        await publisher.publish(URLClicked(code="abc", clicked_at=datetime.now(UTC)))
    await publisher.close()

    assert sample("url_shortener_event_publish_failures_total", **labels) == failures + 1
    assert sample("url_shortener_events_published_total", **labels) == published
