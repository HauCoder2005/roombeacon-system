import io
import json
import unittest
from unittest.mock import MagicMock, patch

from roombeacon_crawler.models.source_qualification_result import (
    AdapterStatus,
    QualificationOverallStatus,
    RobotsQualificationStatus,
    SourceQualificationResult,
    UrlSafetyStatus,
)
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.source_qualifier import SourceQualifier
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.registry import SourceRegistry
from roombeacon_crawler.tools.qualify_source import main


class TestSourceQualifier(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_registry = SourceRegistry()
        self.mock_robots = MagicMock(spec=RobotsPolicy)
        self.qualifier = SourceQualifier(
            robots_policy=self.mock_robots,
            registry=self.mock_registry,
        )

    def test_case_1_valid_url_robots_allowed_registered_adapter_is_ready(self) -> None:
        """Case 1: Valid URL + robots ALLOWED + adapter registered -> READY"""
        class RegisteredAdapter(BaseSourceAdapter):
            SOURCE_NAME = "registered_site"
            DOMAINS = ("registered.com",)

        self.mock_registry.register(RegisteredAdapter)
        self.mock_robots.evaluate.return_value = ("ALLOWED", "https://registered.com/robots.txt")

        result = self.qualifier.qualify("https://registered.com/rooms/123")

        self.assertEqual(result.url_status, UrlSafetyStatus.VALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.ALLOWED)
        self.assertEqual(result.adapter_status, AdapterStatus.REGISTERED)
        self.assertEqual(result.overall_status, QualificationOverallStatus.READY)
        self.assertEqual(result.source_name, "registered_site")
        self.mock_robots.evaluate.assert_called_once_with("https://registered.com/rooms/123")

    def test_case_2_valid_url_robots_allowed_no_adapter_is_candidate(self) -> None:
        """Case 2: Valid URL + robots ALLOWED + no adapter -> CANDIDATE_FOR_ADAPTER"""
        self.mock_robots.evaluate.return_value = ("ALLOWED", "https://new-candidate.com/robots.txt")

        result = self.qualifier.qualify("https://new-candidate.com/for-rent")

        self.assertEqual(result.url_status, UrlSafetyStatus.VALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.ALLOWED)
        self.assertEqual(result.adapter_status, AdapterStatus.NOT_REGISTERED)
        self.assertEqual(result.overall_status, QualificationOverallStatus.CANDIDATE_FOR_ADAPTER)
        self.assertIsNone(result.source_name)
        self.assertIn("robots permits target", result.reason)

    def test_case_3_valid_url_robots_denied_is_denied_by_robots(self) -> None:
        """Case 3: Valid URL + robots DENIED -> DENIED_BY_ROBOTS"""
        self.mock_robots.evaluate.return_value = ("DENIED", "https://blocked-site.com/robots.txt")

        result = self.qualifier.qualify("https://blocked-site.com/private/rentals")

        self.assertEqual(result.url_status, UrlSafetyStatus.VALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.DENIED)
        self.assertEqual(result.overall_status, QualificationOverallStatus.DENIED_BY_ROBOTS)

    def test_case_4_unsafe_localhost_is_invalid_url_no_network(self) -> None:
        """Case 4: Unsafe localhost -> INVALID_URL (no network request made)"""
        result = self.qualifier.qualify("http://localhost:8080/rentals")

        self.assertEqual(result.url_status, UrlSafetyStatus.INVALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.SKIPPED)
        self.assertEqual(result.overall_status, QualificationOverallStatus.INVALID_URL)
        self.mock_robots.evaluate.assert_not_called()

    def test_case_5_private_ip_is_invalid_url_no_network(self) -> None:
        """Case 5: Private IP -> INVALID_URL (no network request made)"""
        result = self.qualifier.qualify("http://192.168.1.1/admin/rentals")

        self.assertEqual(result.url_status, UrlSafetyStatus.INVALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.SKIPPED)
        self.assertEqual(result.overall_status, QualificationOverallStatus.INVALID_URL)
        self.mock_robots.evaluate.assert_not_called()

    def test_case_6_robots_network_failure_is_check_failed(self) -> None:
        """Case 6: Robots network failure -> CHECK_FAILED"""
        self.mock_robots.evaluate.return_value = ("ERROR", "https://unreachable-site.com/robots.txt")

        result = self.qualifier.qualify("https://unreachable-site.com/rentals")

        self.assertEqual(result.url_status, UrlSafetyStatus.VALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.ERROR)
        self.assertEqual(result.overall_status, QualificationOverallStatus.CHECK_FAILED)

    def test_case_7_human_readable_formatting(self) -> None:
        """Case 7: Format output is clean, human-readable without Python dict punctuation."""
        result = SourceQualificationResult(
            target_url="https://example.com/rentals",
            hostname="example.com",
            robots_url="https://example.com/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.ALLOWED,
            adapter_status=AdapterStatus.NOT_REGISTERED,
            overall_status=QualificationOverallStatus.CANDIDATE_FOR_ADAPTER,
            reason="robots permits target but no adapter is registered",
        )

        output = result.format_human_readable()
        self.assertIn("Source Qualification", output)
        self.assertIn("Target URL : https://example.com/rentals", output)
        self.assertIn("Hostname   : example.com", output)
        self.assertIn("Robots URL : https://example.com/robots.txt", output)
        self.assertIn("URL Safety : VALID", output)
        self.assertIn("Robots     : ALLOWED", output)
        self.assertIn("Adapter    : NOT_REGISTERED", output)
        self.assertIn("Overall    : CANDIDATE_FOR_ADAPTER", output)
        self.assertNotIn("{", output)
        self.assertNotIn("}", output)
        self.assertNotIn("': '", output)

    @patch("sys.stdout", new_callable=io.StringIO)
    @patch("roombeacon_crawler.services.source_qualifier.RobotsPolicy.evaluate")
    def test_cli_human_readable_execution(
        self, mock_robots_eval: MagicMock, mock_stdout: io.StringIO
    ) -> None:
        """Kiểm thử CLI xuất kết quả dạng text thông thường."""
        mock_robots_eval.return_value = ("ALLOWED", "https://example.com/robots.txt")

        with patch("sys.argv", ["qualify_source", "https://example.com/rentals"]):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Source Qualification", output)
        self.assertIn("Target URL : https://example.com/rentals", output)
        self.assertIn("Overall    : CANDIDATE_FOR_ADAPTER", output)

    @patch("sys.stdout", new_callable=io.StringIO)
    @patch("roombeacon_crawler.services.source_qualifier.RobotsPolicy.evaluate")
    def test_cli_json_execution(
        self, mock_robots_eval: MagicMock, mock_stdout: io.StringIO
    ) -> None:
        """Kiểm thử CLI xuất kết quả dạng JSON."""
        mock_robots_eval.return_value = ("ALLOWED", "https://example.com/robots.txt")

        with patch("sys.argv", ["qualify_source", "https://example.com/rentals", "--json"]):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        output = mock_stdout.getvalue()
        data = json.loads(output)
        self.assertEqual(data["target_url"], "https://example.com/rentals")
        self.assertEqual(data["overall_status"], "CANDIDATE_FOR_ADAPTER")
        self.assertEqual(data["robots_status"], "ALLOWED")


    def test_qualify_batdongsan_adapter_registered_robots_denied(self) -> None:
        """Kiểm tra BatDongSan URL: Adapter REGISTERED và nếu robots DENIED thì overall là DENIED_BY_ROBOTS."""
        from roombeacon_crawler.sources.registry import source_registry
        real_qualifier = SourceQualifier(
            robots_policy=self.mock_robots,
            registry=source_registry,
        )
        self.mock_robots.evaluate.return_value = ("DENIED", "https://batdongsan.com.vn/robots.txt")

        result = real_qualifier.qualify("https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm")

        self.assertEqual(result.url_status, UrlSafetyStatus.VALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.DENIED)
        self.assertEqual(result.adapter_status, AdapterStatus.REGISTERED)
        self.assertEqual(result.source_name, "batdongsan")
        self.assertEqual(result.overall_status, QualificationOverallStatus.DENIED_BY_ROBOTS)

    def test_qualify_muaban_adapter_registered_robots_allowed(self) -> None:
        """Kiểm tra Muaban URL: Adapter REGISTERED và nếu robots ALLOWED thì overall là READY."""
        from roombeacon_crawler.sources.registry import source_registry
        real_qualifier = SourceQualifier(
            robots_policy=self.mock_robots,
            registry=source_registry,
        )
        self.mock_robots.evaluate.return_value = ("ALLOWED", "https://muaban.net/robots.txt")

        result = real_qualifier.qualify("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm")

        self.assertEqual(result.url_status, UrlSafetyStatus.VALID)
        self.assertEqual(result.robots_status, RobotsQualificationStatus.ALLOWED)
        self.assertEqual(result.adapter_status, AdapterStatus.REGISTERED)
        self.assertEqual(result.source_name, "muaban")
        self.assertEqual(result.overall_status, QualificationOverallStatus.READY)


if __name__ == "__main__":
    unittest.main()

