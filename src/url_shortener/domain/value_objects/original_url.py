from dataclasses import dataclass
from urllib.parse import urlparse

from url_shortener.domain.exceptions import InvalidUrlError

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_LENGTH = 2048


@dataclass(frozen=True, slots=True)
class OriginalUrl:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) > _MAX_LENGTH:
            raise InvalidUrlError(f"URL excede o tamanho máximo de {_MAX_LENGTH} caracteres")

        parsed = urlparse(self.value)
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
            raise InvalidUrlError(f"URL inválida: {self.value!r}")

        # Truque de phishing: em https://google.com@evil.com o host real é evil.com.
        if parsed.username is not None or parsed.password is not None:
            raise InvalidUrlError("URLs com credenciais (usuário@host) não são permitidas")

    @property
    def host(self) -> str:
        """Hostname normalizado (minúsculo, sem porta e sem o ponto final de FQDN)."""
        return (urlparse(self.value).hostname or "").rstrip(".")

    def __str__(self) -> str:
        return self.value
