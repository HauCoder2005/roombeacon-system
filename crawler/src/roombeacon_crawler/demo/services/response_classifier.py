from http import HTTPStatus

from roombeacon_crawler.demo.enums.crawl_status import CrawlStatus


class ResponseClassifier:
    def classify(
        self,
        status_code: int,
        html: str,
    ) -> CrawlStatus:
        if self._is_cloudflare_challenge(status_code=status_code, html=html):
            return CrawlStatus.CLOUDFLARE_CHALLENGE

        if 200 <= status_code < 300:
            return CrawlStatus.SUCCESS

        if status_code == HTTPStatus.BAD_REQUEST:
            return CrawlStatus.BAD_REQUEST

        if status_code == HTTPStatus.UNAUTHORIZED:
            return CrawlStatus.UNAUTHORIZED

        if status_code == HTTPStatus.FORBIDDEN:
            return CrawlStatus.ACCESS_DENIED

        if status_code == HTTPStatus.NOT_FOUND:
            return CrawlStatus.NOT_FOUND

        if status_code == HTTPStatus.TOO_MANY_REQUESTS:
            return CrawlStatus.RATE_LIMITED

        if 500 <= status_code < 600:
            return CrawlStatus.SERVER_ERROR

        return CrawlStatus.UNKNOWN

    @staticmethod
    def _is_cloudflare_challenge(
        status_code: int,
        html: str,
    ) -> bool:
        if status_code != HTTPStatus.FORBIDDEN:
            return False

        content = html.lower() if html else ""
        indicators = (
            "just a moment",
            "challenges.cloudflare.com",
            "cf-chl-",
        )

        return any(indicator in content for indicator in indicators)