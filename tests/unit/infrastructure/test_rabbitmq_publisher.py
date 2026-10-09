from datetime import UTC, datetime

import pytest

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
