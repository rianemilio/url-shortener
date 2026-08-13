from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class URLClicked:
    code: str
    clicked_at: datetime

    ROUTING_KEY = "url.clicked"
