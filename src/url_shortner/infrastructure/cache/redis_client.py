from redis.asyncio import Redis

from url_shortner.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_uri, decode_responses=True)
