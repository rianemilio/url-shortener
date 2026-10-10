import httpx
import pytest
from fastapi import FastAPI

from url_shortener.application.exceptions import StorageUnavailableError
from url_shortener.interface.api.errors import register_error_handlers


@pytest.mark.asyncio
async def test_storage_unavailable_becomes_503_with_retry_after() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise StorageUnavailableError("MongoDB indisponível")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
