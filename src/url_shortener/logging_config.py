import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    """Configura o logger raiz. Sem isso, na API os loggers da aplicação caem no handler
    de último recurso do Python, que só mostra WARNING para cima."""
    logging.basicConfig(level=level.upper(), format=_FORMAT)
