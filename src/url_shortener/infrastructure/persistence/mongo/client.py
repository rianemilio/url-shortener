from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from url_shortener.config import Settings


def create_mongo_client(settings: Settings) -> AsyncIOMotorClient:
    # O padrão do driver é esperar até 30s por um servidor disponível.
    return AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=settings.mongo_timeout_ms,
        connectTimeoutMS=settings.mongo_timeout_ms,
        socketTimeoutMS=settings.mongo_timeout_ms,
        # Datas voltam com fuso (UTC), iguais às que o domínio grava com datetime.now(UTC).
        tz_aware=True,
    )


def get_database(client: AsyncIOMotorClient, settings: Settings) -> AsyncIOMotorDatabase:
    return client[settings.mongo_db_name]
