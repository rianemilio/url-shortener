import pytest

from url_shortener.domain.services import base62


@pytest.mark.parametrize(
    "number",
    [0, 1, 61, 62, 63, 3843, 1_000_000, 218_340_105_584_895],
)
def test_encode_decode_round_trip(number: int) -> None:
    assert base62.decode(base62.encode(number)) == number


def test_encode_zero_returns_first_alphabet_char() -> None:
    assert base62.encode(0) == "0"


def test_encode_is_monotonically_increasing_in_length_or_value() -> None:
    codes = [base62.encode(n) for n in range(0, 200)]
    assert len(codes) == len(set(codes))


def test_encode_rejects_negative_numbers() -> None:
    with pytest.raises(ValueError):
        base62.encode(-1)
