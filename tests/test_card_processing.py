from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock

from roombeacon_crawler.application.crawl.card_processing import (
    CardProcessingOutcome,
    CardProcessingProcessor,
)
from roombeacon_crawler.application.crawl.session_state import CrawlSessionState
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.policies.detail_refresh_policy import DetailRefreshPolicy


class TestCardProcessingProcessor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        self.adapter = MagicMock(SOURCE_NAME="example")
        self.detail_pipeline = MagicMock()
        self.detail_pipeline.execute = AsyncMock()
        self.deferred_repository = MagicMock()
        self.deferred_repository.enqueue.return_value = 1
        self.processor = CardProcessingProcessor(
            adapter=self.adapter,
            detail_pipeline=self.detail_pipeline,
            detail_refresh_policy=DetailRefreshPolicy(default_ttl_hours=24),
            deferred_repository=self.deferred_repository,
        )

    @staticmethod
    def card(title: str = "Room one") -> ListingCardRaw:
        return ListingCardRaw(
            source="example",
            listing_id="listing-1",
            detail_url="https://example.test/listing-1",
            title_raw=title,
            price_raw="100",
            area_raw="20",
            location_raw="District 1",
            posted_at_raw=None,
        )

    async def process(
        self,
        state: CrawlSessionState,
        *,
        card: ListingCardRaw | None = None,
        crawl_details: bool = True,
        budget: int | None = 10,
    ):
        return await self.processor.execute(
            card=card or self.card(),
            state=state,
            run_id="run-1",
            target_id="target-1",
            now=self.now,
            crawl_details=crawl_details,
            max_details_per_run=budget,
        )

    async def test_new_listing_is_recorded(self):
        state = CrawlSessionState()

        result = await self.process(state, crawl_details=False)

        self.assertTrue(result.is_new)
        self.assertFalse(result.counts_as_known)
        self.assertEqual(result.outcome, CardProcessingOutcome.LIGHTWEIGHT)
        self.assertEqual(state.new_listing_ids, ["listing-1"])
        self.assertEqual(len(state.bronze_records), 1)
        self.assertEqual(state.full_address_missing, 1)
        self.assertEqual(state.coarse_only_address, 1)

    async def test_known_unchanged_listing_within_ttl_is_lightweight(self):
        card = self.card()
        fingerprint = self.processor._fingerprint(card)
        recent = (self.now - timedelta(hours=2)).isoformat()
        state = CrawlSessionState(
            known_seen_ids={"listing-1"},
            known_seen_meta={
                "listing-1": {
                    "card_fingerprint": fingerprint,
                    "last_detailed_at": recent,
                    "detail_status": "SUCCESS_WITH_ADDRESS",
                }
            },
        )

        result = await self.process(state, card=card)

        self.assertTrue(result.counts_as_known)
        self.assertFalse(result.content_changed)
        self.assertEqual(result.outcome, CardProcessingOutcome.LIGHTWEIGHT)
        self.assertEqual(state.skipped_known_unchanged_ttl, 1)
        self.assertEqual(
            state.updated_seen_meta["listing-1"]["detail_status"],
            "SUCCESS_WITH_ADDRESS",
        )
        self.detail_pipeline.execute.assert_not_awaited()

    async def test_known_missing_address_within_ttl_forces_detail_refresh(self):
        card = self.card()
        recent = (self.now - timedelta(hours=2)).isoformat()
        state = CrawlSessionState(
            known_seen_ids={"listing-1"},
            known_seen_meta={
                "listing-1": {
                    "card_fingerprint": self.processor._fingerprint(card),
                    "last_detailed_at": recent,
                    "detail_status": "SUCCESS_WITHOUT_ADDRESS",
                }
            },
        )
        detail_raw = MagicMock()
        detail_raw.address_raw = "12 Example Street, District 1"
        self.detail_pipeline.execute.return_value = (MagicMock(), detail_raw, MagicMock())

        result = await self.process(state, card=card)

        self.assertEqual(result.outcome, CardProcessingOutcome.DETAIL_SUCCEEDED)
        self.assertEqual(state.detail_requested, 1)
        self.assertEqual(
            state.updated_seen_meta["listing-1"]["detail_status"],
            "SUCCESS_WITH_ADDRESS",
        )
        self.detail_pipeline.execute.assert_awaited_once()

    async def test_changed_listing_forces_detail_refresh(self):
        state = CrawlSessionState(
            known_seen_ids={"listing-1"},
            known_seen_meta={
                "listing-1": {
                    "card_fingerprint": "old-fingerprint",
                    "last_detailed_at": (self.now - timedelta(hours=2)).isoformat(),
                }
            },
        )
        detail_bronze = MagicMock()
        detail_raw = MagicMock()
        self.detail_pipeline.execute.return_value = (
            detail_bronze,
            detail_raw,
            MagicMock(),
        )

        result = await self.process(state, card=self.card("Changed title"))

        self.assertTrue(result.content_changed)
        self.assertEqual(result.outcome, CardProcessingOutcome.DETAIL_SUCCEEDED)
        self.assertEqual(state.records_changed, 1)
        self.assertEqual(state.detail_requests_forced_by_change, 1)

    async def test_duplicate_in_same_run_is_skipped(self):
        state = CrawlSessionState(seen_in_current_run={"listing-1"})

        result = await self.process(state)

        self.assertEqual(result.outcome, CardProcessingOutcome.DUPLICATE)
        self.assertTrue(result.counts_as_known)
        self.assertEqual(state.duplicates_skipped, 1)
        self.assertEqual(state.detail_required, 0)
        self.detail_pipeline.execute.assert_not_awaited()

    async def test_expired_ttl_fetches_detail_successfully(self):
        card = self.card()
        state = CrawlSessionState(
            known_seen_ids={"listing-1"},
            known_seen_meta={
                "listing-1": {
                    "card_fingerprint": self.processor._fingerprint(card),
                    "last_detailed_at": (self.now - timedelta(hours=25)).isoformat(),
                }
            },
        )
        detail_raw = MagicMock()
        detail_raw.address_raw = "12 Example Street, District 1"
        self.detail_pipeline.execute.return_value = (MagicMock(), detail_raw, MagicMock())

        result = await self.process(state, card=card)

        self.assertEqual(result.outcome, CardProcessingOutcome.DETAIL_SUCCEEDED)
        self.assertEqual(state.detail_requested, 1)
        self.assertEqual(state.detail_succeeded, 1)
        self.assertEqual(state.full_address_present, 1)
        self.assertEqual(state.detail_address_extracted, 1)
        detail_target = self.detail_pipeline.execute.await_args.kwargs["target"]
        self.assertEqual(detail_target.listing_id, "listing-1")

    async def test_detail_failure_keeps_lightweight_observation(self):
        state = CrawlSessionState()
        self.detail_pipeline.execute.return_value = (None, None, MagicMock())

        result = await self.process(state)

        self.assertEqual(result.outcome, CardProcessingOutcome.DETAIL_FAILED)
        self.assertEqual(state.detail_failed, 1)
        self.assertEqual(len(state.bronze_records), 1)
        self.assertEqual(state.full_address_missing, 1)
        self.assertEqual(state.detail_address_parse_failed, 0)

    async def test_parsed_detail_without_address_is_counted_separately(self):
        state = CrawlSessionState()
        detail_raw = MagicMock()
        detail_raw.address_raw = None
        self.detail_pipeline.execute.return_value = (MagicMock(), detail_raw, MagicMock())

        result = await self.process(state)

        self.assertEqual(result.outcome, CardProcessingOutcome.DETAIL_SUCCEEDED)
        self.assertEqual(state.full_address_missing, 1)
        self.assertEqual(state.coarse_only_address, 1)
        self.assertEqual(state.detail_address_parse_failed, 1)
        self.assertIsNone(state.updated_seen_meta["listing-1"]["last_detailed_at"])
        self.assertEqual(
            state.updated_seen_meta["listing-1"]["detail_status"],
            "ADDRESS_MISSING_RETRY",
        )
        self.deferred_repository.record_success.assert_not_called()
        self.deferred_repository.record_failure.assert_called_once_with(
            "example",
            "target-1",
            "listing-1",
            error="ADDRESS_EXTRACTION_MISSING",
            is_terminal=False,
            now=self.now,
        )

    async def test_exhausted_budget_enqueues_deferred_detail(self):
        state = CrawlSessionState(details_crawled_count=2)

        result = await self.process(state, budget=2)

        self.assertEqual(result.outcome, CardProcessingOutcome.DEFERRED)
        self.assertEqual(state.skipped_request_budget, 1)
        self.assertEqual(state.deferred_added, 1)
        self.deferred_repository.enqueue.assert_called_once()
        self.detail_pipeline.execute.assert_not_awaited()

    async def test_discovery_first_always_persists_lightweight_and_defers(self):
        state = CrawlSessionState()

        result = await self.processor.execute(
            card=self.card(),
            state=state,
            run_id="run-1",
            target_id="target-1",
            now=self.now,
            crawl_details=True,
            max_details_per_run=10,
            defer_details_for_discovery=True,
        )

        self.assertEqual(result.outcome, CardProcessingOutcome.DEFERRED)
        self.assertEqual(len(state.bronze_records), 1)
        self.assertEqual(state.skipped_deferred_for_discovery, 1)
        self.assertEqual(state.skipped_request_budget, 0)
        self.deferred_repository.enqueue.assert_called_once()
        self.detail_pipeline.execute.assert_not_awaited()

    async def test_same_run_deferred_success_is_not_requeued_by_page_processing(self):
        card = self.card()
        fingerprint = self.processor._fingerprint(card)
        detailed_at = self.now.isoformat()
        state = CrawlSessionState(
            known_seen_ids={"listing-1"},
            known_seen_meta={
                "listing-1": {
                    "card_fingerprint": fingerprint,
                    "last_detailed_at": None,
                }
            },
            updated_seen_meta={
                "listing-1": {
                    "card_fingerprint": fingerprint,
                    "last_detailed_at": detailed_at,
                    "detail_status": "SUCCESS_WITH_ADDRESS",
                }
            },
            details_crawled_count=10,
        )

        result = await self.process(state, card=card, budget=10)

        self.assertEqual(result.outcome, CardProcessingOutcome.LIGHTWEIGHT)
        self.assertEqual(state.skipped_known_unchanged_ttl, 1)
        self.assertEqual(state.updated_seen_meta["listing-1"]["last_detailed_at"], detailed_at)
        self.assertEqual(
            state.updated_seen_meta["listing-1"]["detail_status"],
            "SUCCESS_WITH_ADDRESS",
        )
        self.deferred_repository.enqueue.assert_not_called()
        self.detail_pipeline.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
