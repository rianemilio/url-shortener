from typing import Protocol

from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.value_objects.short_code import ShortCode


class UrlRepositoryPort(Protocol):
    async def save(self, short_url: ShortUrl) -> None:
        """Persiste a URL e, na mesma escrita atômica, marca `URLCreated` como pendente de
        publicação (outbox). Levanta `ShortCodeConflictError` se o código já existir."""
        ...

    async def find_by_code(self, code: ShortCode) -> ShortUrl | None: ...

    async def increment_clicks(self, code: ShortCode) -> None: ...
