class StorageUnavailableError(Exception):
    """O armazenamento principal não respondeu; a operação pode dar certo se repetida."""


class ShortCodeConflictError(Exception):
    """O código gerado já pertence a outra URL.

    Não acontece em operação normal (o contador só cresce e a permutação é uma bijeção),
    mas acontece se a chave do embaralhamento mudar ou o contador for resetado.
    """
