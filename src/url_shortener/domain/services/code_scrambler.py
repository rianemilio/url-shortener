"""Embaralha o contador sequencial antes do base62 para que os códigos não sejam enumeráveis.

Usa uma rede de Feistel com chave secreta sobre o domínio exato [0, 62^CODE_LENGTH): é
uma bijeção (dois valores de contador nunca geram o mesmo código), mas, sem a chave,
conhecer alguns pares contador→código não ajuda a prever os outros. Uma função linear
como `n * K mod 62^7` não serve: dois códigos consecutivos diferem sempre por `K`, então
duas criações seguidas bastariam para enumerar todas as URLs.

Trocar a chave muda o mapeamento: códigos novos podem colidir com códigos antigos, o que
o caso de uso trata gerando outro código (ver `ShortCodeConflictError`).
"""

import hashlib
import hmac

from url_shortener.domain.services import base62

CODE_LENGTH = 7
_MODULUS = len(base62.ALPHABET) ** CODE_LENGTH
# 62^7 = 62^3 * 62^4: a Feistel desbalanceada alterna entre as duas metades, então cobre o
# domínio exato sem precisar de cycle-walking.
_LEFT_MODULUS = len(base62.ALPHABET) ** 3
_RIGHT_MODULUS = len(base62.ALPHABET) ** 4
# Par para terminar com as metades nos módulos de origem.
_ROUNDS = 8


def scramble(number: int, key: bytes) -> str:
    if not 0 <= number < _MODULUS:
        raise ValueError(f"contador fora do intervalo suportado [0, {_MODULUS})")
    permuted = feistel(number, key, _LEFT_MODULUS, _RIGHT_MODULUS)
    return base62.encode(permuted).rjust(CODE_LENGTH, base62.ALPHABET[0])


def feistel(number: int, key: bytes, left_modulus: int, right_modulus: int) -> int:
    """Permutação de [0, left_modulus * right_modulus). Exposta para os testes provarem a
    bijeção exaustivamente num domínio pequeno."""
    left, right = divmod(number, right_modulus)
    for round_index in range(_ROUNDS):
        # (L mod a, R mod b) -> (R mod b, (L + F(R)) mod a): os módulos trocam a cada rodada.
        left, right = right, (left + _round_function(key, round_index, right)) % left_modulus
        left_modulus, right_modulus = right_modulus, left_modulus
    return left * right_modulus + right


def _round_function(key: bytes, round_index: int, value: int) -> int:
    message = round_index.to_bytes(1, "big") + value.to_bytes(8, "big")
    return int.from_bytes(hmac.digest(key, message, hashlib.sha256)[:8], "big")
