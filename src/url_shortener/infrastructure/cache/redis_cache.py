from redis.asyncio import Redis

from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode
from url_shortener.metrics import CACHE_LOOKUPS

_KEY_PREFIX = "short_url:"


class RedisCache:
    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def get(self, code: ShortCode) -> OriginalUrl | None:
        try:
            value = await self._client.get(_KEY_PREFIX + str(code))
        except Exception:
            CACHE_LOOKUPS.labels("error").inc()
            raise
        if value is None:
            CACHE_LOOKUPS.labels("miss").inc()
            return None
        CACHE_LOOKUPS.labels("hit").inc()
        return OriginalUrl(str(value))

    async def set(self, code: ShortCode, original_url: OriginalUrl) -> None:
        await self._client.set(_KEY_PREFIX + str(code), str(original_url), ex=self._ttl_seconds)
