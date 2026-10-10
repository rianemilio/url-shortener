import httpx
import pytest
from fastapi import FastAPI, HTTPException

from tests.metrics_helpers import sample
from url_shortener.interface.api.metrics import HttpMetricsMiddleware
from url_shortener.interface.api.routers import metrics


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(HttpMetricsMiddleware)
    app.include_router(metrics.router)

    @app.get("/{code}")
    async def by_code(code: str) -> dict[str, str]:
        if code == "missing":
            raise HTTPException(status_code=404)
        return {"code": code}

    @app.get("/boom/now")
    async def boom() -> None:
        raise RuntimeError("falha inesperada")

    return app


def _requests(route: str, status: str) -> float:
    return sample("url_shortener_http_requests_total", method="GET", route=route, status=status)


async def _get(path: str) -> httpx.Response:
    # raise_app_exceptions=False: deixa o 500 virar resposta, como num servidor de verdade.
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_labels_requests_by_route_template_not_by_path() -> None:
    ok_before, missing_before = _requests("/{code}", "200"), _requests("/{code}", "404")

    await _get("/abc1234")
    await _get("/xyz9876")
    await _get("/missing")

    assert _requests("/{code}", "200") == ok_before + 2
    assert _requests("/{code}", "404") == missing_before + 1
    assert _requests("/abc1234", "200") == 0


@pytest.mark.asyncio
async def test_unmatched_paths_share_one_label() -> None:
    before = _requests("unmatched", "404")

    await _get("/a/b/c")

    assert _requests("unmatched", "404") == before + 1


@pytest.mark.asyncio
async def test_unhandled_errors_are_counted_as_500() -> None:
    before = _requests("/boom/now", "500")

    response = await _get("/boom/now")

    assert response.status_code == 500
    assert _requests("/boom/now", "500") == before + 1


@pytest.mark.asyncio
async def test_observes_latency() -> None:
    name = "url_shortener_http_request_duration_seconds_count"
    before = sample(name, method="GET", route="/{code}")

    await _get("/abc1234")

    assert sample(name, method="GET", route="/{code}") == before + 1


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_format() -> None:
    response = await _get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "url_shortener_http_requests_total" in response.text
