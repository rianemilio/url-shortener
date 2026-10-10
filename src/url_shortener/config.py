from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    mongo_uri: str = "mongodb://mongo:27017"
    mongo_db_name: str = "url_shortener"
    mongo_timeout_ms: int = 2000

    redis_uri: str = "redis://redis:6379/0"
    redis_cache_ttl_seconds: int = 3600
    redis_timeout_seconds: float = 0.5

    rabbitmq_uri: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_timeout_seconds: float = 2.0
    rabbitmq_reconnect_interval_seconds: float = 5.0

    rate_limit_create_requests: int = 20
    rate_limit_create_window_seconds: int = 60
    # Conta só os redirects que dão 404: quem varre códigos erra quase sempre.
    rate_limit_redirect_miss_requests: int = 30
    rate_limit_redirect_miss_window_seconds: int = 60

    # Chave da permutação que embaralha o contador (`domain/services/code_scrambler.py`).
    # Sem default de propósito: uma chave conhecida tornaria os códigos enumeráveis.
    code_secret: SecretStr = Field(min_length=16)

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 100

    # Porta do servidor de métricas (API e worker, cada um no seu container).
    metrics_port: int = 9100
    # O worker toca este arquivo enquanto está saudável; o healthcheck confere a idade dele.
    worker_heartbeat_file: str = "/tmp/url-shortener-worker.heartbeat"
    worker_heartbeat_interval_seconds: float = 10.0

    base_url: str = "http://localhost:8000"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    # code_secret vem do ambiente; o mypy não sabe disso e cobraria o argumento.
    return Settings()  # type: ignore[call-arg]
