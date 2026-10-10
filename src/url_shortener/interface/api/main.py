from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from url_shortener.bootstrap.container import ApiContainer
from url_shortener.config import get_settings
from url_shortener.interface.api.errors import register_error_handlers
from url_shortener.interface.api.routers import health, redirect, urls
from url_shortener.logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    container = await ApiContainer.create(settings)
    app.state.container = container
    try:
        yield
    finally:
        await container.close()


app = FastAPI(title="URL Shortener", lifespan=lifespan)
register_error_handlers(app)

# health antes do redirect: senão GET /health cairia em /{code}.
app.include_router(health.router)
app.include_router(urls.router)
app.include_router(redirect.router)
