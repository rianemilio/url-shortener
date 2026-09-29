import aio_pika

from url_shortner.domain.events.url_clicked import URLClicked

EVENTS_EXCHANGE = "url_events"
URL_CLICKED_QUEUE = "url_clicked_queue"

DEAD_LETTER_EXCHANGE = "url_events.dlx"
URL_CLICKED_DEAD_LETTER_QUEUE = "url_clicked_queue.dlq"


async def declare_events_exchange(
    channel: aio_pika.abc.AbstractChannel,
) -> aio_pika.abc.AbstractExchange:
    return await channel.declare_exchange(
        EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )


async def declare_url_clicked_queue(
    channel: aio_pika.abc.AbstractChannel, exchange: aio_pika.abc.AbstractExchange
) -> aio_pika.abc.AbstractQueue:
    """Declara a fila de cliques e sua DLQ, para onde vão as mensagens rejeitadas sem requeue."""
    dead_letter_exchange = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    dead_letter_queue = await channel.declare_queue(URL_CLICKED_DEAD_LETTER_QUEUE, durable=True)
    await dead_letter_queue.bind(dead_letter_exchange, routing_key=URLClicked.ROUTING_KEY)

    queue = await channel.declare_queue(
        URL_CLICKED_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE},
    )
    await queue.bind(exchange, routing_key=URLClicked.ROUTING_KEY)
    return queue
