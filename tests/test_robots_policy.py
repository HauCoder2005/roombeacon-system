import io
import urllib.error
from urllib.error import HTTPError
import urllib.request
import unittest
from unittest.mock import MagicMock, patch

from roombeacon_crawler.models.source_qualification_result import (
    QualificationOverallStatus,
    RobotsQualificationStatus,
)
from roombeacon_crawler.policies.robots_policy import (
    RobotsDocument,
    RobotsPolicy,
    RobotsRule,
)
from roombeacon_crawler.services.source_qualifier import SourceQualifier


class TestRobotsPolicyForensicAndRFC9309(unittest.TestCase):
    """Kiểm thử toàn diện chính sách RobotsPolicy, cơ chế phân tích cú pháp RFC 9309 và tính bất biến theo thứ tự đánh giá."""

    def test_nhatot_public_robots_rules_matching(self) -> None:
        """Kiểm tra tài liệu robots.txt thực tế của NhaTot:
        - URL danh mục gốc (không có query param): ALLOWED
        - URL phân trang (?page=2): DENIED
        - URL tham số cấm khác (?q=, ?sort=): DENIED
        - URL cấm tuyệt đối (/notfound.htm): DENIED
        """
        nhatot_robots_text = """
User-agent: *
Allow: /
Sitemap: https://www.nhatot.com/sitemap-index.xml
Disallow: /notfound.htm
Disallow: /*undefined*
Disallow: /*tin-dang-tuong-tu*
Disallow: /user/
Disallow: /*chatroom*
Disallow: /*q=
Disallow: /*chi-tiet-danh-gia*
Disallow: /nhan/
Disallow: /*page=
Disallow: /*sort=
Disallow: /*contain_videos=
Disallow: /*distance=
Disallow: /dashboard
Disallow: /itunes*
Disallow: /feed

User-agent: ChatGPT-User
Allow: /
"""
        doc = RobotsDocument.parse_text(nhatot_robots_text)

        # 1. Base URL must be ALLOWED
        decision, matched_ua, matched_rule, rule_type = doc.evaluate(
            "/thue-phong-tro-tp-ho-chi-minh", "RoomBeaconCrawler/0.1"
        )
        self.assertEqual(decision, "ALLOWED")
        self.assertEqual(matched_ua, "*")
        self.assertEqual(matched_rule, "Allow: /")

        # 2. Page=2 URL must be DENIED
        decision, matched_ua, matched_rule, rule_type = doc.evaluate(
            "/thue-phong-tro-tp-ho-chi-minh?page=2", "RoomBeaconCrawler/0.1"
        )
        self.assertEqual(decision, "DENIED")
        self.assertEqual(matched_ua, "*")
        self.assertEqual(matched_rule, "Disallow: /*page=")

        # 3. Query q= URL must be DENIED
        decision, _, matched_rule, _ = doc.evaluate(
            "/thue-phong-tro-tp-ho-chi-minh?q=phongtro", "RoomBeaconCrawler/0.1"
        )
        self.assertEqual(decision, "DENIED")
        self.assertEqual(matched_rule, "Disallow: /*q=")

        # 4. /notfound.htm must be DENIED
        decision, _, matched_rule, _ = doc.evaluate(
            "/notfound.htm", "RoomBeaconCrawler/0.1"
        )
        self.assertEqual(decision, "DENIED")
        self.assertEqual(matched_rule, "Disallow: /notfound.htm")

    def test_evaluation_order_independence(self) -> None:
        """Kiểm tra tính độc lập của cache: Thứ tự đánh giá URL không làm sai lệch kết quả của nhau."""
        nhatot_robots_text = """
User-agent: *
Allow: /
Disallow: /*page=
"""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.headers = {"Content-Type": "text/plain"}
            mock_resp.read.return_value = nhatot_robots_text.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            # Run 1: Base first, then Page 2
            policy_1 = RobotsPolicy()
            dec_base_1, _ = policy_1.evaluate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh")
            dec_page_1, _ = policy_1.evaluate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2")

            self.assertEqual(dec_base_1, "ALLOWED")
            self.assertEqual(dec_page_1, "DENIED")

            # Run 2: Page 2 first, then Base
            policy_2 = RobotsPolicy()
            dec_page_2, _ = policy_2.evaluate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2")
            dec_base_2, _ = policy_2.evaluate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh")

            self.assertEqual(dec_page_2, "DENIED")
            self.assertEqual(dec_base_2, "ALLOWED")

    def test_robots_http_403_or_html_challenge_classified_as_error_not_denied(self) -> None:
        """Phản hồi HTTP 403 hoặc HTML WAF challenge phải được phân loại là ERROR/UNAVAILABLE, TUYỆT ĐỐI KHÔNG coi là explicit DENIED."""
        policy = RobotsPolicy()

        # Mock HTTP 403 Forbidden
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                url="https://example.com/robots.txt",
                code=403,
                msg="Forbidden",
                hdrs={},
                fp=io.BytesIO(b"Cloudflare WAF Block"),
            )
            decision, robots_url = policy.evaluate("https://example.com/listings")
            self.assertEqual(decision, "ERROR")
            self.assertNotEqual(decision, "DENIED")

        # Mock HTML response
        policy_html = RobotsPolicy()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            mock_resp.read.return_value = b"<html><body>Captcha Challenge</body></html>"
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            decision, _ = policy_html.evaluate("https://example.com/listings")
            self.assertEqual(decision, "ALLOWED")  # Fallback gracefully when robots is unavailable HTML

    def test_robots_http_404_410_is_allowed(self) -> None:
        """HTTP 404 hoặc 410 khi tải robots.txt đồng nghĩa website không có robots.txt -> Cho phép crawl (ALLOWED)."""
        policy = RobotsPolicy()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                url="https://no-robots.com/robots.txt",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=io.BytesIO(b""),
            )
            decision, _ = policy.evaluate("https://no-robots.com/rooms")
            self.assertEqual(decision, "ALLOWED")

    def test_specific_useragent_takes_precedence_over_wildcard(self) -> None:
        """Nhóm User-Agent khớp cụ thể (RoomBeaconCrawler) phải được ưu tiên trước nhóm User-agent: *."""
        robots_text = """
User-agent: *
Disallow: /

User-agent: RoomBeaconCrawler
Allow: /public/
Disallow: /admin/
"""
        doc = RobotsDocument.parse_text(robots_text)

        # RoomBeaconCrawler product token matches specific group
        dec_pub, matched_ua, _, _ = doc.evaluate("/public/rooms", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec_pub, "ALLOWED")
        self.assertEqual(matched_ua, "RoomBeaconCrawler")

        dec_adm, matched_ua, _, _ = doc.evaluate("/admin/users", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec_adm, "DENIED")
        self.assertEqual(matched_ua, "RoomBeaconCrawler")

        # Other crawler falls back to wildcard *
        dec_other, matched_ua, _, _ = doc.evaluate("/public/rooms", "OtherBot/1.0")
        self.assertEqual(dec_other, "DENIED")
        self.assertEqual(matched_ua, "*")

    def test_longest_match_rfc9309(self) -> None:
        """Quy tắc Longest Match: Chỉ thị có pattern dài hơn sẽ thắng khi cả hai đều khớp."""
        robots_text = """
User-agent: *
Disallow: /rentals/
Allow: /rentals/special-deal
"""
        doc = RobotsDocument.parse_text(robots_text)

        # /rentals/normal matches Disallow: /rentals/ (length 9)
        dec_normal, _, matched_rule, _ = doc.evaluate("/rentals/normal", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec_normal, "DENIED")
        self.assertEqual(matched_rule, "Disallow: /rentals/")

        # /rentals/special-deal matches both, but Allow is length 22 > 9 -> Wins!
        dec_deal, _, matched_rule, _ = doc.evaluate("/rentals/special-deal", "RoomBeaconCrawler/0.1")
        self.assertEqual(dec_deal, "ALLOWED")
        self.assertEqual(matched_rule, "Allow: /rentals/special-deal")

    def test_source_qualifier_and_robots_policy_agreement(self) -> None:
        """Kiểm tra sự đồng thuận hoàn toàn giữa SourceQualifier và RobotsPolicy."""
        nhatot_robots_text = """
User-agent: *
Allow: /
Disallow: /*page=
"""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.headers = {"Content-Type": "text/plain"}
            mock_resp.read.return_value = nhatot_robots_text.encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            qualifier = SourceQualifier()

            # Base URL
            res_base = qualifier.qualify("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh")
            self.assertEqual(res_base.robots_status, RobotsQualificationStatus.ALLOWED)
            self.assertEqual(res_base.overall_status, QualificationOverallStatus.READY)

            # Page 2 URL
            res_page = qualifier.qualify("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2")
            self.assertEqual(res_page.robots_status, RobotsQualificationStatus.DENIED)
            self.assertEqual(res_page.overall_status, QualificationOverallStatus.DENIED_BY_ROBOTS)


if __name__ == "__main__":
    unittest.main()
