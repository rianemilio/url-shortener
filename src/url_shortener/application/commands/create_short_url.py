import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from url_shortener.application.exceptions import ShortCodeConflictError
from url_shortener.application.ports.cache_port import CachePort
from url_shortener.application.ports.code_generator_port import CodeGeneratorPort
from url_shortener.application.ports.url_repository import UrlRepositoryPort
from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.exceptions import InvalidUrlError
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode

logger = logging.getLogger(__name__)

# Uma colisão já é improvável (só depois de trocar a chave ou resetar o contador); várias
# seguidas indicam contador dessincronizado, e insistir não resolveria.
_MAX_CODE_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class CreateShortUrlCommand:
    url: str


class CreateShortUrlCommandHandler:
    """Cria a URL curta. O evento `URLCreated` não é publicado aqui: o repositório o grava
    como pendente na mesma escrita, e o relay do outbox (no worker) o publica depois."""

    def __init__(
        self,
        url_repository: UrlRepositoryPort,
        cache: CachePort,
        code_generator: CodeGeneratorPort,
        blocked_hosts: Iterable[str] = (),
        reserved_codes: Iterable[str] = (),
    ) -> None:
        self._url_repository = url_repository
        self._cache = cache
        self._code_generator = code_generator
        self._blocked_hosts = frozenset(host.lower().rstrip(".") for host in blocked_hosts)
        self._reserved_codes = frozenset(reserved_codes)

    async def handle(self, command: CreateShortUrlCommand) -> ShortUrl:
        original_url = OriginalUrl(command.url)
        if original_url.host in self._blocked_hosts:
            # Encurtar um link do próprio encurtador só serve para esconder o destino real
            # atrás de uma cadeia de redirects (ou criar um loop).
            raise InvalidUrlError("Não é permitido encurtar links deste próprio encurtador")

        short_url = await self._save_with_fresh_code(original_url)

        try:
            await self._cache.set(short_url.code, original_url)
        except Exception:
            logger.warning("Falha ao popular cache para o código %s", short_url.code, exc_info=True)

        return short_url

    async def _save_with_fresh_code(self, original_url: OriginalUrl) -> ShortUrl:
        for attempt in range(1, _MAX_CODE_ATTEMPTS + 1):
            short_url = ShortUrl(
                code=await self._next_unreserved_code(),
                original_url=original_url,
                created_at=datetime.now(UTC),
            )
            try:
                await self._url_repository.save(short_url)
            except ShortCodeConflictError:
                logger.warning(
                    "Código %s já existe (tentativa %d de %d); gerando outro",
                    short_url.code,
                    attempt,
                    _MAX_CODE_ATTEMPTS,
                )
                continue
            return short_url

        logger.error(
            "%d códigos seguidos já existiam: o contador provavelmente está dessincronizado "
            "com a coleção de URLs",
            _MAX_CODE_ATTEMPTS,
        )
        raise ShortCodeConflictError("Não foi possível gerar um código curto livre")

    async def _next_unreserved_code(self) -> ShortCode:
        # Termina: o gerador nunca repete código, e os reservados são poucos e fixos.
        while True:
            code = await self._code_generator.next_code()
            if str(code) not in self._reserved_codes:
                return code
            logger.info("Código %s coincide com uma rota da API; gerando outro", code)
