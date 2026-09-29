from fastapi import Request

from url_shortener.application.commands.create_short_url import CreateShortUrlCommandHandler
from url_shortener.application.commands.track_click import TrackClickCommandHandler
from url_shortener.application.queries.get_original_url import GetOriginalUrlQueryHandler
from url_shortener.bootstrap.container import ApiContainer


def get_container(request: Request) -> ApiContainer:
    return request.app.state.container


def get_create_short_url_handler(request: Request) -> CreateShortUrlCommandHandler:
    return get_container(request).create_short_url_handler


def get_get_original_url_handler(request: Request) -> GetOriginalUrlQueryHandler:
    return get_container(request).get_original_url_handler


def get_track_click_handler(request: Request) -> TrackClickCommandHandler:
    return get_container(request).track_click_handler
