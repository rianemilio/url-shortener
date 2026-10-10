# url-shortener

![CI](https://github.com/rianemilio/url-shortner/actions/workflows/ci.yml/badge.svg)

**English** | [Português](README.pt-BR.md)

An intentionally "overengineered" URL shortener: the feature set is minimal
(shorten + redirect), but the architecture applies Clean Architecture, CQRS and
event-driven design, with MongoDB and Redis as NoSQL stores.

## Stack

- **Backend**: Python 3.12 + FastAPI
- **Database**: MongoDB (source of truth) + Redis (lookup cache)
- **Messaging**: RabbitMQ (`URLCreated` and `URLClicked` events)
- **Package manager**: [uv](https://github.com/astral-sh/uv)
- **Quality**: ruff (lint/format) + mypy

## Architecture

```
domain/          entities, value objects, events and pure rules, no external dependencies
application/     use cases (commands/queries) and ports (Protocol) implemented by infra
infrastructure/  concrete adapters: Mongo, Redis, RabbitMQ
interface/       FastAPI API and event-consuming worker
bootstrap/       manual dependency wiring (DI container)
```

Dependency rule: `domain` and `application` never import `infrastructure` or
`interface`. Ports live in `application/ports/*.py` as `typing.Protocol`; the
adapters in `infrastructure/**` implement them through structural typing.

### Design decisions

- **Short code generation**: an atomic counter in MongoDB (`findOneAndUpdate`
  with `$inc`), scrambled and encoded as 7 base62 characters. Since Mongo is the
  single source of truth (counter included) and the sequence is strictly
  increasing, there are no collisions in normal operation, unlike hash-based or
  random strategies. If a code does already exist (changed key or reset
  counter), the duplicate `_id` becomes a `ShortCodeConflictError` and the use
  case tries another code, up to 3 times. Codes equal to a fixed API route
  (`health`, `urls`, `docs`...) are skipped too: those routes are matched before
  `/{code}`, so the link would be unreachable. The list is derived from the
  registered routes, so it covers future ones.
- **Non-enumerable codes**: the counter goes through a Feistel network keyed
  with a secret (`APP_CODE_SECRET`) over the exact domain `[0, 62^7)`
  (`domain/services/code_scrambler.py`). It is a bijection, so there are still
  no collisions, and without the key previously seen codes don't help predict
  the next ones. An earlier version used `n * K mod 62^7`, which is linear: two
  consecutive codes always differed by `K`, so two creations were enough to
  enumerate everything. The key is required and has no default. Changing it
  doesn't invalidate existing links (the code is stored, not recomputed); it
  only changes future ones. The space holds ~3.5 trillion codes.
- **Redis is cache only**: it never holds data that can't be rebuilt from
  Mongo. If it goes down, the system keeps working (with more Mongo reads);
  cache read and write failures are logged and ignored.
- **CQRS**: `CreateShortUrlCommandHandler` only writes; `GetOriginalUrlQueryHandler`
  only reads, with no side effects. Click tracking is a separate command
  (`TrackClickCommandHandler`) that the router schedules as a background task
  after resolving the URL. Each handler receives its ports through constructor
  injection.
- **Events with a real consumer**: the `URLClicked` event
  is published on redirect (without blocking the response) and consumed by a
  separate worker that increments `click_count` in Mongo: a genuine use of
  RabbitMQ without growing into a full analytics feature. The `URLCreated`
  event exists for a future extension (no consumer today).
- **`URLCreated` via transactional outbox**: publishing right after the
  `insert` would lose the event whenever the broker was down. Instead, the URL
  document is written with `url_created_pending: true` in the same write, so it
  is atomic without a transaction (which in Mongo would require a replica set).
  A relay in the worker (`interface/worker/outbox_relay.py`) finds pending
  documents through a partial index, publishes, and only then removes the
  field. Delivery is *at-least-once*: if the worker dies between publishing and
  marking, the event goes out again, so `URLCreated` consumers must be
  idempotent (the `code` works as the key). With more than one worker replica,
  the same event may also go out twice.
- **Worker errors**: messages that will never succeed (invalid JSON, missing
  `code`, malformed code) are rejected without requeue and go to the
  `url_clicked_queue.dlq` DLQ. Transient failures (e.g. Mongo down) go back to
  the queue with exponential backoff (1s, 2s, 4s... up to 30s). The click queue
  is a *quorum queue* with `x-delivery-limit`: RabbitMQ itself counts the
  deliveries and, after 5 extra attempts (~1 min), sends the message to the
  DLQ. Messages in the DLQ can be reprocessed by moving them back through the
  management UI (shovel plugin) once the problem is fixed.
- **`click_count` is approximate, on purpose**: RabbitMQ delivers
  *at-least-once* and `$inc` isn't idempotent, so a redelivery (e.g. the worker
  dies between the `$inc` and the ack) counts the click twice. Deduplicating
  would need a per-event id and a record of processed events, a cost that
  doesn't pay off for a click counter.
- **RabbitMQ isn't required by the API**: if the broker is down at startup,
  the API starts anyway and the publisher keeps reconnecting in the background
  (`APP_RABBITMQ_RECONNECT_INTERVAL_SECONDS`). Until then, events fail fast and
  are logged; redirects keep working. The API and the worker declare the same
  topology (exchange, click queue and DLQ), so clicks published before the
  worker's first start stay in the queue instead of being dropped.
- **Explicit timeouts**: Mongo (`APP_MONGO_TIMEOUT_MS`, 2s), Redis
  (`APP_REDIS_TIMEOUT_SECONDS`, 0.5s) and RabbitMQ
  (`APP_RABBITMQ_TIMEOUT_SECONDS`, 2s). Without them, a stuck service (one
  that doesn't refuse the connection, just doesn't answer) holds the request
  indefinitely (Redis) or for 30s (Mongo).
- **URL validation against phishing**: URLs with credentials
  (`https://google.com@evil.com`, whose real host is `evil.com`) are rejected,
  as are links to the shortener's own host (the one in `APP_BASE_URL`), which
  would only serve to hide the destination behind a chain of redirects.
- **Mongo down returns `503`, not `500`**: the Mongo adapters turn connection
  failures into `StorageUnavailableError` (application layer, no pymongo
  dependency) and the API answers `503` with `Retry-After`, signaling that a
  retry is worthwhile.
- **Health checks**: `GET /health` is *liveness*: it doesn't touch
  dependencies, so the orchestrator won't restart the API just because Mongo
  went down. `GET /health/ready` is *readiness*: only Mongo is required (`503`
  without it); without Redis or RabbitMQ the API keeps working and answers
  `200` with status `degraded`.
- **Worker health check**: the worker has no HTTP health endpoint. It touches a
  heartbeat file (`APP_WORKER_HEARTBEAT_FILE`) every
  `APP_WORKER_HEARTBEAT_INTERVAL_SECONDS` (10s), but only if the event loop is
  responsive, Mongo is reachable and the RabbitMQ consumer connection is up: a
  live process isn't enough, because without those dependencies it can't do
  its job. The container healthcheck
  (`python -m url_shortener.interface.worker.healthcheck`) fails if the file is
  older than 3 intervals. The file is deleted on startup and shutdown, so a
  stale heartbeat never looks healthy. Note: in Docker/Podman, `unhealthy` is
  only a signal; `restart: unless-stopped` doesn't restart the container
  because of it (an orchestrator such as Kubernetes does).
- **Metrics (Prometheus)**: the API and the worker expose `/metrics` on a
  dedicated server on `APP_METRICS_PORT` (9100), separate from the application
  port and not published by the compose file. For the API there are two
  reasons: a `/metrics` route would compete with `/{code}` (a short code
  `metrics` would be possible) and would be exposed on the public port along
  with the redirects. Names start with `url_shortener_`: requests and latency
  per route (labeled with the `/{code}` template, never the code itself, to
  avoid one series per URL), cache `hit`/`miss`/`error`, `429` responses per
  limit, published events and publish failures, click message outcomes
  (`registered`, `requeued`, `dead_lettered`) and pending outbox events. Queue
  and DLQ depth come from the `rabbitmq_prometheus` plugin, already enabled in
  the image (port 15692). With more than one uvicorn process per container,
  each would have its own counters; that would require the `prometheus_client`
  multiprocess mode.
- **Rate limit on creation**: `POST /urls` accepts up to
  `APP_RATE_LIMIT_CREATE_REQUESTS` calls per IP every
  `APP_RATE_LIMIT_CREATE_WINDOW_SECONDS` (default 20/min); above that it
  answers `429` with `Retry-After`. The counter lives in Redis (fixed window)
  so it holds across multiple API instances. If Redis fails, the request goes
  through: it remains an accessory.
- **Rate limit on unknown codes**: each redirect to a well-formed code that
  doesn't exist counts against the IP (`APP_RATE_LIMIT_REDIRECT_MISS_REQUESTS`
  per `APP_RATE_LIMIT_REDIRECT_MISS_WINDOW_SECONDS`, default 30/min). Past the
  limit, the IP gets `429` on any redirect, valid codes included, and the
  lookup is stopped before reaching Mongo. Clients that only open valid links
  are never limited. This costs one extra Redis read per redirect. A negative
  cache wouldn't help: whoever scans random codes never repeats one. Paths that
  don't match the code format (`/favicon.ico`, `/robots.txt`, scanners probing
  `/wp-login.php`) answer `404` without counting: they're rejected before Mongo,
  so they cost nothing, and counting them would block legitimate crawlers.
  Accepted trade-off: behind a shared IP (CGNAT, corporate network), whoever
  scans codes blocks redirects for everyone on that IP for up to one window.
  Blocking only the misses wouldn't protect Mongo, because a code is only
  known to be missing after looking it up.
