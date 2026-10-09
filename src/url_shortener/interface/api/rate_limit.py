import logging
from typing import Protocol

from fastapi import HTTPException, Request, status

from url_shortener.infrastructure.rate_limit.redis_rate_limiter import RateLimitDecision

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def hit(self, key: str) -> RateLimitDecision: ...


async def enforce_create_rate_limit(request: Request) -> None:
    """Limita criações por IP. Se o Redis falhar, deixa passar: ele é acessório, não crítico."""
    limiter: RateLimiter = request.app.state.container.create_rate_limiter
    # Atrás de um proxy reverso este é o IP do proxy; aí seria preciso confiar no X-Forwarded-For
    # (ex.: uvicorn --proxy-headers --forwarded-allow-ips).
    client_ip = request.client.host if request.client else "unknown"

    try:
        decision = await limiter.hit(client_ip)
    except Exception:
        logger.warning(
            "Falha no rate limit para %s; liberando a requisição", client_ip, exc_info=True
        )
        return

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de criação de URLs excedido, tente novamente mais tarde",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
