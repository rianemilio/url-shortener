from redis.asyncio import Redis

from url_shortener.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    # Sem timeout, um Redis travado (que não recusa a conexão) prende a requisição para sempre.
    return Redis.from_url(
        settings.redis_uri,
        decode_responses=True,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_timeout_seconds,
    )
