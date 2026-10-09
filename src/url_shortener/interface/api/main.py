from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from url_shortener.bootstrap.container import ApiContainer
from url_shortener.interface.api.routers import health, redirect, urls


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = await ApiContainer.create()
    app.state.container = container
    try:
        yield
    finally:
        await container.close()


app = FastAPI(title="URL Shortener", lifespan=lifespan)

# health antes do redirect: senão GET /health cairia em /{code}.
app.include_router(health.router)
app.include_router(urls.router)
app.include_router(redirect.router)
