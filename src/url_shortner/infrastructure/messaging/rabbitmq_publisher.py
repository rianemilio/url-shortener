import json
from dataclasses import asdict

import aio_pika

from url_shortner.application.ports.event_publisher_port import DomainEvent


def _serialize(event: DomainEvent) -> bytes:
    payload = {
        k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in asdict(event).items()
    }
    return json.dumps(payload).encode("utf-8")


class RabbitMQPublisher:
    def __init__(self, exchange: aio_pika.abc.AbstractExchange) -> None:
        self._exchange = exchange

    async def publish(self, event: DomainEvent) -> None:
        message = aio_pika.Message(
            body=_serialize(event),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=event.ROUTING_KEY)
