import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from tests.fakes.fake_url_repository import FakeUrlRepository
from tests.metrics_helpers import sample
from url_shortener.bootstrap.container import WorkerContainer
from url_shortener.config import Settings
from url_shortener.domain.entities.short_url import ShortUrl
from url_shortener.domain.value_objects.original_url import OriginalUrl
from url_shortener.domain.value_objects.short_code import ShortCode
from url_shortener.interface.worker.healthcheck import is_heartbeat_fresh
from url_shortener.interface.worker.heartbeat import run_heartbeat


class UnreachableOutbox(FakeUrlRepository):
    async def count_pending(self) -> int:
        raise ConnectionError("mongo indisponível")


class FakeConnection:
    def __init__(self, connected: bool) -> None:
        self.connected = asyncio.Event()
        if connected:
            self.connected.set()


class FakeHeartbeatContainer:
    def __init__(
        self, heartbeat_file: Path, outbox: FakeUrlRepository, rabbitmq_connected: bool = True
    ) -> None:
        self.settings = Settings(
            worker_heartbeat_file=str(heartbeat_file), worker_heartbeat_interval_seconds=0.01
        )
        self.url_created_outbox = outbox
        self.rabbitmq_connection = FakeConnection(rabbitmq_connected)


async def _run_briefly(container: FakeHeartbeatContainer, heartbeat_file: Path) -> bool:
    """Roda o heartbeat por alguns ciclos e diz se o arquivo chegou a existir."""
    stop = asyncio.Event()
    task = asyncio.create_task(run_heartbeat(cast(WorkerContainer, container), stop))
    seen = False
    for _ in range(20):
        await asyncio.sleep(0.01)
        seen = seen or heartbeat_file.exists()
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    return seen


@pytest.mark.asyncio
async def test_touches_heartbeat_when_dependencies_are_up(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"

    seen = await _run_briefly(
        FakeHeartbeatContainer(heartbeat_file, FakeUrlRepository()), heartbeat_file
    )

    assert seen
    # Parada limpa remove o arquivo: um worker desligado não é saudável.
    assert not heartbeat_file.exists()


@pytest.mark.asyncio
async def test_no_heartbeat_without_mongo(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"

    seen = await _run_briefly(
        FakeHeartbeatContainer(heartbeat_file, UnreachableOutbox()), heartbeat_file
    )

    assert not seen


@pytest.mark.asyncio
async def test_no_heartbeat_without_rabbitmq(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    container = FakeHeartbeatContainer(
        heartbeat_file, FakeUrlRepository(), rabbitmq_connected=False
    )

    assert not await _run_briefly(container, heartbeat_file)


@pytest.mark.asyncio
async def test_removes_stale_heartbeat_on_start(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    heartbeat_file.touch()

    seen = await _run_briefly(
        FakeHeartbeatContainer(heartbeat_file, UnreachableOutbox()), heartbeat_file
    )

    assert not seen


@pytest.mark.asyncio
async def test_reports_pending_outbox_events(tmp_path: Path) -> None:
    outbox = FakeUrlRepository()
    for code in ("a", "b", "c"):
        await outbox.save(
            ShortUrl(
                code=ShortCode(code),
                original_url=OriginalUrl("https://example.com"),
                created_at=datetime.now(UTC),
            )
        )

    await _run_briefly(FakeHeartbeatContainer(tmp_path / "hb", outbox), tmp_path / "hb")

    assert sample("url_shortener_outbox_pending_events") == 3


def test_heartbeat_is_fresh_within_tolerance(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    heartbeat_file.touch()
    now = time.time()

    assert is_heartbeat_fresh(heartbeat_file, interval_seconds=10, now=now + 29)
    assert not is_heartbeat_fresh(heartbeat_file, interval_seconds=10, now=now + 31)


def test_missing_heartbeat_is_not_fresh(tmp_path: Path) -> None:
    assert not is_heartbeat_fresh(tmp_path / "nao-existe", interval_seconds=10, now=time.time())


def test_healthcheck_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from url_shortener.config import get_settings
    from url_shortener.interface.worker import healthcheck

    heartbeat_file = tmp_path / "heartbeat"
    monkeypatch.setenv("APP_WORKER_HEARTBEAT_FILE", str(heartbeat_file))
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit) as missing:
            healthcheck.main()
        heartbeat_file.touch()
        with pytest.raises(SystemExit) as fresh:
            healthcheck.main()
    finally:
        get_settings.cache_clear()

    assert missing.value.code == 1
    assert fresh.value.code == 0
