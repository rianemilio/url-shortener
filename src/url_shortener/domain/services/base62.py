ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_BASE = len(ALPHABET)


def encode(number: int) -> str:
    if number < 0:
        raise ValueError("base62 encode requires a non-negative integer")
    if number == 0:
        return ALPHABET[0]

    digits: list[str] = []
    while number:
        number, remainder = divmod(number, _BASE)
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def decode(code: str) -> int:
    number = 0
    for char in code:
        number = number * _BASE + ALPHABET.index(char)
    return number
