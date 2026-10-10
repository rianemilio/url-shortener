from typing import Any

from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.events.url_created import URLCreated
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode

URLS_COLLECTION = "urls"
COUNTERS_COLLECTION = "counters"
SHORT_URL_SEQUENCE_ID = "short_url_seq"

# Outbox embutido no próprio documento da URL: o Mongo garante atomicidade por documento
# sem precisar de transação (que exigiria replica set). Só existe enquanto o evento não foi
# publicado; o relay remove o campo depois do publish.
URL_CREATED_PENDING_FIELD = "url_created_pending"


def short_url_to_document(short_url: ShortUrl) -> dict[str, Any]:
    return {
        "_id": str(short_url.code),
        "original_url": str(short_url.original_url),
        "created_at": short_url.created_at,
        "click_count": short_url.click_count,
        URL_CREATED_PENDING_FIELD: True,
    }


def document_to_short_url(document: dict[str, Any]) -> ShortUrl:
    return ShortUrl(
        code=ShortCode(document["_id"]),
        original_url=OriginalUrl(document["original_url"]),
        created_at=document["created_at"],
        click_count=document["click_count"],
    )


def document_to_url_created(document: dict[str, Any]) -> URLCreated:
    # O evento é derivado do estado gravado: não há payload duplicado para divergir.
    return URLCreated(
        code=document["_id"],
        original_url=document["original_url"],
        created_at=document["created_at"],
    )
