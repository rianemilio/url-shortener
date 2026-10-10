import logging
from typing import Protocol

from fastapi import HTTPException, Request, status

from url_shortener.infrastructure.rate_limit.redis_rate_limiter import RateLimitDecision

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def hit(self, key: str) -> RateLimitDecision: ...

    async def peek(self, key: str) -> RateLimitDecision: ...


def client_ip(request: Request) -> str:
    # Atrás de um proxy reverso, o uvicorn só troca este IP pelo do X-Forwarded-For se o
    # proxy estiver em FORWARDED_ALLOW_IPS; sem isso, todos os clientes dividem um limite só.
    return request.client.host if request.client else "unknown"


async def enforce_create_rate_limit(request: Request) -> None:
    """Limita criações por IP. Se o Redis falhar, deixa passar: ele é acessório, não crítico."""
    limiter: RateLimiter = request.app.state.container.create_rate_limiter
    ip = client_ip(request)

    try:
        decision = await limiter.hit(ip)
    except Exception:
        logger.warning("Falha no rate limit para %s; liberando a requisição", ip, exc_info=True)
        return

    if not decision.allowed:
        _raise_too_many_requests(
            "Limite de criação de URLs excedido, tente novamente mais tarde", decision
        )


async def enforce_redirect_miss_limit(request: Request) -> None:
    """Bloqueia o redirect para quem já errou códigos demais, antes de consultar o Mongo.

    Só consulta o contador (os erros são contados em `record_redirect_miss`): quem acessa
    links válidos nunca é limitado, por mais tráfego que gere.
    """
    limiter: RateLimiter = request.app.state.container.redirect_miss_rate_limiter
    ip = client_ip(request)

    try:
        decision = await limiter.peek(ip)
    except Exception:
        logger.warning("Falha no rate limit para %s; liberando a requisição", ip, exc_info=True)
        return

    if not decision.allowed:
        _raise_too_many_requests(
            "Muitos códigos inexistentes, tente novamente mais tarde", decision
        )


async def record_redirect_miss(request: Request) -> None:
    limiter: RateLimiter = request.app.state.container.redirect_miss_rate_limiter
    ip = client_ip(request)
    try:
        await limiter.hit(ip)
    except Exception:
        logger.warning("Falha ao contabilizar código inexistente para %s", ip, exc_info=True)


def _raise_too_many_requests(detail: str, decision: RateLimitDecision) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )
