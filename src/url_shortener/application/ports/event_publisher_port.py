from typing import Protocol

from url_shortener.domain.events.url_clicked import URLClicked
from url_shortener.domain.events.url_created import URLCreated

DomainEvent = URLCreated | URLClicked


class EventPublisherPort(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...
