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

        eval_res = eval_policy.evaluate(clean_url)
        if isinstance(eval_res, tuple) and not hasattr(eval_res, "decision"):
            decision = eval_res[0]
            robots_url = eval_res[1] if len(eval_res) > 1 else robots_url
            http_status = None
            matched_rule = "None"
            error_reason = None
        else:
            decision = getattr(eval_res, "decision", "ALLOWED")
            robots_url = getattr(eval_res, "robots_url", robots_url) or robots_url
            http_status = getattr(eval_res, "http_status", None)
            matched_rule = getattr(eval_res, "matched_rule", "None")
            error_reason = getattr(eval_res, "error_reason", None)

        if decision == "DENIED":
            robots_status = RobotsQualificationStatus.DENIED
        elif decision == "ALLOWED":
            robots_status = RobotsQualificationStatus.ALLOWED
        elif decision == "UNREACHABLE":
            robots_status = RobotsQualificationStatus.UNREACHABLE
        elif decision == "UNAVAILABLE":
            robots_status = RobotsQualificationStatus.UNAVAILABLE
        else:
            robots_status = RobotsQualificationStatus.ERROR

        # 3. SourceRegistry Lookup
        adapter_cls = self.registry.resolve_adapter_class_for_url(clean_url)
        is_registered = adapter_cls is not None
        source_name = adapter_cls.SOURCE_NAME if adapter_cls else None
        adapter_status = AdapterStatus.REGISTERED if is_registered else AdapterStatus.NOT_REGISTERED
        
        access_profile = None
        caps_dict = None
        if adapter_cls:
            caps = getattr(adapter_cls, "CAPABILITIES", None)
            if caps:
                access_profile = caps.access_profile.value if hasattr(caps.access_profile, "value") else str(caps.access_profile)
                caps_dict = {
                    "access_profile": access_profile,
                    "supports_pagination": caps.supports_pagination,
                    "supports_sitemap_discovery": caps.supports_sitemap_discovery,
                    "preferred_fetch_strategy": caps.preferred_fetch_strategy.value if hasattr(caps.preferred_fetch_strategy, "value") else str(caps.preferred_fetch_strategy),
                    "robots_required": caps.robots_required,
                    "detail_fetch_supported": caps.detail_fetch_supported,
                }

        # 4. Overall Qualification Decision
        failure_reason = None

        if robots_status == RobotsQualificationStatus.UNREACHABLE or robots_status == RobotsQualificationStatus.ERROR:
            overall_status = QualificationOverallStatus.CHECK_FAILED
            err_info = eval_policy.get_error_details(hostname) if hasattr(eval_policy, "get_error_details") else None
            if err_info:
                failure_reason = err_info.get("failure_type") or ("ROBOTS_UNREACHABLE" if robots_status == RobotsQualificationStatus.UNREACHABLE else "ROBOTS_FETCH_ERROR")
                http_status = err_info.get("status_code", http_status)
            else:
                failure_reason = "ROBOTS_UNREACHABLE" if robots_status == RobotsQualificationStatus.UNREACHABLE else "ROBOTS_FETCH_ERROR"
            reason = f"Robots endpoint unreachable ({failure_reason}, HTTP {http_status}): {error_reason or (err_info.get('reason') if err_info else 'Network/server failure')}"
        elif robots_status == RobotsQualificationStatus.DENIED:
            overall_status = QualificationOverallStatus.DENIED_BY_ROBOTS
            failure_reason = "ROBOTS_DENIED"
            reason = f"robots.txt cấm User-Agent truy cập ({matched_rule})"
        elif robots_status == RobotsQualificationStatus.UNAVAILABLE:
            failure_reason = None
            if adapter_status == AdapterStatus.REGISTERED:
                overall_status = QualificationOverallStatus.READY
                reason = f"robots.txt trả về HTTP {http_status or 404} (UNAVAILABLE) - RFC 9309: Coi như không có hạn chế robots, sẵn sàng cào với Adapter '{source_name}'"
            else:
                overall_status = QualificationOverallStatus.CANDIDATE_FOR_ADAPTER
                reason = f"robots.txt UNAVAILABLE (HTTP {http_status or 404}) - candidate for adapter"
        else:  # ALLOWED
            failure_reason = None
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
            access_profile=access_profile,
            capabilities=caps_dict,
            reason=reason,
            failure_reason=failure_reason,
            http_status=http_status,
            checked_at=checked_at,
        )
