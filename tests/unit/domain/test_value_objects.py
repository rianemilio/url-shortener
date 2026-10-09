import pytest

from url_shortener.domain.exceptions import InvalidShortCodeError, InvalidUrlError
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode


@pytest.mark.parametrize(
    "value",
    ["https://example.com", "http://example.com/path?x=1", "https://example.com/users/@handle"],
)
def test_original_url_accepts_http_and_https(value: str) -> None:
    assert str(OriginalUrl(value)) == value


@pytest.mark.parametrize(
    "value",
    [
        "ftp://example.com",
        "not-a-url",
        "javascript:alert(1)",
        "https://",
        "",
        "https://google.com@evil.com",
        "https://user:pass@example.com",
        "https://:pass@example.com",
    ],
)
def test_original_url_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidUrlError):
        OriginalUrl(value)


def test_original_url_rejects_values_over_max_length() -> None:
    too_long = "https://example.com/" + ("a" * 2048)
    with pytest.raises(InvalidUrlError):
        OriginalUrl(too_long)


@pytest.mark.parametrize("value", ["a", "b7F3", "0123456789"])
def test_short_code_accepts_base62_values(value: str) -> None:
    assert str(ShortCode(value)) == value


@pytest.mark.parametrize("value", ["", "has space", "has-dash", "a" * 11, "áéíóú"])
def test_short_code_rejects_invalid_values(value: str) -> None:
    with pytest.raises(InvalidShortCodeError):
        ShortCode(value)
