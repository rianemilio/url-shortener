from datetime import UTC, datetime

import pytest

from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortner.application.commands.register_click import (
    RegisterClickCommand,
    RegisterClickCommandHandler,
)
from url_shortner.domain.entities.short_url import ShortUrl
from url_shortner.domain.value_objects.original_url import OriginalUrl
from url_shortner.domain.value_objects.short_code import ShortCode


@pytest.mark.asyncio
async def test_increments_click_count() -> None:
    repo = FakeUrlRepository()
    code = ShortCode("abc")
    await repo.save(
        ShortUrl(
            code=code,
            original_url=OriginalUrl("https://example.com"),
            created_at=datetime.now(UTC),
        )
    )
    handler = RegisterClickCommandHandler(repo)

    await handler.handle(RegisterClickCommand(code="abc"))
    await handler.handle(RegisterClickCommand(code="abc"))

    stored = await repo.find_by_code(code)
    assert stored is not None
    assert stored.click_count == 2


@pytest.mark.asyncio
async def test_ignores_unknown_code_without_raising() -> None:
    handler = RegisterClickCommandHandler(FakeUrlRepository())

    await handler.handle(RegisterClickCommand(code="ghost"))
