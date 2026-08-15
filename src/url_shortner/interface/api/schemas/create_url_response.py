from datetime import datetime

from pydantic import BaseModel


class CreateUrlResponse(BaseModel):
    code: str
    short_url: str
    original_url: str
    created_at: datetime
