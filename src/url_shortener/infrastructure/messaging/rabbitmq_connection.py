import aio_pika

from url_shortener.config import Settings


async def create_rabbitmq_connection(settings: Settings) -> aio_pika.abc.AbstractRobustConnection:
    return await aio_pika.connect_robust(
        settings.rabbitmq_uri, timeout=settings.rabbitmq_timeout_seconds
    )
