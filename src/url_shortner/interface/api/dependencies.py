from fastapi import Request

from url_shortner.application.commands.create_short_url import CreateShortUrlCommandHandler
from url_shortner.application.queries.get_original_url import GetOriginalUrlQueryHandler
from url_shortner.bootstrap.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_create_short_url_handler(request: Request) -> CreateShortUrlCommandHandler:
    return get_container(request).create_short_url_handler


def get_get_original_url_handler(request: Request) -> GetOriginalUrlQueryHandler:
    return get_container(request).get_original_url_handler
