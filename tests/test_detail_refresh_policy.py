from datetime import datetime, timedelta, timezone
import unittest

from roombeacon_crawler.policies.detail_refresh_policy import DetailRefreshPolicy


class TestDetailRefreshPolicy(unittest.TestCase):
    """Kiểm thử chính sách làm mới chi tiết (Detail Refresh Policy)."""

    def setUp(self):
        self.policy = DetailRefreshPolicy(default_ttl_hours=24)
        self.now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

    def test_new_listing_always_triggers_refresh(self):
        """Tin đăng mới (NEW) bắt buộc kích hoạt cào chi tiết."""
        decision = self.policy.evaluate(
            is_new=True,
            card_changed=False,
            last_detailed_at=None,
            current_time=self.now,
        )
        self.assertTrue(decision.should_refresh)
        self.assertEqual(decision.reason, "NEW_LISTING")

    def test_known_listing_with_changed_card_triggers_refresh(self):
        """Tin đăng đã biết nhưng có trường nhẹ bị thay đổi bắt buộc kích hoạt cào chi tiết (Forced Refresh)."""
        recent_detailed = (self.now - timedelta(hours=2)).isoformat()
        decision = self.policy.evaluate(
            is_new=False,
            card_changed=True,
            last_detailed_at=recent_detailed,
            current_time=self.now,
        )
        self.assertTrue(decision.should_refresh)
        self.assertEqual(decision.reason, "CARD_CHANGED")

    def test_known_listing_without_prior_detail_triggers_refresh(self):
        """Tin đã biết nhưng chưa từng có bản ghi detail đầy đủ bắt buộc fetch detail."""
        decision = self.policy.evaluate(
            is_new=False,
            card_changed=False,
            last_detailed_at=None,
            current_time=self.now,
        )
        self.assertTrue(decision.should_refresh)
        self.assertEqual(decision.reason, "NO_PRIOR_DETAIL")

    def test_known_listing_with_missing_address_bypasses_ttl(self):
        recent_detailed = (self.now - timedelta(hours=2)).isoformat()
        decision = self.policy.evaluate(
            is_new=False,
            card_changed=False,
            last_detailed_at=recent_detailed,
            current_time=self.now,
            detail_status="ADDRESS_MISSING_RETRY",
        )

        self.assertTrue(decision.should_refresh)
        self.assertEqual(decision.reason, "ADDRESS_MISSING")

    def test_known_listing_unchanged_within_ttl_skips_refresh(self):
        """Tin đã biết, không đổi và còn trong hạn TTL (< 24h) BỎ QUA network request detail."""
        recent_detailed = (self.now - timedelta(hours=5)).isoformat()
        decision = self.policy.evaluate(
            is_new=False,
            card_changed=False,
            last_detailed_at=recent_detailed,
            current_time=self.now,
        )
        self.assertFalse(decision.should_refresh)
        self.assertEqual(decision.reason, "UNCHANGED_WITHIN_TTL")

    def test_known_listing_unchanged_after_ttl_triggers_refresh(self):
        """Tin đã biết, không đổi nhưng đã quá hạn TTL (>= 24h) kích hoạt làm mới định kỳ."""
        old_detailed = (self.now - timedelta(hours=25)).isoformat()
        decision = self.policy.evaluate(
            is_new=False,
            card_changed=False,
            last_detailed_at=old_detailed,
            current_time=self.now,
        )
        self.assertTrue(decision.should_refresh)
        self.assertEqual(decision.reason, "TTL_EXPIRED")


if __name__ == "__main__":
    unittest.main()
