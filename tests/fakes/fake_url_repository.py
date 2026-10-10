from url_shortener.application.exceptions import ShortCodeConflictError
from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.events.url_created import URLCreated
from url_shortener.domain.value_objects.short_code import ShortCode


class FakeUrlRepository:
    """Implementa o repositório e o outbox, como o Mongo (os dois na mesma coleção)."""

    def __init__(self) -> None:
        self.saved: dict[str, ShortUrl] = {}
        self.pending_codes: list[str] = []

    async def save(self, short_url: ShortUrl) -> None:
        if str(short_url.code) in self.saved:
            raise ShortCodeConflictError("Código curto já existe")
        self.saved[str(short_url.code)] = short_url
        self.pending_codes.append(str(short_url.code))

    async def find_by_code(self, code: ShortCode) -> ShortUrl | None:
        return self.saved.get(str(code))

    async def increment_clicks(self, code: ShortCode) -> None:
        existing = self.saved.get(str(code))
        if existing is not None:
            self.saved[str(code)] = ShortUrl(
                code=existing.code,
                original_url=existing.original_url,
                created_at=existing.created_at,
                click_count=existing.click_count + 1,
            )

    async def pending(self, limit: int) -> list[URLCreated]:
        return [
            URLCreated(
                code=code,
                original_url=str(self.saved[code].original_url),
                created_at=self.saved[code].created_at,
            )
            for code in self.pending_codes[:limit]
        ]

    async def mark_published(self, event: URLCreated) -> None:
        self.pending_codes.remove(event.code)

    async def ensure_indexes(self) -> None:
        """No Mongo cria o índice do outbox; aqui não há o que fazer."""

    async def count_pending(self) -> int:
        return len(self.pending_codes)
