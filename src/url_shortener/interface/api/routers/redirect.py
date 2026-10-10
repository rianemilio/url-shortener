from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from url_shortener.application.commands.track_click import (
    TrackClickCommand,
    TrackClickCommandHandler,
)
from url_shortener.application.queries.get_original_url import (
    GetOriginalUrlQuery,
    GetOriginalUrlQueryHandler,
)
from url_shortener.domain.exceptions import InvalidShortCodeError, UrlNotFoundError
from url_shortener.interface.api.dependencies import (
    get_get_original_url_handler,
    get_track_click_handler,
)
from url_shortener.interface.api.rate_limit import (
    enforce_redirect_miss_limit,
    record_redirect_miss,
)

router = APIRouter(tags=["redirect"])


@router.get("/{code}", dependencies=[Depends(enforce_redirect_miss_limit)])
async def redirect_to_original_url(
    code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    handler: GetOriginalUrlQueryHandler = Depends(get_get_original_url_handler),
    track_click_handler: TrackClickCommandHandler = Depends(get_track_click_handler),
) -> RedirectResponse:
    try:
        original_url = await handler.handle(GetOriginalUrlQuery(code=code))
    except InvalidShortCodeError as error:
        # Fora do formato (/favicon.ico, /robots.txt, scanners): barrado antes do Mongo, então
        # não custa nada e não conta para o limite, que bloquearia crawlers legítimos à toa.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except UrlNotFoundError as error:
        # Cada código inexistente conta para o limite: é o rastro de quem varre códigos.
        await record_redirect_miss(request)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    # Roda depois que a resposta é enviada: o redirect não espera o RabbitMQ.
    background_tasks.add_task(track_click_handler.handle, TrackClickCommand(code=code))

    return RedirectResponse(url=str(original_url), status_code=status.HTTP_307_TEMPORARY_REDIRECT)
