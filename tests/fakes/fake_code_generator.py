from collections.abc import Iterable
from itertools import count

from url_shortener.domain.services import base62
from url_shortener.domain.value_objects.short_code import ShortCode


class FakeCodeGenerator:
    def __init__(self, start: int = 1) -> None:
        self._counter = count(start)

    async def next_code(self) -> ShortCode:
        return ShortCode(base62.encode(next(self._counter)))


class ScriptedCodeGenerator:
    """Devolve os códigos na ordem dada, para simular colisões."""

    def __init__(self, codes: Iterable[str]) -> None:
        self._codes = iter(codes)

    async def next_code(self) -> ShortCode:
        return ShortCode(next(self._codes))
