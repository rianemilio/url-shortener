from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from url_shortener.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

_UNMATCHED_ROUTE = "unmatched"


class HttpMetricsMiddleware:
    """Conta requisições e mede latência por rota.

    Rotula pelo template da rota (`/{code}`), não pelo path: um label por código curto
    criaria uma série por URL e derrubaria o Prometheus. ASGI puro (e não
    BaseHTTPMiddleware) para não pôr uma task extra no caminho de todo redirect.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()
        # Sem resposta enviada (exceção não tratada), o servidor responde 500.
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # O router do FastAPI grava a rota casada no próprio scope.
            route = getattr(scope.get("route"), "path", _UNMATCHED_ROUTE)
            method = scope["method"]
            HTTP_REQUESTS.labels(method, route, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, route).observe(perf_counter() - start)
