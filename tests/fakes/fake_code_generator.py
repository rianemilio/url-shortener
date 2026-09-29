from itertools import count

from url_shortener.domain.services import base62
from url_shortener.domain.value_objects.short_code import ShortCode


class FakeCodeGenerator:
    def __init__(self, start: int = 1) -> None:
        self._counter = count(start)

    async def next_code(self) -> ShortCode:
        return ShortCode(base62.encode(next(self._counter)))
