import httpx
import pytest
from fastapi import FastAPI

from url_shortener.interface.api.routers import health


class FakeMongoAdmin:
    def __init__(self, healthy: bool) -> None:
        self._healthy = healthy

    async def command(self, name: str) -> dict[str, int]:
        if not self._healthy:
            raise ConnectionError("mongo indisponível")
        return {"ok": 1}


class FakeMongoClient:
    def __init__(self, healthy: bool) -> None:
        self.admin = FakeMongoAdmin(healthy)


class FakeRedisClient:
    def __init__(self, healthy: bool) -> None:
        self._healthy = healthy

    async def ping(self) -> bool:
        if not self._healthy:
            raise ConnectionError("redis indisponível")
        return True


class FakeEventPublisher:
    def __init__(self, connected: bool) -> None:
        self.is_connected = connected


class FakeApiContainer:
    def __init__(self, mongo: bool = True, redis: bool = True, rabbitmq: bool = True) -> None:
        self.mongo_client = FakeMongoClient(mongo)
        self.redis_client = FakeRedisClient(redis)
        self.event_publisher = FakeEventPublisher(rabbitmq)


async def _get(path: str, container: FakeApiContainer) -> httpx.Response:
    app = FastAPI()
    app.include_router(health.router)
    app.state.container = container
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_infrastructure() -> None:
    response = await _get("/health", FakeApiContainer(mongo=False, redis=False, rabbitmq=False))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_when_all_dependencies_are_up() -> None:
    response = await _get("/health/ready", FakeApiContainer())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"mongo": "ok", "redis": "ok", "rabbitmq": "ok"},
    }


@pytest.mark.parametrize(
    ("container", "failed"),
    [(FakeApiContainer(redis=False), "redis"), (FakeApiContainer(rabbitmq=False), "rabbitmq")],
)
@pytest.mark.asyncio
async def test_degraded_but_ready_without_optional_dependency(
    container: FakeApiContainer, failed: str
) -> None:
    response = await _get("/health/ready", container)

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"][failed] == "error"


@pytest.mark.asyncio
async def test_not_ready_without_mongo() -> None:
    response = await _get("/health/ready", FakeApiContainer(mongo=False))

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["mongo"] == "error"
