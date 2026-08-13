import re
from dataclasses import dataclass

from url_shortner.domain.exceptions import InvalidShortCodeError

_SHORT_CODE_PATTERN = re.compile(r"^[0-9A-Za-z]{1,10}$")


@dataclass(frozen=True, slots=True)
class ShortCode:
    value: str

    def __post_init__(self) -> None:
        if not _SHORT_CODE_PATTERN.match(self.value):
            raise InvalidShortCodeError(f"Código curto inválido: {self.value!r}")

    def __str__(self) -> str:
        return self.value
