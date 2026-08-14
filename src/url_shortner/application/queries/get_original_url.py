import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from url_shortner.application.ports.cache_port import CachePort
from url_shortner.application.ports.event_publisher_port import EventPublisherPort
from url_shortner.application.ports.url_repository import UrlRepositoryPort
from url_shortner.domain.events.url_clicked import URLClicked
from url_shortner.domain.exceptions import UrlNotFoundError
from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GetOriginalUrlQuery:
    code: str


class GetOriginalUrlQueryHandler:
    def __init__(
        self,
        url_repository: UrlRepositoryPort,
        cache: CachePort,
        event_publisher: EventPublisherPort,
    ) -> None:
        self._url_repository = url_repository
        self._cache = cache
        self._event_publisher = event_publisher
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def handle(self, query: GetOriginalUrlQuery) -> OriginalUrl:
        code = ShortCode(query.code)

        original_url = await self._cache.get(code)
        if original_url is None:
            short_url = await self._url_repository.find_by_code(code)
            if short_url is None:
                raise UrlNotFoundError(f"Nenhuma URL encontrada para o código {code}")
            original_url = short_url.original_url

            try:
                await self._cache.set(code, original_url)
            except Exception:
                logger.warning("Falha ao popular cache para o código %s", code, exc_info=True)

        event = URLClicked(code=str(code), clicked_at=datetime.now(UTC))
        task = asyncio.create_task(self._publish_click_event(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return original_url

    async def _publish_click_event(self, event: URLClicked) -> None:
        try:
            await self._event_publisher.publish(event)
        except Exception:
            logger.warning("Falha ao publicar evento URLClicked para %s", event.code, exc_info=True)
