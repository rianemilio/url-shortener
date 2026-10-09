# url-shortener

Encurtador de URLs propositalmente "overengineered": a funcionalidade é mínima
(encurtar + redirecionar), mas a arquitetura aplica Clean Architecture, CQRS e
design orientado a eventos, com MongoDB e Redis como bancos NoSQL.

## Stack

- **Backend**: Python 3.12 + FastAPI
- **Banco de dados**: MongoDB (fonte da verdade) + Redis (cache de lookup)
- **Mensageria**: RabbitMQ (eventos `URLCreated` e `URLClicked`)
- **Gerenciador de pacotes**: [uv](https://github.com/astral-sh/uv)
- **Qualidade**: ruff (lint/format) + mypy

## Arquitetura

```
domain/          entidades, value objects, eventos e regras puras, sem dependências externas
application/     casos de uso (commands/queries) e portas (Protocol) que a infra implementa
infrastructure/  adapters concretos: Mongo, Redis, RabbitMQ
interface/       API FastAPI e worker consumidor de eventos
bootstrap/       composição manual das dependências (container de DI)
```

Regra de dependência: `domain` e `application` nunca importam `infrastructure` ou
`interface`. As portas ficam em `application/ports/*.py` como `typing.Protocol`;
os adapters em `infrastructure/**` as implementam por structural typing.

### Decisões de design

- **Geração de código curto**: contador atômico no MongoDB (`findOneAndUpdate`
  com `$inc`), embaralhado e convertido para base62 com 7 caracteres. Como o
  Mongo é a única fonte de verdade (inclusive do contador) e a sequência é
  estritamente crescente, não há necessidade de retry por colisão, diferente
  de estratégias baseadas em hash ou valores aleatórios.
- **Códigos não enumeráveis**: o contador passa por `n * K mod 62^7`, com `K`
  coprimo com `62^7` (`domain/services/code_scrambler.py`). Isso é uma bijeção,
  então continua sem colisão, mas `/1`, `/2`, `/3`... deixam de listar todas as
  URLs. Não é criptografia: é ofuscação suficiente para impedir varredura
  trivial. O espaço comporta ~3,5 trilhões de códigos.
- **Redis é só cache**: nunca guarda dado que não possa ser reconstruído a
  partir do Mongo. Se cair, o sistema continua funcionando (com mais leituras
  no Mongo); falhas de leitura e escrita no cache são logadas e ignoradas.
- **CQRS**: `CreateShortUrlCommandHandler` só escreve; `GetOriginalUrlQueryHandler`
  só lê, sem efeitos colaterais. O rastreamento do clique é um comando separado
  (`TrackClickCommandHandler`), que o router agenda como background task depois
  de resolver a URL. Cada handler recebe suas portas via injeção de construtor.
- **Eventos com consumidor de verdade**: o evento `URLClicked` é
  publicado no redirect (sem bloquear a resposta) e consumido por um worker
  separado que incrementa `click_count` no Mongo: dá uso genuíno ao RabbitMQ
  sem virar uma feature completa de analytics. O evento `URLCreated` é
  publicado para uma extensão futura (hoje sem consumidor).
- **Erros no worker**: mensagens que nunca vão dar certo (JSON inválido, sem
  `code`, código fora do formato) são rejeitadas sem requeue e vão para a DLQ
  `url_clicked_queue.dlq`. Falhas transitórias (ex.: Mongo fora do ar) voltam
  para a fila com espera exponencial (1s, 2s, 4s... até 30s). A fila de cliques
  é uma *quorum queue* com `x-delivery-limit`: o próprio RabbitMQ conta as
  entregas e, após 5 tentativas extras (~1 min), manda a mensagem para a DLQ.
  Mensagens na DLQ podem ser reprocessadas movendo-as de volta pelo painel de
  management (plugin shovel) quando o problema for resolvido.
- **`click_count` é aproximado, de propósito**: o RabbitMQ entrega
  *at-least-once* e o `$inc` não é idempotente, então uma reentrega (ex.: worker
  cai entre o `$inc` e o ack) conta o clique duas vezes. Deduplicar exigiria um
  id por evento e um registro de eventos processados, um custo que não se paga
  para um contador de cliques.
- **RabbitMQ não é obrigatório para a API**: se o broker estiver fora na
  subida, a API sobe mesmo assim e o publisher tenta reconectar em background
  (`APP_RABBITMQ_RECONNECT_INTERVAL_SECONDS`). Até lá, os eventos falham rápido
  e são logados; o redirect continua funcionando. A API e o worker declaram a
  mesma topologia (exchange, fila de cliques e DLQ), então cliques publicados
  antes da primeira subida do worker ficam na fila em vez de serem descartados.
- **Timeouts explícitos**: Mongo (`APP_MONGO_TIMEOUT_MS`, 2s), Redis
  (`APP_REDIS_TIMEOUT_SECONDS`, 0,5s) e RabbitMQ (`APP_RABBITMQ_TIMEOUT_SECONDS`,
  2s). Sem eles, um serviço travado (que não recusa a conexão, só não
  responde) prende a requisição indefinidamente (Redis) ou por 30s (Mongo).
- **Validação de URL contra phishing**: URLs com credenciais
  (`https://google.com@evil.com`, cujo host real é `evil.com`) são rejeitadas.
- **Health checks**: `GET /health` é *liveness*: não toca dependências, para
  o orquestrador não reiniciar a API só porque o Mongo caiu. `GET /health/ready`
  é *readiness*: só o Mongo é obrigatório (`503` sem ele); sem Redis ou
  RabbitMQ a API segue funcionando e responde `200` com status `degraded`.
- **Rate limit na criação**: `POST /urls` aceita até
  `APP_RATE_LIMIT_CREATE_REQUESTS` chamadas por IP a cada
  `APP_RATE_LIMIT_CREATE_WINDOW_SECONDS` (padrão 20/min); acima disso responde
  `429` com `Retry-After`. O contador fica no Redis (janela fixa) para valer
  entre várias instâncias da API. Se o Redis falhar, a requisição passa: ele
  segue sendo acessório. Atrás de um proxy reverso, o IP visto é o do proxy:
  seria preciso rodar o uvicorn com `--proxy-headers --forwarded-allow-ips`.

## Rodando com Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Sobe `api` (porta 8000), `worker`, `mongo`, `redis` e `rabbitmq` (painel de
management em `localhost:15672`, usuário/senha `guest`/`guest`).
`api` e `worker` usam `restart: unless-stopped`: se caírem, voltam sozinhos.

### Testando manualmente

```bash
curl -X POST localhost:8000/urls -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/pagina-longa"}'
# => {"code": "cJinsL5", "short_url": "http://localhost:8000/cJinsL5", ...}

curl -v localhost:8000/cJinsL5
# => 307 Temporary Redirect para a URL original
```

Após alguns segundos, o `click_count` do documento no Mongo deve ter sido
incrementado pelo worker. Confirme com:

```bash
docker compose exec mongo mongosh url_shortener --eval 'db.urls.find()'
```

## Desenvolvimento local

```bash
uv sync
uv run pytest              # testes unitários (rápidos, sem Docker)
uv run pytest -m integration  # teste de integração ponta a ponta (requer Docker)
uv run ruff check .
uv run ruff format .
uv run mypy src/
```
