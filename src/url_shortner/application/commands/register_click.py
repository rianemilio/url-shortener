from dataclasses import dataclass

from url_shortner.application.ports.url_repository import UrlRepositoryPort
from url_shortner.domain.value_objects.short_code import ShortCode


@dataclass(frozen=True, slots=True)
class RegisterClickCommand:
    code: str


class RegisterClickCommandHandler:
    def __init__(self, url_repository: UrlRepositoryPort) -> None:
        self._url_repository = url_repository

    async def handle(self, command: RegisterClickCommand) -> None:
        await self._url_repository.increment_clicks(ShortCode(command.code))
