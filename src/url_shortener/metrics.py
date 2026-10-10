"""Métricas Prometheus da API e do worker.

Cada processo tem o próprio registry: a API expõe em `GET /metrics` e o worker num servidor
HTTP próprio (`APP_WORKER_METRICS_PORT`). Profundidade das filas e da DLQ não estão aqui: o
plugin `rabbitmq_prometheus`, ligado por padrão na imagem do RabbitMQ, já as expõe na 15692.
"""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "url_shortener_http_requests_total",
    "Requisições HTTP atendidas pela API",
    ["method", "route", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "url_shortener_http_request_duration_seconds",
    "Latência das requisições HTTP da API",
    ["method", "route"],
    # Redirect com cache hit fica na casa de poucos ms; os timeouts das dependências, em 0,5-2s.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
CACHE_LOOKUPS = Counter(
    "url_shortener_cache_lookups_total",
    "Consultas ao cache de URLs, por resultado (hit, miss, error)",
    ["result"],
)
RATE_LIMITED = Counter(
    "url_shortener_rate_limited_requests_total",
    "Requisições recusadas com 429, por limite (create_url, redirect_miss)",
    ["scope"],
)
EVENTS_PUBLISHED = Counter(
    "url_shortener_events_published_total",
    "Eventos publicados no RabbitMQ",
    ["routing_key"],
)
EVENT_PUBLISH_FAILURES = Counter(
    "url_shortener_event_publish_failures_total",
    "Falhas ao publicar eventos no RabbitMQ (broker fora ou timeout)",
    ["routing_key"],
)
CLICK_MESSAGES = Counter(
    "url_shortener_click_messages_total",
    "Mensagens de clique processadas pelo worker (registered, requeued, dead_lettered)",
    ["outcome"],
)
OUTBOX_PENDING = Gauge(
    "url_shortener_outbox_pending_events",
    "Eventos URLCreated gravados e ainda não publicados (medido a cada heartbeat do worker)",
)
