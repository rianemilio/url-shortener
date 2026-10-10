import ipaddress
import logging
from typing import Protocol

from fastapi import HTTPException, Request, status

from url_shortener.infrastructure.rate_limit.redis_rate_limiter import RateLimitDecision
from url_shortener.metrics import RATE_LIMITED

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def hit(self, key: str) -> RateLimitDecision: ...

    async def peek(self, key: str) -> RateLimitDecision: ...


def client_key(request: Request) -> str:
    """Chave do cliente nos rate limits: o IPv4, ou o /64 do IPv6.

    Um /64 é o que um provedor entrega a um único cliente, que pode trocar de endereço dentro
    dele à vontade; limitar por endereço IPv6 individual não limitaria ninguém.
    """
    # Atrás de um proxy reverso, o uvicorn só troca este IP pelo do X-Forwarded-For se o
    # proxy estiver em FORWARDED_ALLOW_IPS; sem isso, todos os clientes dividem um limite só.
    host = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return host


async def enforce_create_rate_limit(request: Request) -> None:
    """Limita criações por IP. Se o Redis falhar, deixa passar: ele é acessório, não crítico."""
    limiter: RateLimiter = request.app.state.container.create_rate_limiter
    key = client_key(request)

    try:
        decision = await limiter.hit(key)
    except Exception:
        logger.warning("Falha no rate limit para %s; liberando a requisição", key, exc_info=True)
        return

    if not decision.allowed:
        _raise_too_many_requests(
            "create_url", "Limite de criação de URLs excedido, tente novamente mais tarde", decision
        )


async def enforce_redirect_miss_limit(request: Request) -> None:
    """Bloqueia o redirect para quem já errou códigos demais, antes de consultar o Mongo.

    Só consulta o contador (os erros são contados em `record_redirect_miss`): quem acessa
    links válidos nunca é limitado, por mais tráfego que gere.
    """
    limiter: RateLimiter = request.app.state.container.redirect_miss_rate_limiter
    key = client_key(request)

    try:
        decision = await limiter.peek(key)
    except Exception:
        logger.warning("Falha no rate limit para %s; liberando a requisição", key, exc_info=True)
        return

    if not decision.allowed:
        _raise_too_many_requests(
            "redirect_miss", "Muitos códigos inexistentes, tente novamente mais tarde", decision
        )


async def record_redirect_miss(request: Request) -> None:
    limiter: RateLimiter = request.app.state.container.redirect_miss_rate_limiter
    key = client_key(request)
    try:
        await limiter.hit(key)
    except Exception:
        logger.warning("Falha ao contabilizar código inexistente para %s", key, exc_info=True)


def _raise_too_many_requests(scope: str, detail: str, decision: RateLimitDecision) -> None:
    RATE_LIMITED.labels(scope).inc()
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )
