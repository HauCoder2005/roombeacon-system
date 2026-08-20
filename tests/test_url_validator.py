import unittest

from roombeacon_crawler.validators.url_validator import URLValidator


class TestGenericURLValidator(unittest.TestCase):
    def test_accepts_arbitrary_safe_urls(self) -> None:
        safe_urls = [
            "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            "https://phongtro123.com/tinh-thanh/ho-chi-minh",
            "https://example.com/rentals/123",
            "http://vietnam-property.vn/posts?category=room",
            "https://subdomain.another-site.org/index.html",
        ]
        for url in safe_urls:
            is_valid, err = URLValidator.validate(url)
            self.assertTrue(is_valid, f"Expected safe for {url}, got error: {err}")
            self.assertIsNone(err)

    def test_rejects_invalid_schemes(self) -> None:
        invalid_schemes = [
            "file:///etc/passwd",
            "ftp://files.example.com/archive.zip",
            "javascript:alert(1)",
            "data:text/html,<h1>Hello</h1>",
            "gopher://gopher.example.com/",
        ]
        for url in invalid_schemes:
            is_valid, err = URLValidator.validate(url)
            self.assertFalse(is_valid, f"Expected invalid for {url}")
            self.assertIsNotNone(err)
            self.assertIn("Protocol", err)

    def test_ssrf_blocked_hostnames_and_ips(self) -> None:
        blocked_urls = [
            "http://localhost/admin",
            "http://127.0.0.1:8080/test",
            "http://0.0.0.0/",
            "http://192.168.1.1/router",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/private",
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
        ]
        for url in blocked_urls:
            is_valid, err = URLValidator.validate(url)
            self.assertFalse(is_valid, f"Expected SSRF blocked for {url}")
            self.assertIsNotNone(err)

    def test_empty_or_none_url(self) -> None:
        is_valid, err = URLValidator.validate("")
        self.assertFalse(is_valid)
        self.assertIn("trống", err)

        is_valid, err = URLValidator.validate("   ")
        self.assertFalse(is_valid)
        self.assertIn("trống", err)

        is_valid, err = URLValidator.validate(None)
        self.assertFalse(is_valid)
        self.assertIn("trống", err)


if __name__ == "__main__":
    unittest.main()
