from typing import Protocol

from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode


class CachePort(Protocol):
    async def get(self, code: ShortCode) -> OriginalUrl | None: ...

    async def set(self, code: ShortCode, original_url: OriginalUrl) -> None: ...
