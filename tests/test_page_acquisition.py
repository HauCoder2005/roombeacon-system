import unittest
from unittest.mock import AsyncMock, MagicMock

from roombeacon_crawler.application.crawl.page_acquisition import (
    PageAcquisitionOutcome,
    PageAcquisitionProcessor,
)
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw


class TestPageAcquisitionProcessor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.adapter = MagicMock()
        self.adapter.base_url = "https://example.test/rentals"
        self.adapter.SOURCE_NAME = "example"
        self.adapter.pagination.build_page_url.return_value = (
            "https://example.test/rentals?page=2"
        )
        self.pipeline = MagicMock()
        self.pipeline.execute = AsyncMock()
        self.processor = PageAcquisitionProcessor(
            adapter=self.adapter,
            listing_pipeline=self.pipeline,
            limit_per_page=25,
        )

    async def test_page_success_returns_cards_and_success_metrics(self):
        card = ListingCardRaw(
            source="example",
            listing_id="one",
            detail_url="https://example.test/one",
            title_raw="One",
            price_raw=None,
            area_raw=None,
            location_raw=None,
            posted_at_raw=None,
        )
        metadata = MagicMock(crawl_status=CrawlStatus.SUCCESS)
        self.pipeline.execute.return_value = ([card], [], metadata, "<html />")

        result = await self.processor.execute(
            run_id="run-1", page_number=2, forward_only=False
        )

        self.assertEqual(result.outcome, PageAcquisitionOutcome.READY)
        self.assertEqual(result.cards, [card])
        self.assertTrue(result.counts_as_attempt)
        self.assertTrue(result.counts_as_success)
        self.assertFalse(result.counts_as_failure)
        target = self.pipeline.execute.await_args.kwargs["target"]
        self.assertEqual(target.url, "https://example.test/rentals?page=2")
        self.assertEqual(target.page_number, 2)

    async def test_page_fetch_failure_is_explicit(self):
        metadata = MagicMock(crawl_status=CrawlStatus.CONNECTION_ERROR)
        self.pipeline.execute.return_value = ([], [], metadata, None)

        result = await self.processor.execute(
            run_id="run-2", page_number=1, forward_only=False
        )

        self.assertEqual(result.outcome, PageAcquisitionOutcome.FETCH_ERROR)
        self.assertTrue(result.counts_as_attempt)
        self.assertFalse(result.counts_as_success)
        self.assertTrue(result.counts_as_failure)

    async def test_parse_failure_is_not_swallowed(self):
        self.pipeline.execute.side_effect = ValueError("synthetic parser failure")

        with self.assertRaisesRegex(ValueError, "synthetic parser failure"):
            await self.processor.execute(
                run_id="run-3", page_number=1, forward_only=True
            )

    async def test_empty_successful_page_is_source_end(self):
        metadata = MagicMock(crawl_status=CrawlStatus.SUCCESS)
        self.pipeline.execute.return_value = ([], [], metadata, "<html />")

        result = await self.processor.execute(
            run_id="run-4", page_number=1, forward_only=True
        )

        self.assertEqual(result.outcome, PageAcquisitionOutcome.SOURCE_END)
        self.assertEqual(result.page_url, self.adapter.base_url)
        self.assertTrue(result.counts_as_attempt)
        self.assertFalse(result.counts_as_success)
        self.assertFalse(result.counts_as_failure)


if __name__ == "__main__":
    unittest.main()
