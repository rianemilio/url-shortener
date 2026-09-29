import asyncio

import httpx
import pytest
from asgi_lifespan import LifespanManager
from testcontainers.community.mongodb import MongoDbContainer
from testcontainers.community.rabbitmq import RabbitMqContainer
from testcontainers.community.redis import RedisContainer

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def containers():
    with (
        MongoDbContainer("mongo:7") as mongo,
        RedisContainer("redis:7-alpine") as redis,
        RabbitMqContainer("rabbitmq:3-management-alpine") as rabbitmq,
    ):
        yield {
            "mongo_uri": mongo.get_connection_url(),
            "redis_uri": f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
            "rabbitmq_uri": (
                f"amqp://{rabbitmq.username}:{rabbitmq.password}@"
                f"{rabbitmq.get_container_host_ip()}:{rabbitmq.get_exposed_port(rabbitmq.port)}/"
            ),
        }


@pytest.fixture
def _env(containers, monkeypatch):
    monkeypatch.setenv("APP_MONGO_URI", containers["mongo_uri"])
    monkeypatch.setenv("APP_REDIS_URI", containers["redis_uri"])
    monkeypatch.setenv("APP_RABBITMQ_URI", containers["rabbitmq_uri"])

    from url_shortner.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def app_client(_env):
    from url_shortner.interface.api.main import app

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def running_worker(_env):
    from url_shortner.interface.worker.click_consumer import run

    task = asyncio.create_task(run())
    await asyncio.sleep(1)
    yield
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.asyncio
async def test_create_and_redirect_flow(app_client: httpx.AsyncClient) -> None:
    create_response = await app_client.post("/urls", json={"url": "https://example.com/page"})
    assert create_response.status_code == 201
    code = create_response.json()["code"]

    redirect_response = await app_client.get(f"/{code}", follow_redirects=False)
    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == "https://example.com/page"


@pytest.mark.asyncio
async def test_click_count_incremented_by_worker(
    app_client: httpx.AsyncClient, running_worker, containers
) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    from url_shortner.config import Settings

    create_response = await app_client.post("/urls", json={"url": "https://example.com/worker"})
    code = create_response.json()["code"]

    await app_client.get(f"/{code}", follow_redirects=False)

    settings = Settings(mongo_uri=containers["mongo_uri"])
    mongo_client = AsyncIOMotorClient(settings.mongo_uri)
    collection = mongo_client[settings.mongo_db_name]["urls"]

    click_count = 0
    for _ in range(20):
        await asyncio.sleep(0.5)
        document = await collection.find_one({"_id": code})
        if document and document["click_count"] > 0:
            click_count = document["click_count"]
            break

    mongo_client.close()
    assert click_count == 1
