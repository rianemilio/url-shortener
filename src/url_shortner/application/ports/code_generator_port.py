from typing import Protocol

from url_shortner.domain.value_objects.short_code import ShortCode


class CodeGeneratorPort(Protocol):
    async def next_code(self) -> ShortCode: ...
