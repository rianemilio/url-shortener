import asyncio
import contextlib
import logging

from url_shortener.application.commands.publish_pending_events import PublishPendingEventsCommand
from url_shortener.bootstrap.container import WorkerContainer

logger = logging.getLogger(__name__)


async def run_outbox_relay(container: WorkerContainer, stop: asyncio.Event) -> None:
    """Publica os `URLCreated` pendentes até `stop` ser sinalizado.

    Lote cheio indica que há mais pendentes, então roda de novo na hora; senão espera o
    intervalo de polling. Falhas (Mongo ou RabbitMQ fora) só adiam a publicação: os eventos
    continuam pendentes no Mongo.
    """
    settings = container.settings
    command = PublishPendingEventsCommand(batch_size=settings.outbox_batch_size)
    indexes_ready = False

    while not stop.is_set():
        published = 0
        try:
            if not indexes_ready:
                await container.url_created_outbox.ensure_indexes()
                indexes_ready = True
            published = await container.publish_pending_events_handler.handle(command)
        except Exception:
            logger.warning("Falha no relay do outbox; tentando de novo em seguida", exc_info=True)

        if published:
            logger.info("%d evento(s) URLCreated publicados pelo outbox", published)
        if published < command.batch_size:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.outbox_poll_interval_seconds)
