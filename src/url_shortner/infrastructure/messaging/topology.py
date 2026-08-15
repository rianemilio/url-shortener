import aio_pika

EVENTS_EXCHANGE = "url_events"
URL_CLICKED_QUEUE = "url_clicked_queue"
URL_CLICKED_ROUTING_KEY = "url.clicked"
URL_CREATED_ROUTING_KEY = "url.created"


async def declare_events_exchange(
    channel: aio_pika.abc.AbstractChannel,
) -> aio_pika.abc.AbstractExchange:
    return await channel.declare_exchange(
        EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )


async def declare_url_clicked_queue(
    channel: aio_pika.abc.AbstractChannel, exchange: aio_pika.abc.AbstractExchange
) -> aio_pika.abc.AbstractQueue:
    queue = await channel.declare_queue(URL_CLICKED_QUEUE, durable=True)
    await queue.bind(exchange, routing_key=URL_CLICKED_ROUTING_KEY)
    return queue
