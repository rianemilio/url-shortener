from dataclasses import dataclass

from redis.asyncio import Redis

_KEY_PREFIX = "rate_limit:"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class RedisRateLimiter:
    """Janela fixa no Redis: no máximo `limit` chamadas por chave a cada `window_seconds`.

    Fica no Redis (e não em memória) para o limite valer entre várias instâncias da API.
    """

    def __init__(self, client: Redis, scope: str, limit: int, window_seconds: int) -> None:
        self._client = client
        self._scope = scope
        self._limit = limit
        self._window_seconds = window_seconds

    async def hit(self, key: str) -> RateLimitDecision:
        redis_key = f"{_KEY_PREFIX}{self._scope}:{key}"
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, self._window_seconds, nx=True)
            pipe.ttl(redis_key)
            count, _, ttl = await pipe.execute()

        return RateLimitDecision(
            allowed=count <= self._limit,
            retry_after_seconds=ttl if ttl > 0 else self._window_seconds,
        )
