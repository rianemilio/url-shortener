from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from url_shortner.application.queries.get_original_url import (
    GetOriginalUrlQuery,
    GetOriginalUrlQueryHandler,
)
from url_shortner.domain.exceptions import InvalidShortCodeError, UrlNotFoundError
from url_shortner.interface.api.dependencies import get_get_original_url_handler

router = APIRouter(tags=["redirect"])


@router.get("/{code}")
async def redirect_to_original_url(
    code: str,
    handler: GetOriginalUrlQueryHandler = Depends(get_get_original_url_handler),
) -> RedirectResponse:
    try:
        original_url = await handler.handle(GetOriginalUrlQuery(code=code))
    except (InvalidShortCodeError, UrlNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return RedirectResponse(url=str(original_url), status_code=status.HTTP_307_TEMPORARY_REDIRECT)
