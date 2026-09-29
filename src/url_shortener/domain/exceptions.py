class DomainError(Exception):
    """Base para todos os erros de domínio."""


class InvalidUrlError(DomainError):
    """URL original não passa nas regras de validação do domínio."""


class InvalidShortCodeError(DomainError):
    """Código curto não segue o formato base62 esperado."""


class UrlNotFoundError(DomainError):
    """Nenhuma URL encontrada para o código curto informado."""
