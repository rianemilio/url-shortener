import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response, status

from url_shortener.bootstrap.container import ApiContainer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

_CHECK_TIMEOUT_SECONDS = 2.0


@router.get("")
async def liveness() -> dict[str, str]:
    """Liveness: o processo está de pé. Não toca dependências, para o orquestrador não
    reiniciar a API só porque o Mongo caiu."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request, response: Response) -> dict[str, object]:
    """Readiness: só o Mongo é obrigatório. Sem Redis ou RabbitMQ a API funciona
    (sem cache, sem rate limit, sem eventos), então responde 200 com status `degraded`."""
    container: ApiContainer = request.app.state.container

    mongo_ok, redis_ok = await asyncio.gather(
        _check("mongo", lambda: container.mongo_client.admin.command("ping")),
        _check("redis", lambda: container.redis_client.ping()),
    )
    rabbitmq_ok = container.event_publisher.is_connected

    if not mongo_ok:
        status_text = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif not (redis_ok and rabbitmq_ok):
        status_text = "degraded"
    else:
        status_text = "ok"

    return {
        "status": status_text,
        "checks": {
            "mongo": _label(mongo_ok),
            "redis": _label(redis_ok),
            "rabbitmq": _label(rabbitmq_ok),
        },
    }


async def _check(name: str, probe: Callable[[], Awaitable[object]]) -> bool:
    try:
        await asyncio.wait_for(probe(), timeout=_CHECK_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("Health check falhou para %s", name, exc_info=True)
        return False
    return True


def _label(ok: bool) -> str:
    return "ok" if ok else "error"
