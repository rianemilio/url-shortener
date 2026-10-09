from fastapi import APIRouter, Depends, HTTPException, Request, status

from url_shortener.application.commands.create_short_url import (
    CreateShortUrlCommand,
    CreateShortUrlCommandHandler,
)
from url_shortener.domain.exceptions import InvalidUrlError
from url_shortener.interface.api.dependencies import get_create_short_url_handler
from url_shortener.interface.api.rate_limit import enforce_create_rate_limit
from url_shortener.interface.api.schemas.create_url_request import CreateUrlRequest
from url_shortener.interface.api.schemas.create_url_response import CreateUrlResponse

router = APIRouter(tags=["urls"])


@router.post(
    "/urls",
    response_model=CreateUrlResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_create_rate_limit)],
)
async def create_short_url(
    body: CreateUrlRequest,
    request: Request,
    handler: CreateShortUrlCommandHandler = Depends(get_create_short_url_handler),
) -> CreateUrlResponse:
    try:
        short_url = await handler.handle(CreateShortUrlCommand(url=body.url))
    except InvalidUrlError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    base_url = request.app.state.container.settings.base_url.rstrip("/")
    return CreateUrlResponse(
        code=str(short_url.code),
        short_url=f"{base_url}/{short_url.code}",
        original_url=str(short_url.original_url),
        created_at=short_url.created_at,
    )
