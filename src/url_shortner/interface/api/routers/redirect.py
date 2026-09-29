from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from url_shortner.application.commands.track_click import (
    TrackClickCommand,
    TrackClickCommandHandler,
)
from url_shortner.application.queries.get_original_url import (
    GetOriginalUrlQuery,
    GetOriginalUrlQueryHandler,
)
from url_shortner.domain.exceptions import InvalidShortCodeError, UrlNotFoundError
from url_shortner.interface.api.dependencies import (
    get_get_original_url_handler,
    get_track_click_handler,
)

router = APIRouter(tags=["redirect"])


@router.get("/{code}")
async def redirect_to_original_url(
    code: str,
    background_tasks: BackgroundTasks,
    handler: GetOriginalUrlQueryHandler = Depends(get_get_original_url_handler),
    track_click_handler: TrackClickCommandHandler = Depends(get_track_click_handler),
) -> RedirectResponse:
    try:
        original_url = await handler.handle(GetOriginalUrlQuery(code=code))
    except (InvalidShortCodeError, UrlNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    # Roda depois que a resposta é enviada: o redirect não espera o RabbitMQ.
    background_tasks.add_task(track_click_handler.handle, TrackClickCommand(code=code))

    return RedirectResponse(url=str(original_url), status_code=status.HTTP_307_TEMPORARY_REDIRECT)
