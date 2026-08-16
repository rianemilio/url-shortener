import asyncio
import json
import logging

import aio_pika

from url_shortner.application.commands.register_click import RegisterClickCommand
from url_shortner.bootstrap.container import Container
from url_shortner.infrastructure.messaging.topology import declare_url_clicked_queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _handle_message(
    message: aio_pika.abc.AbstractIncomingMessage, container: Container
) -> None:
    async with message.process(requeue=True, ignore_processed=True):
        payload = json.loads(message.body)
        code = payload["code"]
        await container.register_click_handler.handle(RegisterClickCommand(code=code))
        logger.info("Click registrado para o código %s", code)


async def run() -> None:
    container = await Container.create()
    queue = await declare_url_clicked_queue(container.rabbitmq_channel, container.rabbitmq_exchange)
    await container.rabbitmq_channel.set_qos(prefetch_count=10)

    logger.info("Worker aguardando mensagens em url_clicked_queue...")
    try:
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    await _handle_message(message, container)
                except Exception:
                    logger.exception("Falha ao processar mensagem de click, requeued")
    finally:
        await container.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
