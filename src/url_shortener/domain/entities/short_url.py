from dataclasses import dataclass
from datetime import datetime

from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode


@dataclass(frozen=True, slots=True)
class ShortUrl:
    code: ShortCode
    original_url: OriginalUrl
    created_at: datetime
    click_count: int = 0
