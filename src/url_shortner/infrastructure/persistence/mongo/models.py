from typing import Any

from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode

URLS_COLLECTION = "urls"
COUNTERS_COLLECTION = "counters"
SHORT_URL_SEQUENCE_ID = "short_url_seq"


def short_url_to_document(short_url: ShortUrl) -> dict[str, Any]:
    return {
        "_id": str(short_url.code),
        "original_url": str(short_url.original_url),
        "created_at": short_url.created_at,
        "click_count": short_url.click_count,
    }


def document_to_short_url(document: dict[str, Any]) -> ShortUrl:
    return ShortUrl(
        code=ShortCode(document["_id"]),
        original_url=OriginalUrl(document["original_url"]),
        created_at=document["created_at"],
        click_count=document["click_count"],
    )
