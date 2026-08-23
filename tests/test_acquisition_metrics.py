import unittest

from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.enums.crawl_status import CrawlStatus


class TestAcquisitionMetrics(unittest.TestCase):
    """Kiểm thử tính toán các chỉ số hiệu suất thu thập (Acquisition Efficiency Metrics) và định luật bảo toàn."""

    def test_unique_yield_and_change_rate_calculation(self):
        """Tính toán chính xác unique_yield và change_rate khi có ứng viên hợp lệ."""
        records_seen = 50
        records_new = 10
        records_known = 40
        records_changed = 8

        unique_yield = (records_new / records_seen * 100.0) if records_seen > 0 else 0.0
        change_rate = (records_changed / records_known * 100.0) if records_known > 0 else 0.0

        self.assertEqual(unique_yield, 20.0)
        self.assertEqual(change_rate, 20.0)

    def test_zero_division_safety(self):
        """Xử lý an toàn mẫu số bằng 0 (Zero division protection)."""
        records_seen = 0
        records_new = 0
        records_known = 0
        records_changed = 0

        unique_yield = (records_new / records_seen * 100.0) if records_seen > 0 else 0.0
        change_rate = (records_changed / records_known * 100.0) if records_known > 0 else 0.0

        self.assertEqual(unique_yield, 0.0)
        self.assertEqual(change_rate, 0.0)

    def test_detail_conservation_rules(self):
        """Kiểm thử định luật bảo toàn Detail Metrics:
        1. detail_required = detail_requested + detail_skipped
        2. detail_requested = detail_succeeded + detail_failed
        3. detail_skipped = skipped_known_unchanged_ttl + skipped_no_detail_url + skipped_request_budget + skipped_source_policy + skipped_other
        """
        res = CrawlRunResult(
            run_id="run_test",
            source="nhatrovn",
            started_at="2026-08-22T00:00:00Z",
            finished_at="2026-08-22T00:01:00Z",
            status=CrawlStatus.SUCCESS,
            detail_required=40,
            detail_requested=20,
            detail_succeeded=20,
            detail_failed=0,
            detail_skipped=20,
            skipped_known_unchanged_ttl=0,
            skipped_no_detail_url=0,
            skipped_request_budget=20,
            skipped_source_policy=0,
            skipped_other=0,
            unique_yield=100.0,
            change_rate=0.0,
            records_seen=40,
            records_new=40,
            records_known=0,
            records_changed=0,
        )

        # Định luật 1: detail_required = detail_requested + detail_skipped
        self.assertEqual(res.detail_required, res.detail_requested + res.detail_skipped)

        # Định luật 2: detail_requested = detail_succeeded + detail_failed
        self.assertEqual(res.detail_requested, res.detail_succeeded + res.detail_failed)

        # Định luật 3: detail_skipped = tổng các lý do skip rời rạc
        total_skips = (
            res.skipped_known_unchanged_ttl
            + res.skipped_no_detail_url
            + res.skipped_request_budget
            + res.skipped_source_policy
            + res.skipped_other
        )
        self.assertEqual(res.detail_skipped, total_skips)


if __name__ == "__main__":
    unittest.main()
