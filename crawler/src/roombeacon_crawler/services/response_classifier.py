from roombeacon_crawler.enums.crawl_status import CrawlStatus


class ResponseClassifier:
    """Phân loại trạng thái phản hồi HTTP và nhận diện các rào cản bảo mật như Cloudflare."""

    CLOUDFLARE_INDICATORS = (
        "just a moment",
        "challenges.cloudflare.com",
        "cf-chl-",
        "attention required! | cloudflare",
    )

    def classify(self, status_code: int, html: str | None = None) -> CrawlStatus:
        """Phân loại status_code và nội dung HTML thành CrawlStatus chuẩn."""
        html_lower = html.lower() if html else ""

        if status_code == 403:
            for indicator in self.CLOUDFLARE_INDICATORS:
                if indicator in html_lower:
                    return CrawlStatus.CLOUDFLARE_CHALLENGE
            return CrawlStatus.ACCESS_DENIED

        if 200 <= status_code < 300:
            for indicator in self.CLOUDFLARE_INDICATORS:
                if indicator in html_lower:
                    return CrawlStatus.CLOUDFLARE_CHALLENGE
            return CrawlStatus.SUCCESS

        if status_code == 400:
            return CrawlStatus.BAD_REQUEST

        if status_code == 401:
            return CrawlStatus.UNAUTHORIZED

        if status_code == 404:
            return CrawlStatus.NOT_FOUND

        if status_code == 429:
            return CrawlStatus.RATE_LIMITED

        if 500 <= status_code < 600:
            return CrawlStatus.SERVER_ERROR

        return CrawlStatus.UNKNOWN
