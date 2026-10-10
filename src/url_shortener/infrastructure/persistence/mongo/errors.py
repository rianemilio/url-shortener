from collections.abc import Iterator
from contextlib import contextmanager

from pymongo.errors import ConnectionFailure

from url_shortener.application.exceptions import StorageUnavailableError


@contextmanager
def translate_connection_errors() -> Iterator[None]:
    """Converte falhas de conexão do pymongo no erro da aplicação, para as camadas de cima
    não dependerem do driver."""
    try:
        yield
    except ConnectionFailure as error:
        raise StorageUnavailableError("MongoDB indisponível") from error
