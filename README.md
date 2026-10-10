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
  estritamente crescente, em operação normal não há colisão, diferente de
  estratégias baseadas em hash ou valores aleatórios. Se mesmo assim o código já
  existir (chave trocada ou contador resetado), o `_id` duplicado vira
  `ShortCodeConflictError` e o caso de uso tenta outro código, até 3 vezes.
  Códigos iguais a uma rota fixa da API (`health`, `urls`, `docs`...) também são
  pulados: essas rotas são casadas antes de `/{code}`, e o link ficaria
  inacessível. A lista é derivada das rotas registradas, então cobre as futuras.
- **Códigos não enumeráveis**: o contador passa por uma rede de Feistel com
  chave secreta (`APP_CODE_SECRET`) sobre o domínio exato `[0, 62^7)`
  (`domain/services/code_scrambler.py`). É uma bijeção, então continua sem
  colisão, e sem a chave os códigos já vistos não ajudam a prever os próximos.
  Uma versão anterior usava `n * K mod 62^7`, que é linear: dois códigos
  consecutivos diferiam sempre por `K`, então duas criações bastavam para
  enumerar tudo. A chave é obrigatória e não tem default. Trocá-la não invalida
  os links existentes (o código é gravado, não recalculado), só muda os
  próximos. O espaço comporta ~3,5 trilhões de códigos.
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
  sem virar uma feature completa de analytics. O evento `URLCreated` existe para
  uma extensão futura (hoje sem consumidor).
- **`URLCreated` via transactional outbox**: publicar direto depois do `insert`
  perderia o evento sempre que o broker estivesse fora. Em vez disso, o documento
  da URL já é gravado com `url_created_pending: true` na mesma escrita, então é
  atômico sem precisar de transação (que no Mongo exigiria replica set). Um relay
  no worker (`interface/worker/outbox_relay.py`) busca os pendentes por um índice
  parcial, publica e só então remove o campo. Entrega *at-least-once*: se o
  worker cair entre o publish e a marcação, o evento sai de novo, então
  consumidores de `URLCreated` precisam ser idempotentes (o `code` serve de
  chave). Com mais de uma réplica do worker, o mesmo evento também pode sair
  duas vezes.
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
  (`https://google.com@evil.com`, cujo host real é `evil.com`) são rejeitadas,
  assim como links para o host do próprio encurtador (o de `APP_BASE_URL`), que
  só serviriam para esconder o destino atrás de uma cadeia de redirects.
- **Mongo fora do ar responde `503`, não `500`**: os adapters do Mongo
  convertem falhas de conexão em `StorageUnavailableError` (camada de
  aplicação, sem depender do pymongo) e a API responde `503` com
  `Retry-After`, sinalizando que vale tentar de novo.
- **Health checks**: `GET /health` é *liveness*: não toca dependências, para
  o orquestrador não reiniciar a API só porque o Mongo caiu. `GET /health/ready`
  é *readiness*: só o Mongo é obrigatório (`503` sem ele); sem Redis ou
  RabbitMQ a API segue funcionando e responde `200` com status `degraded`.
- **Health check do worker**: o worker não tem HTTP de saúde. Ele toca um
  arquivo de heartbeat (`APP_WORKER_HEARTBEAT_FILE`) a cada
  `APP_WORKER_HEARTBEAT_INTERVAL_SECONDS` (10s), mas só se o loop de eventos
  responde, o Mongo está acessível e a conexão de consumo com o RabbitMQ está de
  pé: o processo vivo não basta, porque sem essas dependências ele não faz o seu
  trabalho. O healthcheck do container
  (`python -m url_shortener.interface.worker.healthcheck`) falha se o arquivo
  tiver mais de 3 intervalos. O arquivo é apagado na subida e na parada, para um
  heartbeat velho não parecer saudável. Atenção: no Docker/Podman, `unhealthy`
  só sinaliza; o `restart: unless-stopped` não reinicia o container por isso
  (um orquestrador como Kubernetes, sim).
- **Métricas (Prometheus)**: API e worker expõem `/metrics` num servidor
  próprio na porta `APP_METRICS_PORT` (9100), separada da porta da aplicação e
  não publicada no compose. Na API, isso tem dois motivos: uma rota `/metrics`
  disputaria caminho com `/{code}` (um código curto `metrics` seria possível) e
  ficaria aberta na porta pública junto com os redirects.
  Os nomes começam com `url_shortener_`: requisições e latência por rota
  (rotuladas pelo template `/{code}`, nunca pelo código, para não criar uma série
  por URL), cache `hit`/`miss`/`error`, respostas `429` por limite, eventos
  publicados e falhas de publicação, desfecho das mensagens de clique
  (`registered`, `requeued`, `dead_lettered`) e eventos pendentes no outbox.
  Profundidade das filas e da DLQ vêm do plugin `rabbitmq_prometheus`, já ligado
  na imagem (porta 15692). Com mais de um processo uvicorn por container, cada
  um teria o próprio contador; aí seria preciso o modo multiprocess do
  `prometheus_client`.
- **Rate limit na criação**: `POST /urls` aceita até
  `APP_RATE_LIMIT_CREATE_REQUESTS` chamadas por IP a cada
  `APP_RATE_LIMIT_CREATE_WINDOW_SECONDS` (padrão 20/min); acima disso responde
  `429` com `Retry-After`. O contador fica no Redis (janela fixa) para valer
  entre várias instâncias da API. Se o Redis falhar, a requisição passa: ele
  segue sendo acessório.
