import aio_pika
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from url_shortner.application.commands.create_short_url import CreateShortUrlCommandHandler
from url_shortner.application.commands.register_click import RegisterClickCommandHandler
from url_shortner.application.commands.track_click import TrackClickCommandHandler
from url_shortner.application.queries.get_original_url import GetOriginalUrlQueryHandler
from url_shortner.config import Settings, get_settings
from url_shortner.infrastructure.cache.redis_cache import RedisCache
from url_shortner.infrastructure.cache.redis_client import create_redis_client
from url_shortner.infrastructure.messaging.rabbitmq_connection import create_rabbitmq_connection
from url_shortner.infrastructure.messaging.rabbitmq_publisher import RabbitMQPublisher
from url_shortner.infrastructure.messaging.topology import declare_events_exchange
from url_shortner.infrastructure.persistence.counter.mongo_counter_code_generator import (
    MongoCounterCodeGenerator,
)
from url_shortner.infrastructure.persistence.mongo.client import create_mongo_client, get_database
from url_shortner.infrastructure.persistence.mongo.mongo_url_repository import MongoUrlRepository


class ApiContainer:
    """Dependências da API: Mongo, Redis e publicação de eventos no RabbitMQ."""

    def __init__(
        self,
        settings: Settings,
        mongo_client: AsyncIOMotorClient,
        redis_client: Redis,
        rabbitmq_connection: aio_pika.abc.AbstractRobustConnection,
        rabbitmq_exchange: aio_pika.abc.AbstractExchange,
    ) -> None:
        self.settings = settings
        self.mongo_client = mongo_client
        self.redis_client = redis_client
        self.rabbitmq_connection = rabbitmq_connection

        database = get_database(mongo_client, settings)
        url_repository = MongoUrlRepository(database)
        cache = RedisCache(redis_client, settings.redis_cache_ttl_seconds)
        event_publisher = RabbitMQPublisher(rabbitmq_exchange)

        self.create_short_url_handler = CreateShortUrlCommandHandler(
            url_repository=url_repository,
            cache=cache,
            code_generator=MongoCounterCodeGenerator(database),
            event_publisher=event_publisher,
        )
        self.get_original_url_handler = GetOriginalUrlQueryHandler(
            url_repository=url_repository,
            cache=cache,
        )
        self.track_click_handler = TrackClickCommandHandler(event_publisher=event_publisher)

    @classmethod
    async def create(cls, settings: Settings | None = None) -> "ApiContainer":
        settings = settings or get_settings()

        rabbitmq_connection = await create_rabbitmq_connection(settings)
        rabbitmq_channel = await rabbitmq_connection.channel()
        rabbitmq_exchange = await declare_events_exchange(rabbitmq_channel)

        return cls(
            settings=settings,
            mongo_client=create_mongo_client(settings),
            redis_client=create_redis_client(settings),
            rabbitmq_connection=rabbitmq_connection,
            rabbitmq_exchange=rabbitmq_exchange,
        )

    async def close(self) -> None:
        await self.rabbitmq_connection.close()
        await self.redis_client.aclose()
        self.mongo_client.close()


class WorkerContainer:
    """Dependências do worker de cliques: só Mongo e consumo do RabbitMQ."""

    def __init__(
        self,
        settings: Settings,
        mongo_client: AsyncIOMotorClient,
        rabbitmq_connection: aio_pika.abc.AbstractRobustConnection,
        rabbitmq_channel: aio_pika.abc.AbstractChannel,
        rabbitmq_exchange: aio_pika.abc.AbstractExchange,
    ) -> None:
        self.settings = settings
        self.mongo_client = mongo_client
        self.rabbitmq_connection = rabbitmq_connection
        self.rabbitmq_channel = rabbitmq_channel
        self.rabbitmq_exchange = rabbitmq_exchange

        database = get_database(mongo_client, settings)
        self.register_click_handler = RegisterClickCommandHandler(
            url_repository=MongoUrlRepository(database),
        )

    @classmethod
    async def create(cls, settings: Settings | None = None) -> "WorkerContainer":
        settings = settings or get_settings()

        rabbitmq_connection = await create_rabbitmq_connection(settings)
        rabbitmq_channel = await rabbitmq_connection.channel()
        rabbitmq_exchange = await declare_events_exchange(rabbitmq_channel)

        return cls(
            settings=settings,
            mongo_client=create_mongo_client(settings),
            rabbitmq_connection=rabbitmq_connection,
            rabbitmq_channel=rabbitmq_channel,
            rabbitmq_exchange=rabbitmq_exchange,
        )

    async def close(self) -> None:
        await self.rabbitmq_connection.close()
        self.mongo_client.close()
