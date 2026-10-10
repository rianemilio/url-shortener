import pytest

from tests.metrics_helpers import sample
from url_shortener.domain.value_objects.short_code import ShortCode
from url_shortener.infrastructure.cache.redis_cache import RedisCache


class FakeRedis:
    def __init__(self, store: dict[str, str]) -> None:
        self.store = store

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


class BrokenRedis:
    async def get(self, key: str) -> str | None:
        raise ConnectionError("redis indisponível")


def _lookups(result: str) -> float:
    return sample("url_shortener_cache_lookups_total", result=result)


@pytest.mark.asyncio
async def test_counts_hits_and_misses() -> None:
    cache = RedisCache(FakeRedis({"short_url:abc": "https://example.com"}), ttl_seconds=60)  # type: ignore[arg-type]
    hits, misses = _lookups("hit"), _lookups("miss")

    assert await cache.get(ShortCode("abc")) is not None
    assert await cache.get(ShortCode("xyz")) is None

    assert _lookups("hit") == hits + 1
    assert _lookups("miss") == misses + 1


@pytest.mark.asyncio
async def test_counts_errors_and_reraises() -> None:
    cache = RedisCache(BrokenRedis(), ttl_seconds=60)  # type: ignore[arg-type]
    errors = _lookups("error")

    with pytest.raises(ConnectionError):
        await cache.get(ShortCode("abc"))

    assert _lookups("error") == errors + 1
