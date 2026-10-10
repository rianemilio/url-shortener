from url_shortener.application.ports.event_publisher_port import DomainEvent


class FakeEventPublisher:
    def __init__(self, fail_after: int | None = None) -> None:
        self.published: list[DomainEvent] = []
        self._fail_after = fail_after

    async def publish(self, event: DomainEvent) -> None:
        if self._fail_after is not None and len(self.published) >= self._fail_after:
            raise ConnectionError("broker indisponível")
        self.published.append(event)
