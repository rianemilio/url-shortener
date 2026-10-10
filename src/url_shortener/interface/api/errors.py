import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from url_shortener.application.exceptions import StorageUnavailableError

logger = logging.getLogger(__name__)

_RETRY_AFTER_SECONDS = 5


async def _storage_unavailable(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("Armazenamento indisponível em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Serviço temporariamente indisponível, tente novamente"},
        headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
    )


def register_error_handlers(app: FastAPI) -> None:
    # 503 em vez de 500: sinaliza ao cliente que é transitório e vale tentar de novo.
    app.add_exception_handler(StorageUnavailableError, _storage_unavailable)
