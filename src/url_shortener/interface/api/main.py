from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from url_shortener.bootstrap.container import ApiContainer
from url_shortener.config import get_settings
from url_shortener.interface.api.errors import register_error_handlers
from url_shortener.interface.api.metrics import HttpMetricsMiddleware
from url_shortener.interface.api.routers import health, redirect, urls
from url_shortener.logging_config import configure_logging
from url_shortener.metrics import MetricsServer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    metrics_server = MetricsServer(settings.metrics_port)
    app.state.metrics_server = metrics_server
    try:
        container = await ApiContainer.create(settings)
        app.state.container = container
        try:
            yield
        finally:
            await container.close()
    finally:
        metrics_server.close()


app = FastAPI(title="URL Shortener", lifespan=lifespan)
app.add_middleware(HttpMetricsMiddleware)
register_error_handlers(app)

# health antes do redirect: senão GET /health cairia em /{code}.
app.include_router(health.router)
app.include_router(urls.router)
app.include_router(redirect.router)
