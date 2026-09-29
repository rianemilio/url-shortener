"""Embaralha o contador sequencial antes do base62 para que os códigos não sejam enumeráveis.

`n -> n * MULTIPLIER mod 62^CODE_LENGTH` é uma bijeção porque MULTIPLIER é coprimo
com 62^CODE_LENGTH, então dois valores de contador nunca geram o mesmo código.
Não é criptografia: quem conhecer as constantes consegue inverter. O objetivo é só
impedir que `/1`, `/2`, `/3`... listem todas as URLs.
"""

from url_shortener.domain.services import base62

CODE_LENGTH = 7
_MODULUS = len(base62.ALPHABET) ** CODE_LENGTH
_MULTIPLIER = 2_176_477_521_739  # ~ razão áurea * _MODULUS, coprimo com _MODULUS


def scramble(number: int) -> str:
    if not 0 <= number < _MODULUS:
        raise ValueError(f"contador fora do intervalo suportado [0, {_MODULUS})")
    return base62.encode(number * _MULTIPLIER % _MODULUS).rjust(CODE_LENGTH, base62.ALPHABET[0])
