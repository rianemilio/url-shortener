import pytest

from url_shortener.domain.services import base62, code_scrambler
from url_shortener.domain.value_objects.short_code import ShortCode

_KEY = b"chave-de-teste-com-16+-caracteres"
_MODULUS = 62**code_scrambler.CODE_LENGTH


def test_codes_have_fixed_length_and_are_valid_short_codes() -> None:
    for number in [0, 1, 2, 61, 62, 1_000_000, _MODULUS - 1]:
        code = code_scrambler.scramble(number, _KEY)
        assert len(code) == code_scrambler.CODE_LENGTH
        ShortCode(code)


@pytest.mark.parametrize(("left", "right"), [(6, 10), (10, 6), (62, 62**2)])
def test_feistel_is_a_bijection(left: int, right: int) -> None:
    # Exaustivo num domínio pequeno: a mesma construção usada em 62^3 x 62^4.
    images = {code_scrambler.feistel(n, _KEY, left, right) for n in range(left * right)}
    assert images == set(range(left * right))


def test_consecutive_numbers_produce_distinct_codes() -> None:
    codes = [code_scrambler.scramble(n, _KEY) for n in range(1, 10_001)]
    assert len(set(codes)) == len(codes)


def test_consecutive_codes_do_not_differ_by_a_constant() -> None:
    # Era a falha do embaralhamento linear: a diferença constante revelava o multiplicador.
    values = [base62.decode(code_scrambler.scramble(n, _KEY)) for n in range(1, 6)]
    differences = {(b - a) % _MODULUS for a, b in zip(values, values[1:], strict=False)}
    assert len(differences) == len(values) - 1


def test_different_keys_produce_different_codes() -> None:
    other_key = b"outra-chave-com-16+-caracteres"
    codes = [code_scrambler.scramble(n, _KEY) for n in range(1, 101)]
    other_codes = [code_scrambler.scramble(n, other_key) for n in range(1, 101)]
    assert sum(a == b for a, b in zip(codes, other_codes, strict=True)) <= 1


@pytest.mark.parametrize("number", [-1, _MODULUS])
def test_rejects_numbers_out_of_range(number: int) -> None:
    with pytest.raises(ValueError):
        code_scrambler.scramble(number, _KEY)
