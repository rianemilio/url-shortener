from collections.abc import Iterable
from urllib.parse import urlparse

import aio_pika
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from url_shortener.application.commands.create_short_url import CreateShortUrlCommandHandler
from url_shortener.application.commands.publish_pending_events import (
    PublishPendingEventsCommandHandler,
)
from url_shortener.application.commands.register_click import RegisterClickCommandHandler
from url_shortener.application.commands.track_click import TrackClickCommandHandler
from url_shortener.application.queries.get_original_url import GetOriginalUrlQueryHandler
from url_shortener.config import Settings, get_settings
from url_shortener.infrastructure.cache.redis_cache import RedisCache
from url_shortener.infrastructure.cache.redis_client import create_redis_client
from url_shortener.infrastructure.messaging.rabbitmq_connection import create_rabbitmq_connection
from url_shortener.infrastructure.messaging.rabbitmq_publisher import RabbitMQPublisher
from url_shortener.infrastructure.messaging.topology import declare_topology
from url_shortener.infrastructure.persistence.counter.mongo_counter_code_generator import (
    MongoCounterCodeGenerator,
)
from url_shortener.infrastructure.persistence.mongo.client import create_mongo_client, get_database
from url_shortener.infrastructure.persistence.mongo.mongo_url_created_outbox import (
    MongoUrlCreatedOutbox,
)
from url_shortener.infrastructure.persistence.mongo.mongo_url_repository import MongoUrlRepository
from url_shortener.infrastructure.rate_limit.redis_rate_limiter import RedisRateLimiter


class ApiContainer:
    """Dependências da API: Mongo, Redis e publicação de eventos no RabbitMQ."""

    def __init__(
        self,
        settings: Settings,
        mongo_client: AsyncIOMotorClient,
        redis_client: Redis,
        event_publisher: RabbitMQPublisher,
        reserved_codes: Iterable[str] = (),
    ) -> None:
        self.settings = settings
        self.mongo_client = mongo_client
        self.redis_client = redis_client
        self.event_publisher = event_publisher

        database = get_database(mongo_client, settings)
        url_repository = MongoUrlRepository(database)
        cache = RedisCache(redis_client, settings.redis_cache_ttl_seconds)

        self.create_short_url_handler = CreateShortUrlCommandHandler(
            url_repository=url_repository,
            cache=cache,
            code_generator=MongoCounterCodeGenerator(
                database, settings.code_secret.get_secret_value().encode()
            ),
            blocked_hosts=[urlparse(settings.base_url).hostname or ""],
            reserved_codes=reserved_codes,
        )
        self.get_original_url_handler = GetOriginalUrlQueryHandler(
            url_repository=url_repository,
            cache=cache,
        )
        self.track_click_handler = TrackClickCommandHandler(event_publisher=event_publisher)
        self.create_rate_limiter = RedisRateLimiter(
            redis_client,
            scope="create_url",
            limit=settings.rate_limit_create_requests,
            window_seconds=settings.rate_limit_create_window_seconds,
        )
        self.redirect_miss_rate_limiter = RedisRateLimiter(
            redis_client,
            scope="redirect_miss",
            limit=settings.rate_limit_redirect_miss_requests,
            window_seconds=settings.rate_limit_redirect_miss_window_seconds,
        )

    @classmethod
    async def create(
        cls, settings: Settings | None = None, reserved_codes: Iterable[str] = ()
    ) -> "ApiContainer":
        settings = settings or get_settings()

        # Não bloqueia a subida se o RabbitMQ estiver fora: o publisher reconecta em background.
        event_publisher = RabbitMQPublisher(settings)
        await event_publisher.start()

        return cls(
            settings=settings,
            mongo_client=create_mongo_client(settings),
            redis_client=create_redis_client(settings),
            event_publisher=event_publisher,
            reserved_codes=reserved_codes,
        )

    async def close(self) -> None:
        await self.event_publisher.close()
        await self.redis_client.aclose()
        self.mongo_client.close()


class WorkerContainer:
    """Dependências do worker: consumo de cliques e relay do outbox de `URLCreated`."""

    def __init__(
        self,
        settings: Settings,
        mongo_client: AsyncIOMotorClient,
        rabbitmq_connection: aio_pika.abc.AbstractRobustConnection,
        rabbitmq_channel: aio_pika.abc.AbstractChannel,
        url_clicked_queue: aio_pika.abc.AbstractQueue,
        event_publisher: RabbitMQPublisher,
    ) -> None:
        self.settings = settings
        self.mongo_client = mongo_client
        self.rabbitmq_connection = rabbitmq_connection
        self.rabbitmq_channel = rabbitmq_channel
        self.url_clicked_queue = url_clicked_queue
        self.event_publisher = event_publisher

        database = get_database(mongo_client, settings)
        self.register_click_handler = RegisterClickCommandHandler(
            url_repository=MongoUrlRepository(database),
        )
        self.url_created_outbox = MongoUrlCreatedOutbox(database)
        self.publish_pending_events_handler = PublishPendingEventsCommandHandler(
            outbox=self.url_created_outbox,
            event_publisher=event_publisher,
        )

    @classmethod
    async def create(cls, settings: Settings | None = None) -> "WorkerContainer":
        settings = settings or get_settings()

        rabbitmq_connection = await create_rabbitmq_connection(settings)
        rabbitmq_channel = await rabbitmq_connection.channel()
        topology = await declare_topology(rabbitmq_channel)

        # Conexão própria para publicar: o canal do consumer fica dedicado ao consumo.
        event_publisher = RabbitMQPublisher(settings)
        await event_publisher.start()

        return cls(
            settings=settings,
            mongo_client=create_mongo_client(settings),
            rabbitmq_connection=rabbitmq_connection,
            rabbitmq_channel=rabbitmq_channel,
            url_clicked_queue=topology.url_clicked_queue,
            event_publisher=event_publisher,
        )

    async def close(self) -> None:
        await self.event_publisher.close()
        await self.rabbitmq_connection.close()
        self.mongo_client.close()
