import asyncio
import contextlib
import logging
from pathlib import Path

from url_shortener.bootstrap.container import WorkerContainer
from url_shortener.metrics import OUTBOX_PENDING

logger = logging.getLogger(__name__)


async def run_heartbeat(container: WorkerContainer, stop: asyncio.Event) -> None:
    """Toca o arquivo de heartbeat enquanto o worker consegue fazer o seu trabalho.

    O processo vivo não basta: sem Mongo ou RabbitMQ o worker não registra cliques nem
    publica eventos. Por isso o arquivo só é atualizado com o loop de eventos respondendo,
    o Mongo acessível (a mesma consulta alimenta a métrica de pendentes do outbox) e a
    conexão de consumo com o RabbitMQ de pé. O healthcheck (`healthcheck.py`) olha a idade.
    """
    settings = container.settings
    heartbeat_file = Path(settings.worker_heartbeat_file)
    # Um arquivo de uma execução anterior faria o worker parecer saudável antes da hora.
    heartbeat_file.unlink(missing_ok=True)

    try:
        while not stop.is_set():
            if await _is_healthy(container):
                heartbeat_file.touch()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.worker_heartbeat_interval_seconds
                )
    finally:
        # Parado de propósito não é saudável: o healthcheck não deve esperar o arquivo envelhecer.
        heartbeat_file.unlink(missing_ok=True)


async def _is_healthy(container: WorkerContainer) -> bool:
    try:
        OUTBOX_PENDING.set(await container.url_created_outbox.count_pending())
    except Exception:
        logger.warning("Mongo inacessível; heartbeat não atualizado", exc_info=True)
        return False

    if not container.rabbitmq_connection.connected.is_set():
        logger.warning("Conexão com o RabbitMQ caída; heartbeat não atualizado")
        return False
    return True
