from motor.motor_asyncio import AsyncIOMotorDatabase

from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.value_objects.short_code import ShortCode
from url_shortner.infrastructure.persistence.mongo.models import (
    URLS_COLLECTION,
    document_to_short_url,
    short_url_to_document,
)


class MongoUrlRepository:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database[URLS_COLLECTION]

    async def save(self, short_url: ShortUrl) -> None:
        await self._collection.insert_one(short_url_to_document(short_url))

    async def find_by_code(self, code: ShortCode) -> ShortUrl | None:
        document = await self._collection.find_one({"_id": str(code)})
        if document is None:
            return None
        return document_to_short_url(document)

    async def increment_clicks(self, code: ShortCode) -> None:
        await self._collection.update_one({"_id": str(code)}, {"$inc": {"click_count": 1}})
