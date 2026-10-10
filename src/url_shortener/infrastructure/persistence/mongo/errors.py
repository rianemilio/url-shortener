from collections.abc import Iterator
from contextlib import contextmanager

from pymongo.errors import ConnectionFailure, DuplicateKeyError

from url_shortener.application.exceptions import ShortCodeConflictError, StorageUnavailableError


@contextmanager
def translate_connection_errors() -> Iterator[None]:
    """Converte falhas de conexão do pymongo no erro da aplicação, para as camadas de cima
    não dependerem do driver."""
    try:
        yield
    except ConnectionFailure as error:
        raise StorageUnavailableError("MongoDB indisponível") from error


@contextmanager
def translate_duplicate_code() -> Iterator[None]:
    """Converte `_id` duplicado na coleção de URLs no conflito de código da aplicação."""
    try:
        yield
    except DuplicateKeyError as error:
        raise ShortCodeConflictError("Código curto já existe") from error
