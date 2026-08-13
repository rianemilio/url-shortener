import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from url_shortner.application.ports.cache_port import CachePort
from url_shortner.application.ports.code_generator_port import CodeGeneratorPort
from url_shortner.application.ports.event_publisher_port import EventPublisherPort
from url_shortner.application.ports.url_repository import UrlRepositoryPort
from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.events.url_created import URLCreated
from url_shortner.domain.value_objects.original_url import OriginalUrl

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateShortUrlCommand:
    url: str


class CreateShortUrlCommandHandler:
    def __init__(
        self,
        url_repository: UrlRepositoryPort,
        cache: CachePort,
        code_generator: CodeGeneratorPort,
        event_publisher: EventPublisherPort,
    ) -> None:
        self._url_repository = url_repository
        self._cache = cache
        self._code_generator = code_generator
        self._event_publisher = event_publisher

    async def handle(self, command: CreateShortUrlCommand) -> ShortUrl:
        original_url = OriginalUrl(command.url)
        code = await self._code_generator.next_code()
        short_url = ShortUrl(
            code=code,
            original_url=original_url,
            created_at=datetime.now(UTC),
        )

        await self._url_repository.save(short_url)

        try:
            await self._cache.set(code, original_url)
        except Exception:
            logger.warning("Falha ao popular cache para o código %s", code, exc_info=True)

        try:
            await self._event_publisher.publish(
                URLCreated(
                    code=str(code),
                    original_url=str(original_url),
                    created_at=short_url.created_at,
                )
            )
        except Exception:
            logger.warning("Falha ao publicar evento URLCreated para %s", code, exc_info=True)

        return short_url
