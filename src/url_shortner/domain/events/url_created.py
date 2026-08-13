from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class URLCreated:
    code: str
    original_url: str
    created_at: datetime

    ROUTING_KEY = "url.created"
