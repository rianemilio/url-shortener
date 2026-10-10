import pytest

from tests.fakes.fake_cache import FakeCache
from tests.fakes.fake_code_generator import FakeCodeGenerator, ScriptedCodeGenerator
from tests.fakes.fake_url_repository import FakeUrlRepository
from url_shortener.application.commands.create_short_url import (
    CreateShortUrlCommand,
    CreateShortUrlCommandHandler,
)
from url_shortener.application.exceptions import ShortCodeConflictError
from url_shortener.application.ports.code_generator_port import CodeGeneratorPort
from url_shortener.domain.exceptions import InvalidUrlError


def make_handler(
    code_generator: CodeGeneratorPort | None = None,
    repo: FakeUrlRepository | None = None,
) -> tuple[CreateShortUrlCommandHandler, FakeUrlRepository, FakeCache]:
    repo = repo or FakeUrlRepository()
    cache = FakeCache()
    handler = CreateShortUrlCommandHandler(
        url_repository=repo,
        cache=cache,
        code_generator=code_generator or FakeCodeGenerator(start=1),
        blocked_hosts=["sho.rt"],
    )
    return handler, repo, cache


@pytest.mark.asyncio
async def test_creates_and_persists_short_url() -> None:
    handler, repo, _cache = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com/page"))

    assert str(result.original_url) == "https://example.com/page"
    stored = await repo.find_by_code(result.code)
    assert stored is not None
    assert stored.click_count == 0


@pytest.mark.asyncio
async def test_populates_cache_after_create() -> None:
    handler, _repo, cache = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com"))

    cached = await cache.get(result.code)
    assert cached is not None
    assert str(cached) == "https://example.com"


@pytest.mark.asyncio
async def test_leaves_url_created_pending_in_outbox() -> None:
    handler, repo, _cache = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com"))

    [event] = await repo.pending(limit=10)
    assert event.code == str(result.code)
    assert event.original_url == "https://example.com"


@pytest.mark.asyncio
async def test_rejects_invalid_url() -> None:
    handler, _repo, _cache = make_handler()

    with pytest.raises(InvalidUrlError):
        await handler.handle(CreateShortUrlCommand(url="not-a-url"))


@pytest.mark.parametrize(
    "url", ["https://sho.rt/abc1234", "http://SHO.RT:8000/x", "https://sho.rt./abc1234"]
)
@pytest.mark.asyncio
async def test_rejects_links_to_the_shortener_itself(url: str) -> None:
    handler, repo, _cache = make_handler()

    with pytest.raises(InvalidUrlError):
        await handler.handle(CreateShortUrlCommand(url=url))
    assert repo.saved == {}


@pytest.mark.asyncio
async def test_allows_subdomains_of_the_shortener() -> None:
    handler, _repo, _cache = make_handler()

    result = await handler.handle(CreateShortUrlCommand(url="https://docs.sho.rt/page"))

    assert str(result.original_url) == "https://docs.sho.rt/page"


@pytest.mark.asyncio
async def test_retries_with_a_new_code_on_conflict() -> None:
    repo = FakeUrlRepository()
    first, _, _ = make_handler(ScriptedCodeGenerator(["taken"]), repo)
    await first.handle(CreateShortUrlCommand(url="https://example.com/old"))
    handler, _, _ = make_handler(ScriptedCodeGenerator(["taken", "free"]), repo)

    result = await handler.handle(CreateShortUrlCommand(url="https://example.com/new"))

    assert str(result.code) == "free"
    assert str(repo.saved["taken"].original_url) == "https://example.com/old"


@pytest.mark.asyncio
async def test_gives_up_after_repeated_conflicts() -> None:
    repo = FakeUrlRepository()
    seed, _, _ = make_handler(ScriptedCodeGenerator(["a", "b", "c"]), repo)
    for _ in range(3):
        await seed.handle(CreateShortUrlCommand(url="https://example.com"))
    handler, _, _ = make_handler(ScriptedCodeGenerator(["a", "b", "c", "d"]), repo)

    with pytest.raises(ShortCodeConflictError):
        await handler.handle(CreateShortUrlCommand(url="https://example.com/new"))
    assert "d" not in repo.saved
