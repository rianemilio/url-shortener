from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, OriginalUrl] = {}

    async def get(self, code: ShortCode) -> OriginalUrl | None:
        return self.store.get(str(code))

    async def set(self, code: ShortCode, original_url: OriginalUrl) -> None:
        self.store[str(code)] = original_url
