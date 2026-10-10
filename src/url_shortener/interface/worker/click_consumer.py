import asyncio
import contextlib
import json
import logging
import signal

import aio_pika

from url_shortener.application.commands.register_click import RegisterClickCommand
from url_shortener.bootstrap.container import WorkerContainer
from url_shortener.config import get_settings
from url_shortener.domain.exceptions import DomainError
from url_shortener.infrastructure.messaging.topology import MAX_DELIVERY_RETRIES
from url_shortener.interface.worker.outbox_relay import run_outbox_relay
from url_shortener.logging_config import configure_logging

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_BASE_SECONDS = 1.0
_RETRY_BACKOFF_MAX_SECONDS = 30.0
_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class InvalidMessageError(Exception):
    """Mensagem que nunca vai ser processada com sucesso, não importa quantas tentativas."""


def _parse_command(body: bytes) -> RegisterClickCommand:
    try:
        code = json.loads(body)["code"]
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidMessageError(f"Payload inválido: {body!r}") from error
    if not isinstance(code, str):
        raise InvalidMessageError(f"Campo 'code' deveria ser string: {body!r}")
    return RegisterClickCommand(code=code)


def _delivery_count(message: aio_pika.abc.AbstractIncomingMessage) -> int:
    """Quantas vezes a mensagem já foi devolvida à fila (header da quorum queue)."""
    value = (message.headers or {}).get("x-delivery-count", 0)
    return value if isinstance(value, int) else 0


def _retry_delay_seconds(retries: int) -> float:
    return float(min(_RETRY_BACKOFF_BASE_SECONDS * 2**retries, _RETRY_BACKOFF_MAX_SECONDS))


async def _handle_message(
    message: aio_pika.abc.AbstractIncomingMessage, container: WorkerContainer
) -> None:
    try:
        command = _parse_command(message.body)
        await container.register_click_handler.handle(command)
    except (InvalidMessageError, DomainError):
        # Erro permanente: requeue causaria loop infinito, então vai para a DLQ.
        logger.exception("Mensagem de click inválida, enviada para a DLQ")
        await message.reject(requeue=False)
    except Exception:
        # Erro transitório (ex.: Mongo fora do ar): espera e devolve para a fila. Passado o
        # x-delivery-limit da fila, o próprio RabbitMQ manda a mensagem para a DLQ.
        retries = _delivery_count(message)
        delay = _retry_delay_seconds(retries)
        logger.exception(
            "Falha ao processar mensagem de click (tentativa %d de %d), requeue em %.1fs",
            retries + 1,
            MAX_DELIVERY_RETRIES + 1,
            delay,
        )
        # Espera ANTES do nack: com o nack a mensagem volta na hora e seria reentregue
        # imediatamente a outro slot do prefetch, anulando o backoff.
        await asyncio.sleep(delay)
        await message.nack(requeue=True)
    else:
        await message.ack()
        logger.info("Click registrado para o código %s", command.code)


async def run() -> None:
    container = await WorkerContainer.create()
    queue = container.url_clicked_queue
    await container.rabbitmq_channel.set_qos(prefetch_count=10)

    # O worker roda como PID 1 no container, e o kernel ignora SIGTERM no PID 1 sem handler:
    # sem isto, `docker stop` esperaria o timeout inteiro e mataria o processo com SIGKILL.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in _STOP_SIGNALS:
        loop.add_signal_handler(sig, stop.set)

    async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        await _handle_message(message, container)

    consumer_tag = await queue.consume(on_message)
    relay_task = asyncio.create_task(run_outbox_relay(container, stop))
    logger.info("Worker aguardando mensagens em url_clicked_queue...")
    try:
        await stop.wait()
        logger.info("Sinal de parada recebido, encerrando o worker")
    finally:
        # Normalmente o relay já saiu sozinho com o `stop`; o cancel cobre o caso de o
        # `run()` ter sido cancelado de fora (ex.: nos testes).
        relay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay_task
        for sig in _STOP_SIGNALS:
            loop.remove_signal_handler(sig)
        try:
            await queue.cancel(consumer_tag)
        except Exception:
            # Conexão já caída: não há consumer para cancelar, segue para o close.
            logger.warning("Falha ao cancelar o consumer", exc_info=True)
        # Mensagens em processamento que não chegarem ao ack voltam para a fila no close.
        await container.close()


def main() -> None:
    configure_logging(get_settings().log_level)
    asyncio.run(run())


if __name__ == "__main__":
    main()