- **Client IP behind a proxy**: uvicorn already reads `X-Forwarded-For`, but
  only trusts it when the connection comes from an IP listed in
  `FORWARDED_ALLOW_IPS` (default `127.0.0.1`). Behind a reverse proxy, set this
  variable to the proxy's IP, or both rate limits will treat every client as
  one.
- **IPv6 limited per /64**: rate limits count the client's IPv4 address, but
  for IPv6 they count the whole /64 prefix. A /64 is what a provider hands to a
  single customer, who can switch addresses inside it at will: limiting per
  individual address wouldn't limit anyone. IPv4-mapped IPv6
  (`::ffff:203.0.113.7`) counts as the IPv4 address.

## Running with Docker Compose

```bash
cp .env.example .env
# in production, set APP_CODE_SECRET in .env (openssl rand -hex 32); without it,
# the compose file uses a development key
docker compose up --build
```
Starts `api` (port 8000), `worker`, `mongo`, `redis`, `rabbitmq` (management
UI at `localhost:15672`, user/password `guest`/`guest`), `prometheus` and
`grafana` (see [Observability](#observability-prometheus-and-grafana)).
`api` and `worker` use `restart: unless-stopped`: if the process dies, they
come back on their own.

The compose file is meant for development: RabbitMQ uses the default
`guest/guest` user (full broker access) and the UI is published only on
`127.0.0.1`, so it isn't open to the network. In production, create a user with
`RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` and adjust `APP_RABBITMQ_URI`.

### Manual testing

```bash
curl -X POST localhost:8000/urls -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some-long-page"}'
# => {"code": "cJinsL5", "short_url": "http://localhost:8000/cJinsL5", ...}

curl -v localhost:8000/cJinsL5
# => 307 Temporary Redirect to the original URL
```

After a few seconds, the document's `click_count` in Mongo should have been
incremented by the worker. Check with:

```bash
docker compose exec -T mongo mongosh url_shortener --quiet --eval 'printjson(db.urls.find().toArray())'
```

The interactive API docs (Swagger UI) are at `localhost:8000/docs`.

## Observability: Prometheus and Grafana

The compose file also starts:

- **Prometheus** (`localhost:9090`): every 5s it scrapes metrics from the API
  and the worker (port 9100 on each) and from RabbitMQ (`rabbitmq_prometheus`
  plugin, port 15692), keeping 7 days of history (`observability/prometheus.yml`).
  *Status → Targets* shows whether all three are `UP`.
- **Grafana** (`localhost:3000`): opens straight into the *URL Shortener*
  dashboard, no login. The datasource and the dashboard are provisioned from
  `observability/grafana/`. Changes made in the browser are lost when the
  container is recreated: to keep them, export the JSON (*Share → Export*) and
  save it to `observability/grafana/dashboards/url-shortener.json`.

Both are bound to `127.0.0.1` only, and Grafana runs without login and with
edit permissions: a development setup, not a production one.

The dashboard has four sections: **health** (API, worker and RabbitMQ being
scraped, cache hit rate, pending outbox), **traffic** (redirects by status,
requests and p95 latency per route, cache hit/miss/error), **protection** (429
per limit) and **events and queues** (published events and failures, click
message outcomes, pending outbox and messages in the RabbitMQ queues).

The charts show rates (`rate()`), which need continuous traffic: a burst of
requests before the first scrape won't show up. To generate traffic:

```bash
while true; do
  code=$(curl -s -X POST localhost:8000/urls -H "Content-Type: application/json" \
    -d "{\"url\": \"https://example.com/$RANDOM\"}" | sed 's/.*"code":"\([^"]*\)".*/\1/')
  for _ in 1 2 3; do curl -s -o /dev/null "localhost:8000/$code"; done
  sleep 1
done
```

Experiments to watch the charts react, with the generator running:

- `docker compose stop rabbitmq`: *Pending outbox* grows with each created URL
  and `url.clicked` publish failures show up. Redirects keep working. After
  `docker compose start rabbitmq`, the outbox drops back to zero.
- `docker compose stop worker`: the `url_clicked_queue` queue piles up clicks;
  after `start`, it drains at once.
- `docker compose stop redis`: the cache starts reporting `error`, every
  redirect goes to Mongo and the rate limit stops applying (it lets requests
  through when Redis fails).
- Hitting 31 nonexistent codes in under 1 minute: `redirect_miss` `429`s show
  up, and for up to 1 minute the same IP also gets `429` on valid links.

## Local development

CI (`.github/workflows/ci.yml`) runs lint, formatting, mypy and unit tests on
every push to `main` and on pull requests; if they pass, it runs the
integration tests.

```bash
uv sync
# To run the API/worker outside compose (the tests already use their own key):
export APP_CODE_SECRET=$(openssl rand -hex 32)   # or set it in .env
uv run pytest              # unit tests (fast, no Docker)
uv run pytest -m integration  # end-to-end integration test (requires Docker)
uv run ruff check .
uv run ruff format .
uv run mypy src/
```

## License

[MIT](LICENSE)
