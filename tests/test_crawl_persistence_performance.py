"""Regression tests for run-scoped transports and persistence round trips."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from pymysql.err import IntegrityError as PyMySQLIntegrityError
from sqlalchemy.exc import IntegrityError

from roombeacon_crawler.application.persistence.persist_observations import (
    PersistBronzeObservationsUseCase,
)
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import (
    MySQLObservationRepository,
)
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import (
    MySQLPostChildrenRepository,
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


class _PersistenceResult:
    def __init__(self, *, lastrowid=0, rowcount=0, row=None):
        self.lastrowid = lastrowid
        self.rowcount = rowcount
        self._row = row

    def fetchone(self):
        return self._row


class _SameRunConnection:
    TABLES = (
        "rental_post_versions",
        "post_prices",
        "post_addresses",
        "post_details",
        "post_images",
        "post_amenities",
        "post_fees",
        "post_contacts",
        "post_attributes",
        "post_status_history",
    )

    def __init__(self):
        self.version_ids = {}
        self.counts = {table: 0 for table in self.TABLES}

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        parameter_map = params if isinstance(params, dict) else {}
        identity = parameter_map.get("rental_post_id"), parameter_map.get("crawl_run_id")
        if sql.startswith("SELECT id FROM rental_post_versions"):
            version_id = self.version_ids.get(identity)
            row = (version_id,) if version_id is not None else None
            return _PersistenceResult(row=row)
        if "INSERT INTO rental_post_versions" in sql:
            if identity in self.version_ids:
                if "ON DUPLICATE KEY UPDATE" in sql:
                    return _PersistenceResult(lastrowid=self.version_ids[identity], rowcount=1)
                raise IntegrityError(
                    sql,
                    params,
                    PyMySQLIntegrityError(1062, "Duplicate entry for key 'uk_post_run'"),
                )
            version_id = 100 + len(self.version_ids)
            self.version_ids[identity] = version_id
            self.counts["rental_post_versions"] += 1
            return _PersistenceResult(lastrowid=version_id, rowcount=1)
        for table in self.TABLES[1:]:
            if f"INSERT INTO {table}" in sql:
                self.counts[table] += len(params) if isinstance(params, list) else 1
                return _PersistenceResult(lastrowid=1, rowcount=1)
        raise AssertionError(f"Unexpected SQL: {sql}")


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


def test_new_observation_insert_returns_created_true_without_rowcount_inference():
    result = MagicMock(lastrowid=100, rowcount=0)
    connection = MagicMock()
    connection.execute.return_value = result

    version_id, inserted = MySQLObservationRepository(connection).insert_observation(
        _observation(), post_id=42
    )

    assert (version_id, inserted) == (100, True)
    connection.execute.assert_called_once()


def test_rental_post_upsert_bounds_title_to_live_column_contract():
    result = MagicMock(lastrowid=42, rowcount=1)
    connection = MagicMock()
    connection.execute.return_value = result
    observation = _observation()
    observation.title_raw = "T" * 28_562

    MySQLRentalPostRepository(connection).upsert_post(observation, platform_id=7)

    params = connection.execute.call_args.args[1]
    assert params["title_raw"] == "T" * 500
    assert observation.title_raw == "T" * 28_562


def test_observation_upsert_bounds_title_but_preserves_source_payload():
    result = MagicMock(lastrowid=100, rowcount=1)
    connection = MagicMock()
    connection.execute.return_value = result
    observation = _observation()
    oversized_title = "T" * 31_449
    observation.title_raw = oversized_title
    observation.source_payload = {"title_raw": oversized_title, "source": "testsource"}

    MySQLObservationRepository(connection).insert_observation(observation, post_id=42)

    params = connection.execute.call_args.args[1]
    assert params["title_raw"] == "T" * 500
    assert json.loads(params["source_payload"])["title_raw"] == oversized_title
    assert observation.title_raw == oversized_title


def test_second_same_run_replay_keeps_aggregate_counts_unchanged():
    connection = _SameRunConnection()
    platform = MagicMock()
    platform.get_or_create_platform.return_value = 7
    posts = MagicMock()
    posts.upsert_post.side_effect = [(42, True), (42, False)]
    versions = MySQLObservationRepository(connection)
    children = MySQLPostChildrenRepository(connection)
    transaction = MagicMock()
    transaction.connection = connection
    use_case = PersistBronzeObservationsUseCase(
        platform, posts, versions, children, transaction
    )
    observation = _observation()
    observation.price_raw = "3.2 triệu/tháng"
    observation.area_raw = "30 m2"
    observation.address_raw = "Quận 2, Hồ Chí Minh"
    observation.image_urls_raw = ["https://example.invalid/one.jpg"]
    observation.amenities_raw = ["Máy lạnh"]
    observation.seller_name_raw = "Chủ nhà"

    first = use_case.execute([observation])
    counts_after_first = dict(connection.counts)
    second = use_case.execute([observation])

    assert first.observations_inserted == 1
    assert second.observations_inserted == 0
    assert second.technical_duplicates == 1
    assert connection.counts == counts_after_first == {
        "rental_post_versions": 1,
        "post_prices": 1,
        "post_addresses": 1,
        "post_details": 1,
        "post_images": 1,
        "post_amenities": 1,
        "post_fees": 0,
        "post_contacts": 1,
        "post_attributes": 0,
        "post_status_history": 0,
    }
    assert transaction.commit.call_count == 2


def test_new_run_for_same_post_creates_one_new_aggregate():
    connection = _SameRunConnection()
    platform = MagicMock()
    platform.get_or_create_platform.return_value = 7
    posts = MagicMock()
    posts.upsert_post.side_effect = [(42, True), (42, False)]
    transaction = MagicMock()
    transaction.connection = connection
    use_case = PersistBronzeObservationsUseCase(
        platform,
        posts,
        MySQLObservationRepository(connection),
        MySQLPostChildrenRepository(connection),
        transaction,
    )
    first_observation = _observation()
    first_observation.price_raw = "3.2 triệu/tháng"
    second_observation = _observation()
    second_observation.run_id = "run-next"
    second_observation.price_raw = "3.2 triệu/tháng"

    first = use_case.execute([first_observation])
    second = use_case.execute([second_observation])

    assert first.observations_inserted == second.observations_inserted == 1
    assert first.technical_duplicates == second.technical_duplicates == 0
    assert connection.counts["rental_post_versions"] == 2
    assert connection.counts["post_prices"] == 2
    assert connection.counts["post_details"] == 2
