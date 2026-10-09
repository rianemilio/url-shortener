import asyncio
import json
import logging
import signal

import aio_pika

from url_shortener.application.commands.register_click import RegisterClickCommand
from url_shortener.bootstrap.container import WorkerContainer
from url_shortener.domain.exceptions import DomainError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_TRANSIENT_ERROR_BACKOFF_SECONDS = 1.0
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
        # Erro transitório (ex.: Mongo fora do ar): devolve para a fila e tenta de novo.
        logger.exception("Falha ao processar mensagem de click, requeued")
        await message.nack(requeue=True)
        await asyncio.sleep(_TRANSIENT_ERROR_BACKOFF_SECONDS)
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
    logger.info("Worker aguardando mensagens em url_clicked_queue...")
    try:
        await stop.wait()
        logger.info("Sinal de parada recebido, encerrando o worker")
    finally:
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
    asyncio.run(run())


if __name__ == "__main__":
    main()
