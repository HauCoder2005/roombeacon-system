from datetime import datetime, timezone
import io
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from roombeacon_crawler.policies.robots_policy import (
    CachedRobotsEntry,
    RobotsDocument,
    RobotsEvaluationResult,
    RobotsPolicy,
    RobotsRule,
)


class TestRobotsPolicyRFC9309(unittest.TestCase):
    """Bộ kiểm thử tuân thủ nghiêm ngặt tiêu chuẩn RFC 9309 Robots Exclusion Protocol."""

    def test_robots_rule_compilation_and_matching(self) -> None:
        """Kiểm tra biên dịch pattern và khớp đường dẫn (wildcard '*' và '$')."""
        # Exact prefix match
        rule1 = RobotsRule.create("/private", allow=False)
        self.assertTrue(rule1.matches("/private"))
        self.assertTrue(rule1.matches("/private/sub"))
        self.assertFalse(rule1.matches("/public"))
        self.assertEqual(rule1.length, len("/private"))

        # Wildcard pattern (NhaTot style)
        rule2 = RobotsRule.create("/*page=", allow=False)
        self.assertTrue(rule2.matches("/thue-phong-tro-tp-ho-chi-minh?page=2"))
        self.assertTrue(rule2.matches("/category/nha-dat?page=10"))
        self.assertFalse(rule2.matches("/thue-phong-tro-tp-ho-chi-minh"))

        # End of path pattern '$'
        rule3 = RobotsRule.create("/exact$", allow=False)
        self.assertTrue(rule3.matches("/exact"))
        self.assertFalse(rule3.matches("/exact/sub"))

    def test_longest_match_and_allow_wins_ties(self) -> None:
        """Kiểm tra luật rule dài nhất thắng, và khi bằng độ dài thì Allow thắng Disallow."""
        # 1. Rule dài hơn thắng
        text1 = """
User-agent: *
Disallow: /news/
Allow: /news/2026/
"""
        doc1 = RobotsDocument.parse_text(text1)
        # /news/2026/post-1 -> Khớp cả /news/ (độ dài 6) và /news/2026/ (độ dài 11) -> Allow wins (11 > 6)
        decision, ua, rule, rule_type = doc1.evaluate("/news/2026/post-1", "RoomBeaconCrawler/0.1")
        self.assertEqual(decision, "ALLOWED")
        self.assertEqual(rule_type, "ALLOW")

        # /news/old-post -> Chỉ khớp /news/ -> Disallow
        decision2, _, _, rule_type2 = doc1.evaluate("/news/old-post", "RoomBeaconCrawler/0.1")
        self.assertEqual(decision2, "DENIED")
        self.assertEqual(rule_type2, "DISALLOW")

        # 2. Bằng độ dài -> Allow thắng (RFC 9309 Section 2.2.2)
        text2 = """
User-agent: *
Disallow: /item
Allow: /item
"""
        doc2 = RobotsDocument.parse_text(text2)
        decision3, _, _, rule_type3 = doc2.evaluate("/item/123", "RoomBeaconCrawler/0.1")
        self.assertEqual(decision3, "ALLOWED")
        self.assertEqual(rule_type3, "ALLOW")

    def test_user_agent_product_token_and_group_precedence(self) -> None:
        """Kiểm tra ưu tiên nhóm User-Agent riêng (RoomBeaconCrawler) trước nhóm '*'."""
        text = """
User-agent: Googlebot
Disallow: /google-blocked

User-agent: RoomBeaconCrawler
Disallow: /roombeacon-only-blocked
Allow: /shared-allowed

User-agent: *
Disallow: /
"""
        doc = RobotsDocument.parse_text(text)

        # Khớp nhóm riêng RoomBeaconCrawler: /shared-allowed được phép
        dec1, ua1, _, _ = doc.evaluate("/shared-allowed", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec1, "ALLOWED")
        self.assertEqual(ua1, "RoomBeaconCrawler")

        # Khớp nhóm riêng RoomBeaconCrawler: /roombeacon-only-blocked bị cấm
        dec2, ua2, _, _ = doc.evaluate("/roombeacon-only-blocked", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec2, "DENIED")
        self.assertEqual(ua2, "RoomBeaconCrawler")

        # Không có nhóm riêng cho BotKhac -> Fallback nhóm '*' (Disallow: /)
        dec3, ua3, _, _ = doc.evaluate("/other-path", "OtherCrawler/1.0")
        self.assertEqual(dec3, "DENIED")
        self.assertEqual(ua3, "*")

    def test_no_matching_group_defaults_to_allow(self) -> None:
        """Nếu robots.txt chỉ có nhóm cho crawler khác mà không có '*' hay RoomBeaconCrawler -> Cho phép tất cả."""
        text = """
User-agent: BadBot
Disallow: /
"""
        doc = RobotsDocument.parse_text(text)
        dec, ua, rule, rule_type = doc.evaluate("/any-path", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec, "ALLOWED")
        self.assertEqual(rule_type, "DEFAULT_ALLOW")

    def test_nhatot_pagination_disallowed_while_landing_allowed(self) -> None:
        """Case study NhaTot: Phân trang ?page= bị cấm bởi /*page= trong khi landing page được phép."""
        text = """
User-agent: *
Disallow: /*page=
Disallow: /admin/
Allow: /
"""
        doc = RobotsDocument.parse_text(text)

        # 1. Landing category URL không có ?page= -> ALLOWED
        dec1, _, _, _ = doc.evaluate("/thue-phong-tro-tp-ho-chi-minh", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec1, "ALLOWED")

        # 2. URL phân trang ?page=2 -> DENIED
        dec2, _, matched_rule, rule_type = doc.evaluate(
            "/thue-phong-tro-tp-ho-chi-minh?page=2", "RoomBeaconCrawler/0.1"
        )
        self.assertEqual(dec2, "DENIED")
        self.assertEqual(rule_type, "DISALLOW")
        self.assertEqual(matched_rule, "Disallow: /*page=")

    @patch("urllib.request.urlopen")
    def test_http_403_returns_unavailable_not_denied(self, mock_urlopen: MagicMock) -> None:
        """Kiểm tra HTTP 403 Forbidden trên /robots.txt trả về UNAVAILABLE (không phải explicit DENIED)."""
        http_error = urllib.error.HTTPError(
            url="https://muaban.net/robots.txt",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        mock_urlopen.side_effect = http_error

        policy = RobotsPolicy()
        res = policy.evaluate("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro")

        self.assertEqual(res.decision, "UNAVAILABLE")
        self.assertEqual(res.robots_state, "UNAVAILABLE")
        self.assertEqual(res.http_status, 403)
        self.assertFalse(res.explicit_denial)
        self.assertEqual(res.decision_source, "RFC_9309_UNAVAILABLE")

        # is_allowed() cho 4xx trả về True (RFC 9309 2.3.1.2: No restrictions assumed)
        self.assertTrue(policy.is_allowed("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro"))

    @patch("urllib.request.urlopen")
    def test_http_404_returns_unavailable_not_denied(self, mock_urlopen: MagicMock) -> None:
        """Kiểm tra HTTP 404 Not Found trên /robots.txt trả về UNAVAILABLE (No restrictions)."""
        http_error = urllib.error.HTTPError(
            url="https://example.com/robots.txt",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        mock_urlopen.side_effect = http_error

        policy = RobotsPolicy()
        res = policy.evaluate("https://example.com/listings")

        self.assertEqual(res.decision, "UNAVAILABLE")
        self.assertEqual(res.http_status, 404)
        self.assertFalse(res.explicit_denial)
        self.assertTrue(policy.is_allowed("https://example.com/listings"))

    @patch("urllib.request.urlopen")
    def test_http_500_and_network_error_returns_unreachable(self, mock_urlopen: MagicMock) -> None:
        """Kiểm tra HTTP 500 hoặc sự cố mạng trả về UNREACHABLE (RFC 9309: Conservative complete disallow)."""
        # 1. HTTP 500 Internal Server Error
        http_error = urllib.error.HTTPError(
            url="https://flaky-source.com/robots.txt",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )
        mock_urlopen.side_effect = http_error

        policy = RobotsPolicy()
        res = policy.evaluate("https://flaky-source.com/listings")

        self.assertEqual(res.decision, "UNREACHABLE")
        self.assertEqual(res.robots_state, "UNREACHABLE")
        self.assertEqual(res.http_status, 500)
        self.assertFalse(res.explicit_denial)
        self.assertEqual(res.decision_source, "RFC_9309_UNREACHABLE")
        # is_allowed() cho 5xx trả về False
        self.assertFalse(policy.is_allowed("https://flaky-source.com/listings"))

        # 2. Network Timeout Error
        mock_urlopen.side_effect = TimeoutError("Connection timed out after 10000ms")
        policy2 = RobotsPolicy()
        res2 = policy2.evaluate("https://timeout-source.com/listings")
        self.assertEqual(res2.decision, "UNREACHABLE")
        self.assertIsNone(res2.http_status)
        self.assertFalse(policy2.is_allowed("https://timeout-source.com/listings"))

    def test_politeness_extension_parsing(self) -> None:
        """Kiểm tra chỉ thị không chuẩn Crawl-delay được lưu vào metadata mà không ảnh hưởng tới rule parsing."""
        text = """
User-agent: *
Crawl-delay: 2.5
Disallow: /admin/
Allow: /
"""
        doc = RobotsDocument.parse_text(text)
        self.assertEqual(doc.crawl_delays.get("*"), 2.5)
        dec, _, _, _ = doc.evaluate("/admin/users", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec, "DENIED")

    @patch("urllib.request.urlopen")
    def test_robots_cache_avoids_repeated_network_fetches(self, mock_urlopen: MagicMock) -> None:
        """Kiểm tra bộ nhớ cache origin theo scheme + domain giúp tránh gọi lại mạng trong cùng TTL."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.geturl.return_value = "https://cached-site.com/robots.txt"
        mock_resp.headers = {"Content-Type": "text/plain"}
        mock_resp.read.return_value = b"User-agent: *\nDisallow: /temp/\n"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        policy = RobotsPolicy(cache_ttl_seconds=3600.0)

        # Lần 1: Fetch qua mạng
        res1 = policy.evaluate("https://cached-site.com/public")
        self.assertEqual(res1.decision, "ALLOWED")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Lần 2: Cùng domain -> Lấy từ cache, không gọi mạng lần 2
        res2 = policy.evaluate("https://cached-site.com/temp/file")
        self.assertEqual(res2.decision, "DENIED")
        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
