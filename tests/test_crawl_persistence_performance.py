"""Regression tests for run-scoped transports and persistence round trips."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from roombeacon_crawler.application.persistence.persist_observations import (
    PersistBronzeObservationsUseCase,
)
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import (
    MySQLObservationRepository,
)
from roombeacon_crawler.infrastructure.mysql.repositories.rental_post_repository import (
    MySQLRentalPostRepository,
)


def _observation(listing_id: str = "1") -> BronzeObservation:
    return BronzeObservation(
        source="testsource",
        listing_id=listing_id,
        run_id="run-test",
        url=f"https://example.invalid/{listing_id}",
        title_raw="title",
    )


def test_http_client_is_reused_and_closed_per_fetcher():
    response = MagicMock(
        url="https://example.invalid/final",
        status_code=200,
        text="ok",
        headers={},
    )
    client = MagicMock(is_closed=False)
    client.get = AsyncMock(return_value=response)
    client.aclose = AsyncMock()

    with patch(
        "roombeacon_crawler.fetchers.http_fetcher.httpx.AsyncClient",
        return_value=client,
    ) as constructor:
        fetcher = HttpFetcher()
        async def execute():
            await fetcher.fetch("https://example.invalid/one")
            await fetcher.fetch("https://example.invalid/two")
            await fetcher.close()

        asyncio.run(execute())

    constructor.assert_called_once()
    assert client.get.await_count == 2
    client.aclose.assert_awaited_once()
    assert fetcher.client_count == 1


def test_browser_and_context_are_reused_while_pages_are_scoped():
    response = MagicMock(status=200)
    response.all_headers = AsyncMock(return_value={})
    pages = []
    for suffix in ("one", "two"):
        page = MagicMock(url=f"https://example.invalid/{suffix}")
        page.goto = AsyncMock(return_value=response)
        page.content = AsyncMock(return_value="ok")
        page.close = AsyncMock()
        pages.append(page)
    context = MagicMock()
    context.new_page = AsyncMock(side_effect=pages)
    context.close = AsyncMock()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.stop = AsyncMock()
    manager = MagicMock()
    manager.start = AsyncMock(return_value=playwright)

    with patch(
        "roombeacon_crawler.fetchers.browser_fetcher.async_playwright",
        return_value=manager,
    ):
        fetcher = BrowserFetcher()
        async def execute():
            await fetcher.fetch("https://example.invalid/one")
            await fetcher.fetch("https://example.invalid/two")
            await fetcher.close()

        asyncio.run(execute())

    playwright.chromium.launch.assert_awaited_once()
    browser.new_context.assert_awaited_once()
    assert context.new_page.await_count == 2
    assert all(page.close.await_count == 1 for page in pages)
    assert (fetcher.launch_count, fetcher.context_count, fetcher.page_count) == (1, 1, 2)


def test_platform_lookup_is_cached_within_one_batch():
    platform = MagicMock()
    platform.get_or_create_platform.return_value = 7
    posts = MagicMock()
    posts.upsert_post.side_effect = [(10, True), (11, True)]
    versions = MagicMock()
    versions.insert_observation.side_effect = [(100, True), (101, True)]
    children = MagicMock()
    transaction = MagicMock()
    transaction.connection = None
    use_case = PersistBronzeObservationsUseCase(
        platform, posts, versions, children, transaction
    )

    result = use_case.execute([_observation("1"), _observation("2")])

    platform.get_or_create_platform.assert_called_once()
    assert result.observations_inserted == 2


def test_rental_post_upsert_uses_one_identity_round_trip():
    result = MagicMock(lastrowid=42, rowcount=2)
    connection = MagicMock()
    connection.execute.return_value = result

    post_id, is_new = MySQLRentalPostRepository(connection).upsert_post(
        _observation(), platform_id=7
    )

    assert (post_id, is_new) == (42, False)
    connection.execute.assert_called_once()
    assert "LAST_INSERT_ID(id)" in str(connection.execute.call_args.args[0])


def test_observation_upsert_is_idempotent_in_one_round_trip():
    result = MagicMock(lastrowid=100, rowcount=0)
    connection = MagicMock()
    connection.execute.return_value = result

    version_id, inserted = MySQLObservationRepository(connection).insert_observation(
        _observation(), post_id=42
    )

    assert (version_id, inserted) == (100, False)
    connection.execute.assert_called_once()
    assert "LAST_INSERT_ID(id)" in str(connection.execute.call_args.args[0])
