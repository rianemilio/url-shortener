from motor.motor_asyncio import AsyncIOMotorDatabase

from url_shortener.domain.events.url_created import URLCreated
from url_shortener.infrastructure.persistence.mongo.errors import translate_connection_errors
from url_shortener.infrastructure.persistence.mongo.models import (
    URL_CREATED_PENDING_FIELD,
    URLS_COLLECTION,
    document_to_url_created,
)

_PENDING_FILTER = {URL_CREATED_PENDING_FIELD: True}


class MongoUrlCreatedOutbox:
    """Lê e confirma os `URLCreated` pendentes gravados nos documentos da coleção de URLs."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database[URLS_COLLECTION]

    async def ensure_indexes(self) -> None:
        # Índice parcial: só os (poucos) documentos pendentes entram nele, então a consulta
        # do relay não varre a coleção inteira e o índice não cresce com o histórico.
        with translate_connection_errors():
            await self._collection.create_index(
                [(URL_CREATED_PENDING_FIELD, 1), ("created_at", 1)],
                name="url_created_pending",
                partialFilterExpression=_PENDING_FILTER,
            )

    async def pending(self, limit: int) -> list[URLCreated]:
        with translate_connection_errors():
            cursor = self._collection.find(_PENDING_FILTER).sort("created_at", 1).limit(limit)
            return [document_to_url_created(document) async for document in cursor]

    async def mark_published(self, event: URLCreated) -> None:
        with translate_connection_errors():
            await self._collection.update_one(
                {"_id": event.code}, {"$unset": {URL_CREATED_PENDING_FIELD: ""}}
            )
