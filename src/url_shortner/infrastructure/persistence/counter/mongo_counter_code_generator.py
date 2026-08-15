from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from url_shortner.domain.services import base62
from url_shortner.domain.value_objects.short_code import ShortCode
from url_shortner.infrastructure.persistence.mongo.models import (
    COUNTERS_COLLECTION,
    SHORT_URL_SEQUENCE_ID,
)


class MongoCounterCodeGenerator:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection = database[COUNTERS_COLLECTION]

    async def next_code(self) -> ShortCode:
        document = await self._collection.find_one_and_update(
            {"_id": SHORT_URL_SEQUENCE_ID},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return ShortCode(base62.encode(document["seq"]))
