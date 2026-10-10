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


def reserved_codes(app: FastAPI) -> frozenset[str]:
    """Caminhos fixos de um segmento só (`/health`, `/urls`, `/docs`...).

    Essas rotas são casadas antes de `/{code}`, então um código curto igual a uma delas
    ficaria inacessível. Derivado das rotas registradas, cobre também as que vierem depois.

    As rotas dos routers incluídos vêm do schema OpenAPI (API pública): o FastAPI guarda
    esses routers em estruturas internas, sem `path`, em `app.routes`. As rotas que ficam
    fora do schema (`/docs`, `/redoc`) estão direto em `app.routes`. Uma rota futura com
    `include_in_schema=False` dentro de um router escaparia: o teste das rotas reservadas
    precisa ser atualizado junto.
    """
    paths = set(app.openapi()["paths"]) | {getattr(route, "path", "") for route in app.routes}
    return frozenset(
        path.strip("/")
        for path in paths
        if path.count("/") == 1 and len(path) > 1 and "{" not in path
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    metrics_server = MetricsServer(settings.metrics_port)
    app.state.metrics_server = metrics_server
    try:
        container = await ApiContainer.create(settings, reserved_codes=reserved_codes(app))
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
