import pytest

from url_shortener.domain.services import code_scrambler
from url_shortener.domain.value_objects.short_code import ShortCode


def test_codes_have_fixed_length_and_are_valid_short_codes() -> None:
    for number in [0, 1, 2, 61, 62, 1_000_000]:
        code = code_scrambler.scramble(number)
        assert len(code) == code_scrambler.CODE_LENGTH
        ShortCode(code)


def test_consecutive_numbers_produce_distinct_codes() -> None:
    codes = [code_scrambler.scramble(n) for n in range(1, 10_001)]
    assert len(set(codes)) == len(codes)


def test_consecutive_numbers_do_not_produce_consecutive_codes() -> None:
    first, second = code_scrambler.scramble(1), code_scrambler.scramble(2)
    assert first[:-1] != second[:-1]


@pytest.mark.parametrize("number", [-1, 62**code_scrambler.CODE_LENGTH])
def test_rejects_numbers_out_of_range(number: int) -> None:
    with pytest.raises(ValueError):
        code_scrambler.scramble(number)
