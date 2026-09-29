import logging
from dataclasses import dataclass

from url_shortener.application.ports.cache_port import CachePort
from url_shortener.application.ports.url_repository import UrlRepositoryPort
from url_shortener.domain.exceptions import UrlNotFoundError
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GetOriginalUrlQuery:
    code: str


class GetOriginalUrlQueryHandler:
    def __init__(self, url_repository: UrlRepositoryPort, cache: CachePort) -> None:
        self._url_repository = url_repository
        self._cache = cache

    async def handle(self, query: GetOriginalUrlQuery) -> OriginalUrl:
        code = ShortCode(query.code)

        original_url = await self._get_from_cache(code)
        if original_url is not None:
            return original_url

        short_url = await self._url_repository.find_by_code(code)
        if short_url is None:
            raise UrlNotFoundError(f"Nenhuma URL encontrada para o código {code}")

        try:
            await self._cache.set(code, short_url.original_url)
        except Exception:
            logger.warning("Falha ao popular cache para o código %s", code, exc_info=True)

        return short_url.original_url

    async def _get_from_cache(self, code: ShortCode) -> OriginalUrl | None:
        try:
            return await self._cache.get(code)
        except Exception:
            logger.warning("Falha ao ler cache para o código %s", code, exc_info=True)
            return None
