import asyncio
import json
import logging

import aio_pika

from url_shortner.application.commands.register_click import RegisterClickCommand
from url_shortner.bootstrap.container import WorkerContainer
from url_shortner.domain.exceptions import DomainError
from url_shortner.infrastructure.messaging.topology import declare_url_clicked_queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_TRANSIENT_ERROR_BACKOFF_SECONDS = 1.0


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
    queue = await declare_url_clicked_queue(container.rabbitmq_channel, container.rabbitmq_exchange)
    await container.rabbitmq_channel.set_qos(prefetch_count=10)

    logger.info("Worker aguardando mensagens em url_clicked_queue...")
    try:
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await _handle_message(message, container)
    finally:
        await container.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
