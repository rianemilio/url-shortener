from motor.motor_asyncio import AsyncIOMotorDatabase

from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.value_objects.short_code import ShortCode
from url_shortener.infrastructure.persistence.mongo.errors import (
    translate_connection_errors,
    translate_duplicate_code,
)
from url_shortener.infrastructure.persistence.mongo.models import (
    URLS_COLLECTION,
    document_to_short_url,
    short_url_to_document,
)


class MongoUrlRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database[URLS_COLLECTION]

    async def save(self, short_url: ShortUrl) -> None:
        # O documento já sai com a marca de URLCreated pendente (ver models.py).
        with translate_connection_errors(), translate_duplicate_code():
            await self._collection.insert_one(short_url_to_document(short_url))

    async def find_by_code(self, code: ShortCode) -> ShortUrl | None:
        with translate_connection_errors():
            document = await self._collection.find_one({"_id": str(code)})
        if document is None:
            return None
        return document_to_short_url(document)

    async def increment_clicks(self, code: ShortCode) -> None:
        with translate_connection_errors():
            await self._collection.update_one({"_id": str(code)}, {"$inc": {"click_count": 1}})
