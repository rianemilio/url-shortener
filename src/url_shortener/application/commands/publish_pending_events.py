from dataclasses import dataclass

from url_shortener.application.ports.event_publisher_port import EventPublisherPort
from url_shortener.application.ports.url_created_outbox_port import UrlCreatedOutboxPort


@dataclass(frozen=True, slots=True)
class PublishPendingEventsCommand:
    batch_size: int


class PublishPendingEventsCommandHandler:
    """Relay do outbox: publica os `URLCreated` pendentes e só então os marca como publicados.

    Entrega at-least-once: se o processo cair entre o publish e a marcação, o evento sai de
    novo na próxima rodada. Consumidores de `URLCreated` precisam ser idempotentes.
    """

    def __init__(self, outbox: UrlCreatedOutboxPort, event_publisher: EventPublisherPort) -> None:
        self._outbox = outbox
        self._event_publisher = event_publisher

    async def handle(self, command: PublishPendingEventsCommand) -> int:
        """Devolve quantos eventos publicou. Uma falha interrompe o lote: os eventos que
        faltaram continuam pendentes e saem na próxima rodada."""
        events = await self._outbox.pending(command.batch_size)
        for event in events:
            await self._event_publisher.publish(event)
            await self._outbox.mark_published(event)
        return len(events)
