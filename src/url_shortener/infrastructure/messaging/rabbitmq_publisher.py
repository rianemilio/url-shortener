import asyncio
import json
import logging
from dataclasses import asdict

import aio_pika

from url_shortener.application.ports.event_publisher_port import DomainEvent
from url_shortener.config import Settings
from url_shortener.infrastructure.messaging.rabbitmq_connection import create_rabbitmq_connection
from url_shortener.infrastructure.messaging.topology import declare_topology

logger = logging.getLogger(__name__)


class EventPublisherUnavailableError(Exception):
    """O broker ainda não está conectado; o evento não foi publicado."""


def _serialize(event: DomainEvent) -> bytes:
    payload = {
        k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in asdict(event).items()
    }
    return json.dumps(payload).encode("utf-8")


class RabbitMQPublisher:
    """Publica eventos sem tornar o RabbitMQ obrigatório para a API subir.

    `start()` tenta conectar uma vez; se falhar, segue tentando em background e, até lá,
    `publish()` levanta `EventPublisherUnavailableError` (os handlers logam e seguem).
    Depois da primeira conexão, o `connect_robust` do aio-pika cuida das reconexões.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if await self._try_connect():
            return
        logger.warning(
            "RabbitMQ indisponível; a API sobe mesmo assim e tenta reconectar a cada %ss",
            self._settings.rabbitmq_reconnect_interval_seconds,
        )
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    @property
    def is_connected(self) -> bool:
        # `is_closed` não serve: na RobustConnection ele fica False enquanto ela tenta
        # reconectar. O evento `connected` é limpo quando a conexão cai.
        return self._connection is not None and self._connection.connected.is_set()

    async def publish(self, event: DomainEvent) -> None:
        if self._exchange is None:
            raise EventPublisherUnavailableError("RabbitMQ ainda não conectado")

        message = aio_pika.Message(
            body=_serialize(event),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(
            message,
            routing_key=event.ROUTING_KEY,
            timeout=self._settings.rabbitmq_timeout_seconds,
        )

    async def close(self) -> None:
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
        if self._connection is not None:
            await self._connection.close()

    async def _try_connect(self) -> bool:
        try:
            connection = await create_rabbitmq_connection(self._settings)
        except Exception:
            logger.debug("Falha ao conectar no RabbitMQ", exc_info=True)
            return False

        try:
            channel = await connection.channel()
            topology = await declare_topology(channel)
        except Exception:
            logger.warning("Falha ao declarar a topologia no RabbitMQ", exc_info=True)
            await connection.close()
            return False

        self._connection = connection
        self._exchange = topology.events_exchange
        logger.info("Conectado ao RabbitMQ")
        return True

    async def _reconnect_loop(self) -> None:
        while not await self._try_connect():
            await asyncio.sleep(self._settings.rabbitmq_reconnect_interval_seconds)
