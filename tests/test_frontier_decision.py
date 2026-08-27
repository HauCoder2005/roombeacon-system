import unittest
from unittest.mock import MagicMock

from roombeacon_crawler.application.crawl.frontier_decision import (
    FrontierAction,
    FrontierDecisionProcessor,
    FrontierTransition,
)
from roombeacon_crawler.application.crawl.page_acquisition import (
    PageAcquisitionOutcome,
)
from roombeacon_crawler.application.crawl.session_state import CrawlSessionState
from roombeacon_crawler.enums.crawl_status import CrawlStatus


class TestFrontierDecisionProcessor(unittest.TestCase):
    def setUp(self):
        self.adapter = MagicMock()
        self.adapter.pagination.has_next_page.return_value = True
        self.processor = FrontierDecisionProcessor(adapter=self.adapter)

    def after_cards(self, state, **overrides):
        values = {
            "page_records_count": 2,
            "page_new_count": 2,
            "page_known_count": 0,
            "effective_max_records": 100,
            "stop_after_known_pages": 2,
            "raw_html": "<html />",
        }
        values.update(overrides)
        return self.processor.after_cards(state=state, **values)

    def test_normal_page_advances_historical_frontier(self):
        state = CrawlSessionState(
            is_bootstrap=True,
            current_page=21,
            effective_end_page=40,
        )

        decision = self.after_cards(state)

        self.assertEqual(decision.action, FrontierAction.CONTINUE)
        self.assertEqual(decision.transition, FrontierTransition.NEXT_PAGE)
        self.assertEqual(state.current_page, 22)
        self.assertIsNone(state.stop_reason)

    def test_source_end_completes_bootstrap(self):
        self.adapter.pagination.has_next_page.return_value = False
        state = CrawlSessionState(
            is_bootstrap=True,
            current_page=30,
            effective_end_page=40,
        )

        decision = self.after_cards(state)

        self.assertEqual(decision.transition, FrontierTransition.SOURCE_END)
        self.assertTrue(decision.should_stop)
        self.assertTrue(state.bootstrap_completed)
        self.assertIsNone(state.bootstrap_next_page)
        self.assertEqual(state.stop_reason, "SOURCE_END")

    def test_known_page_streak_stops_incremental_run(self):
        state = CrawlSessionState(
            is_incremental=True,
            current_page=2,
            effective_end_page=10,
            known_page_streak=1,
        )

        decision = self.after_cards(
            state,
            page_new_count=0,
            page_known_count=2,
        )

        self.assertEqual(
            decision.transition,
            FrontierTransition.KNOWN_REGION_REACHED,
        )
        self.assertEqual(state.known_page_streak, 2)
        self.assertEqual(state.stop_reason, "KNOWN_REGION_REACHED")

    def test_max_pages_advances_bootstrap_resume_frontier(self):
        self.adapter.pagination.has_next_page.return_value = False
        state = CrawlSessionState(
            is_bootstrap=True,
            current_page=40,
            effective_end_page=40,
        )

        decision = self.after_cards(state)

        self.assertEqual(decision.transition, FrontierTransition.MAX_PAGES_REACHED)
        self.assertFalse(state.bootstrap_completed)
        self.assertEqual(state.bootstrap_next_page, 41)

    def test_forward_only_completes_after_one_ready_page(self):
        state = CrawlSessionState(
            is_forward_only=True,
            current_page=1,
            effective_end_page=1,
        )

        decision = self.after_cards(state)

        self.assertEqual(decision.transition, FrontierTransition.FORWARD_COMPLETE)
        self.assertEqual(state.stop_reason, "FORWARD_SCAN_COMPLETE")
        self.assertFalse(state.bootstrap_completed)
        self.adapter.pagination.has_next_page.assert_not_called()

    def test_robots_stop_preserves_current_bootstrap_page(self):
        state = CrawlSessionState(is_bootstrap=True, current_page=21)

        decision = self.processor.after_acquisition(
            state=state,
            outcome=PageAcquisitionOutcome.ROBOTS_DENIED,
            crawl_status=CrawlStatus.ROBOTS_DENIED,
        )

        self.assertEqual(decision.transition, FrontierTransition.ROBOTS_STOP)
        self.assertEqual(state.stop_reason, CrawlStatus.ROBOTS_DENIED)
        self.assertEqual(state.bootstrap_next_page, 21)

    def test_access_stop_preserves_current_bootstrap_page(self):
        state = CrawlSessionState(is_bootstrap=True, current_page=21)

        decision = self.processor.after_acquisition(
            state=state,
            outcome=PageAcquisitionOutcome.ACCESS_CHALLENGE,
            crawl_status=CrawlStatus.CLOUDFLARE_CHALLENGE,
        )

        self.assertEqual(decision.transition, FrontierTransition.ACCESS_STOP)
        self.assertEqual(state.stop_reason, CrawlStatus.CLOUDFLARE_CHALLENGE)
        self.assertEqual(state.bootstrap_next_page, 21)

    def test_fetch_failure_keeps_stop_reason_unset(self):
        state = CrawlSessionState(is_bootstrap=True, current_page=21)

        decision = self.processor.after_acquisition(
            state=state,
            outcome=PageAcquisitionOutcome.FETCH_ERROR,
            crawl_status=CrawlStatus.CONNECTION_ERROR,
        )

        self.assertEqual(decision.transition, FrontierTransition.FETCH_STOP)
        self.assertIsNone(state.stop_reason)
        self.assertEqual(state.bootstrap_next_page, 21)
        self.assertEqual(state.final_status, CrawlStatus.CONNECTION_ERROR)

    def test_max_records_advances_bootstrap_resume_page(self):
        state = CrawlSessionState(
            is_bootstrap=True,
            current_page=3,
            effective_end_page=20,
            bronze_records=[MagicMock(), MagicMock()],
        )

        decision = self.after_cards(state, effective_max_records=2)

        self.assertEqual(
            decision.transition,
            FrontierTransition.MAX_RECORDS_REACHED,
        )
        self.assertEqual(state.bootstrap_next_page, 4)
        self.assertFalse(state.bootstrap_completed)


if __name__ == "__main__":
    unittest.main()
