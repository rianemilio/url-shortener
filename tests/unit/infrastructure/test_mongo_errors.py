import pytest
from pymongo.errors import DuplicateKeyError, NetworkTimeout, ServerSelectionTimeoutError

from url_shortener.application.exceptions import ShortCodeConflictError, StorageUnavailableError
from url_shortener.infrastructure.persistence.mongo.errors import (
    translate_connection_errors,
    translate_duplicate_code,
)


@pytest.mark.parametrize(
    "error", [ServerSelectionTimeoutError("sem servidor"), NetworkTimeout("timeout")]
)
def test_translates_connection_failures(error: Exception) -> None:
    with pytest.raises(StorageUnavailableError) as raised, translate_connection_errors():
        raise error

    assert raised.value.__cause__ is error


def test_leaves_other_errors_untouched() -> None:
    with pytest.raises(DuplicateKeyError), translate_connection_errors():
        raise DuplicateKeyError("duplicado")


def test_translates_duplicate_key_into_code_conflict() -> None:
    error = DuplicateKeyError("duplicado")
    with pytest.raises(ShortCodeConflictError) as raised, translate_duplicate_code():
        raise error

    assert raised.value.__cause__ is error
