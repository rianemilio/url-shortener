from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from url_shortner.bootstrap.container import Container
from url_shortner.interface.api.routers import redirect, urls


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = await Container.create()
    app.state.container = container
    try:
        yield
    finally:
        await container.close()


app = FastAPI(title="URL Shortner", lifespan=lifespan)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(urls.router)
app.include_router(redirect.router)
