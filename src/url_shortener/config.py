from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    mongo_uri: str = "mongodb://mongo:27017"
    mongo_db_name: str = "url_shortener"

    redis_uri: str = "redis://redis:6379/0"
    redis_cache_ttl_seconds: int = 3600

    rabbitmq_uri: str = "amqp://guest:guest@rabbitmq:5672/"

    base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
