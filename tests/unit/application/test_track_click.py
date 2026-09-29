import pytest

from tests.fakes.fake_event_publisher import FakeEventPublisher
from url_shortener.application.commands.track_click import (
    TrackClickCommand,
    TrackClickCommandHandler,
)
from url_shortener.domain.events.url_clicked import URLClicked
from url_shortener.domain.events.url_created import URLCreated


class FailingEventPublisher:
    async def publish(self, event: URLCreated | URLClicked) -> None:
        raise ConnectionError("broker indisponível")


@pytest.mark.asyncio
async def test_publishes_url_clicked_event() -> None:
    publisher = FakeEventPublisher()
    handler = TrackClickCommandHandler(publisher)

    await handler.handle(TrackClickCommand(code="abc"))

    assert len(publisher.published) == 1
    assert isinstance(publisher.published[0], URLClicked)
    assert publisher.published[0].code == "abc"


@pytest.mark.asyncio
async def test_swallows_publisher_failure() -> None:
    handler = TrackClickCommandHandler(FailingEventPublisher())

    await handler.handle(TrackClickCommand(code="abc"))
