from pydantic import BaseModel


class CreateUrlRequest(BaseModel):
    url: str
