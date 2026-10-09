from dataclasses import dataclass

import aio_pika

from url_shortener.domain.events.url_clicked import URLClicked

EVENTS_EXCHANGE = "url_events"
URL_CLICKED_QUEUE = "url_clicked_queue"

DEAD_LETTER_EXCHANGE = "url_events.dlx"
URL_CLICKED_DEAD_LETTER_QUEUE = "url_clicked_queue.dlq"

# Quantas vezes uma mensagem pode voltar para a fila após falha transitória antes de ir
# para a DLQ. Constante (e não configuração) porque API e worker declaram a mesma fila e
# argumentos divergentes fariam a declaração falhar com PRECONDITION_FAILED.
MAX_DELIVERY_RETRIES = 5


@dataclass(frozen=True, slots=True)
class Topology:
    events_exchange: aio_pika.abc.AbstractExchange
    url_clicked_queue: aio_pika.abc.AbstractQueue


async def declare_topology(channel: aio_pika.abc.AbstractChannel) -> Topology:
    """Declara exchange, fila de cliques e DLQ.

    Tanto a API quanto o worker chamam isto: se só o worker declarasse a fila, eventos
    publicados antes da primeira subida dele não teriam para onde ir e seriam descartados.
    As declarações são idempotentes.
    """
    events_exchange = await channel.declare_exchange(
        EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )

    dead_letter_exchange = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    dead_letter_queue = await channel.declare_queue(URL_CLICKED_DEAD_LETTER_QUEUE, durable=True)
    await dead_letter_queue.bind(dead_letter_exchange, routing_key=URLClicked.ROUTING_KEY)

    url_clicked_queue = await channel.declare_queue(
        URL_CLICKED_QUEUE,
        durable=True,
        arguments={
            # Quorum queue: o broker conta as entregas (header x-delivery-count) e, passado o
            # x-delivery-limit, manda a mensagem para a DLQ sozinho.
            "x-queue-type": "quorum",
            "x-delivery-limit": MAX_DELIVERY_RETRIES,
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        },
    )
    await url_clicked_queue.bind(events_exchange, routing_key=URLClicked.ROUTING_KEY)

    return Topology(events_exchange=events_exchange, url_clicked_queue=url_clicked_queue)
