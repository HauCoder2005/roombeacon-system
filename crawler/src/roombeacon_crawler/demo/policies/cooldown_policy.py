from roombeacon_crawler.demo.enums.crawl_status import CrawlStatus


class CooldownPolicy:
    def get_cooldown_seconds(
        self,
        status: CrawlStatus,
        attempt: int = 1,
    ) -> int:
        if status == CrawlStatus.RATE_LIMITED:
            if attempt <= 1:
                return 60
            if attempt == 2:
                return 300
            if attempt == 3:
                return 900
            return 1800

        if status == CrawlStatus.SERVER_ERROR:
            safe_attempt = max(1, attempt)
            return min(30 * safe_attempt, 120)

        if status in (
            CrawlStatus.CLOUDFLARE_CHALLENGE,
            CrawlStatus.ACCESS_DENIED,
        ):
            return 0

        return 0
