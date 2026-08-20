from datetime import datetime, timezone
import logging
from urllib.parse import urlparse

from roombeacon_crawler.models.source_qualification_result import (
    AdapterStatus,
    QualificationOverallStatus,
    RobotsQualificationStatus,
    SourceQualificationResult,
    UrlSafetyStatus,
)
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.sources.registry import SourceRegistry, source_registry
from roombeacon_crawler.validators.url_validator import URLValidator

logger = logging.getLogger(__name__)


class SourceQualifier:
    """Service thẩm định độc lập một URL nguồn ứng viên trước khi phát triển Adapter."""

    def __init__(
        self,
        robots_policy: RobotsPolicy | None = None,
        registry: SourceRegistry | None = None,
    ) -> None:
        self.robots_policy = robots_policy or RobotsPolicy()
        self.registry = registry or source_registry

    def qualify(
        self,
        url: str,
        user_agent: str | None = None,
    ) -> SourceQualificationResult:
        """Đánh giá toàn diện một URL ứng viên.

        Quy trình:
        1. Parse hostname và robots URL.
        2. Kiểm tra URLValidator (cú pháp, scheme, SSRF). Nếu không an toàn -> dừng ngay, không gửi request.
        3. Kiểm tra RobotsPolicy (preflight /robots.txt).
        4. Kiểm tra SourceRegistry xem đã có Adapter nào đăng ký cho domain này chưa.
        5. Tổng hợp thành SourceQualificationResult.
        """
        clean_url = (url or "").strip()
        checked_at = datetime.now(timezone.utc).isoformat()

        try:
            parsed = urlparse(clean_url)
            hostname = (parsed.hostname or "").lower()
            scheme = parsed.scheme or "https"
            robots_url = f"{scheme}://{parsed.netloc}/robots.txt" if parsed.netloc else ""
        except Exception:
            hostname = ""
            robots_url = ""

        # 1. URL Safety & Syntax Validation (Chặn SSRF, localhost, private IP)
        is_valid, err_msg = URLValidator.validate(clean_url)
        if not is_valid:
            return SourceQualificationResult(
                target_url=clean_url,
                hostname=hostname,
                robots_url=robots_url,
                url_status=UrlSafetyStatus.INVALID,
                robots_status=RobotsQualificationStatus.SKIPPED,
                adapter_status=AdapterStatus.NOT_REGISTERED,
                overall_status=QualificationOverallStatus.INVALID_URL,
                source_name=None,
                reason=err_msg,
                checked_at=checked_at,
            )

        # 2. Robots Preflight Evaluation
        if user_agent:
            eval_policy = RobotsPolicy(user_agent=user_agent)
        else:
            eval_policy = self.robots_policy

        decision, computed_robots_url = eval_policy.evaluate(clean_url)
        robots_url = computed_robots_url or robots_url

        if decision == "DENIED":
            robots_status = RobotsQualificationStatus.DENIED
        elif decision == "ALLOWED":
            robots_status = RobotsQualificationStatus.ALLOWED
        elif decision == "ERROR":
            robots_status = RobotsQualificationStatus.ERROR
        else:
            robots_status = RobotsQualificationStatus.UNAVAILABLE

        # 3. SourceRegistry Lookup
        is_registered = self.registry.is_supported(clean_url)
        source_name = self.registry.resolve_source_name(clean_url) if is_registered else None
        adapter_status = AdapterStatus.REGISTERED if is_registered else AdapterStatus.NOT_REGISTERED

        # 4. Overall Qualification Decision
        if robots_status == RobotsQualificationStatus.ERROR:
            overall_status = QualificationOverallStatus.CHECK_FAILED
            reason = "Không thể kiểm tra robots.txt do lỗi kết nối mạng"
        elif robots_status == RobotsQualificationStatus.DENIED:
            overall_status = QualificationOverallStatus.DENIED_BY_ROBOTS
            reason = "robots.txt của website từ chối User-Agent truy cập đường dẫn này"
        else:  # ALLOWED or UNAVAILABLE
            if adapter_status == AdapterStatus.REGISTERED:
                overall_status = QualificationOverallStatus.READY
                reason = f"robots.txt cho phép và đã có Adapter '{source_name}' sẵn sàng"
            else:
                overall_status = QualificationOverallStatus.CANDIDATE_FOR_ADAPTER
                reason = "robots permits target but no adapter is registered"

        return SourceQualificationResult(
            target_url=clean_url,
            hostname=hostname,
            robots_url=robots_url,
            url_status=UrlSafetyStatus.VALID,
            robots_status=robots_status,
            adapter_status=adapter_status,
            overall_status=overall_status,
            source_name=source_name,
            reason=reason,
            checked_at=checked_at,
        )
