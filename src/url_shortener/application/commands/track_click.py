import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from url_shortener.application.ports.event_publisher_port import EventPublisherPort
from url_shortener.domain.events.url_clicked import URLClicked
from url_shortener.domain.value_objects.short_code import ShortCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrackClickCommand:
    code: str


class TrackClickCommandHandler:
    """Publica `URLClicked`; quem incrementa o contador é o worker (`RegisterClickCommand`)."""

    def __init__(self, event_publisher: EventPublisherPort) -> None:
        self._event_publisher = event_publisher

    async def handle(self, command: TrackClickCommand) -> None:
        code = ShortCode(command.code)
        try:
            await self._event_publisher.publish(
                URLClicked(code=str(code), clicked_at=datetime.now(UTC))
            )
        except Exception:
            logger.warning("Falha ao publicar evento URLClicked para %s", code, exc_info=True)
