from datetime import datetime, timezone

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget


class MetadataCollector:
    """Thu thập và cấu trúc hóa technical metadata của request phục vụ audit và tracing."""

    @staticmethod
    def collect(
        target: CrawlTarget,
        response: CapturedResponse | None,
        run_id: str,
        crawl_status: CrawlStatus,
        started_at: str,
        finished_at: str | None = None,
        retry_count: int = 0,
        robots_allowed: bool = True,
    ) -> CrawlMetadata:
        """Đóng gói technical metadata thành đối tượng CrawlMetadata hoàn chỉnh."""
        if finished_at is None:
            finished_at = datetime.now(timezone.utc).isoformat()

        headers = response.headers if response else {}
        server = headers.get("server") or headers.get("Server")
        content_type = headers.get("content-type") or headers.get("Content-Type")
        cf_ray = headers.get("cf-ray") or headers.get("CF-RAY")

        return CrawlMetadata(
            run_id=run_id,
            source=target.source,
            target_type=target.target_type,
            request_url=target.url,
            final_url=response.final_url if response else target.url,
            page_number=target.page_number,
            fetch_strategy=response.fetch_strategy if response else target.target_type,  # type: ignore[arg-type]
            http_status=response.status_code if response else 0,
            content_type=content_type,
            server=server,
            cf_ray=cf_ray,
            html_size=len(response.html) if response else 0,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=response.elapsed_ms if response else 0.0,
            retry_count=retry_count,
            robots_allowed=robots_allowed,
            crawl_status=crawl_status,
        )
