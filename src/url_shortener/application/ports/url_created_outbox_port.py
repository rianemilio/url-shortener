from typing import Protocol

from url_shortener.domain.events.url_created import URLCreated


class UrlCreatedOutboxPort(Protocol):
    """Eventos `URLCreated` gravados junto com a URL e ainda não publicados no broker."""

    async def pending(self, limit: int) -> list[URLCreated]: ...

    async def mark_published(self, event: URLCreated) -> None: ...