- **Rate limit de códigos inexistentes**: cada redirect para um código bem
  formado que não existe conta para o IP (`APP_RATE_LIMIT_REDIRECT_MISS_REQUESTS`
  por `APP_RATE_LIMIT_REDIRECT_MISS_WINDOW_SECONDS`, padrão 30/min). Passado o
  limite, o IP recebe `429` em qualquer redirect, inclusive de códigos válidos,
  e a consulta é barrada antes de chegar ao Mongo. Quem só acessa links válidos
  nunca é limitado. Isso custa uma leitura extra no Redis por redirect. Cache
  negativo não resolveria: quem varre códigos aleatórios não repete código.
  Caminhos fora do formato de código (`/favicon.ico`, `/robots.txt`, scanners
  atrás de `/wp-login.php`) respondem `404` sem contar: são rejeitados antes do
  Mongo, então não custam nada, e contá-los bloquearia crawlers legítimos.
- **IP do cliente atrás de proxy**: o uvicorn já lê `X-Forwarded-For`, mas só
  confia nele quando a conexão vem de um IP listado em `FORWARDED_ALLOW_IPS`
  (padrão `127.0.0.1`). Atrás de um proxy reverso, defina essa variável com o IP
  do proxy, ou os dois rate limits vão tratar todos os clientes como um só.

## Rodando com Docker Compose

```bash
cp .env.example .env
# em produção, defina APP_CODE_SECRET no .env (openssl rand -hex 32); sem ela, o
# compose usa uma chave de desenvolvimento
docker compose up --build
```
Sobe `api` (porta 8000), `worker`, `mongo`, `redis`, `rabbitmq` (painel de
management em `localhost:15672`, usuário/senha `guest`/`guest`), `prometheus` e
`grafana` (ver [Observabilidade](#observabilidade-prometheus-e-grafana)).
`api` e `worker` usam `restart: unless-stopped`: se o processo cair, voltam
sozinhos.

O compose é para desenvolvimento: o RabbitMQ usa o usuário padrão `guest/guest`
(acesso total ao broker) e o painel é publicado só em `127.0.0.1`, para não
ficar aberto na rede. Em produção, crie um usuário com
`RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` e ajuste `APP_RABBITMQ_URI`.

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

## Observabilidade: Prometheus e Grafana

O compose também sobe:

- **Prometheus** (`localhost:9090`): a cada 5s coleta as métricas da API e do
  worker (porta 9100 de cada um) e do RabbitMQ (plugin `rabbitmq_prometheus`,
  porta 15692) e guarda o histórico por 7 dias (`observability/prometheus.yml`).
  Em *Status → Targets* dá para ver se os três estão `UP`.
- **Grafana** (`localhost:3000`): abre direto no dashboard *URL Shortener*, sem
  login. O datasource e o dashboard são provisionados a partir de
  `observability/grafana/`. Alterações feitas no navegador somem ao recriar o
  container: para manter, exporte o JSON (*Share → Export*) e salve em
  `observability/grafana/dashboards/url-shortener.json`.

Os dois ficam só no `127.0.0.1`, e o Grafana roda sem login e com permissão de
edição: configuração de desenvolvimento, não de produção.

O dashboard tem quatro blocos: **saúde** (API, worker e RabbitMQ sendo
coletados, taxa de cache hit, outbox pendente), **tráfego** (redirects por
status, requisições e latência p95 por rota, cache hit/miss/erro), **proteção**
(429 por limite) e **eventos e filas** (publicados e falhas, desfecho das
mensagens de clique, outbox pendente e mensagens nas filas do RabbitMQ).

Os gráficos mostram taxas (`rate()`), que precisam de tráfego contínuo: uma
rajada de requisições antes da primeira coleta não aparece. Para gerar tráfego:

```bash
while true; do
  code=$(curl -s -X POST localhost:8000/urls -H "Content-Type: application/json" \
    -d "{\"url\": \"https://example.com/$RANDOM\"}" | sed 's/.*"code":"\([^"]*\)".*/\1/')
  for _ in 1 2 3; do curl -s -o /dev/null "localhost:8000/$code"; done
  sleep 1
done
```

Experimentos para ver os gráficos reagirem, com o gerador rodando:

- `docker compose stop rabbitmq`: *Outbox pendente* sobe a cada URL criada e
  aparecem falhas de publicação de `url.clicked`. Os redirects seguem
  funcionando. Com `docker compose start rabbitmq`, o outbox volta a zero.
- `docker compose stop worker`: a fila `url_clicked_queue` acumula os cliques;
  com `start`, ela esvazia de uma vez.
- `docker compose stop redis`: o cache passa a dar `error`, cada redirect vai
  ao Mongo e o rate limit deixa de valer (ele libera quando o Redis falha).
- Acessar 31 códigos inexistentes em menos de 1 minuto: aparece `429` de
  `redirect_miss`, e por até 1 minuto o mesmo IP recebe `429` também nos links
  válidos.

## Desenvolvimento local

O CI (`.github/workflows/ci.yml`) roda lint, formatação, mypy e testes unitários
a cada push na `main` e em pull requests; se passarem, roda os testes de
integração.

```bash
uv sync
# Para subir API/worker fora do compose (os testes já usam uma chave própria):
export APP_CODE_SECRET=$(openssl rand -hex 32)   # ou defina no .env
uv run pytest              # testes unitários (rápidos, sem Docker)
uv run pytest -m integration  # teste de integração ponta a ponta (requer Docker)
uv run ruff check .
uv run ruff format .
uv run mypy src/
```
