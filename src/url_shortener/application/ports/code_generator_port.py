from typing import Protocol

from url_shortener.domain.value_objects.short_code import ShortCode


class CodeGeneratorPort(Protocol):
    async def next_code(self) -> ShortCode: ...
