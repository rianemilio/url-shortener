class StorageUnavailableError(Exception):
    """O armazenamento principal não respondeu; a operação pode dar certo se repetida."""
