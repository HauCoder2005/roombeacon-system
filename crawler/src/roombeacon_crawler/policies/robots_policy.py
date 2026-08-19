import logging
from urllib.parse import urlparse
import urllib.robotparser

logger = logging.getLogger(__name__)


class RobotsPolicy:
    """Chính sách kiểm tra và tuân thủ tệp robots.txt của website nguồn."""

    def __init__(self, user_agent: str = "RoomBeaconCrawler/0.1") -> None:
        self.user_agent = user_agent
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def is_allowed(self, url: str) -> bool:
        """Kiểm tra xem User-Agent hiện tại có được phép crawl URL này không."""
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return True

        parser = self._get_or_load_parser(domain, parsed.scheme)
        if parser is None:
            return True

        try:
            allowed = parser.can_fetch(self.user_agent, url)
            if not allowed:
                logger.warning(
                    "URL %s bị cấm bởi robots.txt của domain %s", url, domain
                )
            return allowed
        except Exception as exc:
            logger.debug("Lỗi khi kiểm tra robots.txt cho %s: %s", url, exc)
            return True

    def _get_or_load_parser(
        self, domain: str, scheme: str
    ) -> urllib.robotparser.RobotFileParser | None:
        """Lấy parser từ cache hoặc đọc từ domain."""
        if domain in self._parsers:
            return self._parsers[domain]

        robots_url = f"{scheme or 'https'}://{domain}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)

        try:
            rp.read()
            self._parsers[domain] = rp
            logger.info("Đã nạp thành công robots.txt từ %s", robots_url)
            return rp
        except Exception as exc:
            logger.info(
                "Không thể nạp robots.txt từ %s (%s). Cho phép tiếp tục an toàn.",
                robots_url,
                exc,
            )
            self._parsers[domain] = None
            return None
