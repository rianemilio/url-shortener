from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.value_objects.short_code import ShortCode


class FakeUrlRepository:
    def __init__(self) -> None:
        self.saved: dict[str, ShortUrl] = {}

    async def save(self, short_url: ShortUrl) -> None:
        self.saved[str(short_url.code)] = short_url

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
