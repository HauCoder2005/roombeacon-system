"""Qualify target safety, source health, adapter support, and robots access.

This module is Airflow-free and composes runtime adapters at the use-case boundary.
"""

from datetime import datetime, timezone
import logging
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.repositories.local_source_health_repository import (
    LocalSourceHealthRepository,
)
from roombeacon_crawler.sources.registry import source_registry
from roombeacon_crawler.validators.url_validator import URLValidator

logger = logging.getLogger(__name__)


def qualify_target(plan: dict, **context) -> dict:
    """Thẩm định URL an toàn và kiểm tra RobotsPolicy theo từng CrawlPlan."""
    source = plan.get("source", "unknown")
    target_id = plan.get("target_id", "default")
    url = plan.get("target_url", "")
    now = datetime.now(timezone.utc)

    logger.info("=" * 60)
    logger.info("STAGE 3: QUALIFY TARGET")
    logger.info("Source: %s | Target ID: %s", source, target_id)
    logger.info("URL   : %s", url)
    logger.info("Mode  : %s | Reason: %s", plan.get("mode"), plan.get("reason"))

    adapter_cls = source_registry.resolve_adapter_class_for_url(url)
    access_profile = (
        adapter_cls.CAPABILITIES.access_profile.value
        if (adapter_cls and hasattr(adapter_cls, "CAPABILITIES"))
        else "STANDARD_PAGINATION"
    )
    logger.info("Access Profile : %s", access_profile)
    logger.info("=" * 60)

    # Source Health Gate: Kiểm tra Cooldown trước khi gửi bất kỳ request mạng nào
    health_repo = LocalSourceHealthRepository()
    health_state = health_repo.get_health(source, target_id)
    if health_state and health_state.is_in_cooldown(now):
        logger.info("=" * 60)
        logger.info("SOURCE HEALTH GATE")
        logger.info("Source               : %s", source)
        logger.info("Target               : %s", target_id)
        logger.info("Last outcome         : %s", health_state.last_outcome.value)
        logger.info("Consecutive failures : %d", health_state.consecutive_failures)
        logger.info("Cooldown until       : %s", health_state.cooldown_until)
        logger.info("Decision             : DEFER")
        logger.info("Reason               : COOLDOWN_ACTIVE")
        logger.info("=" * 60)
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "access_profile": access_profile,
            "qualification_status": "COOLDOWN_ACTIVE",
            "robots_status": "SKIPPED",
            "action": "DEFERRED",
            "reason": f"Target in cooldown until {health_state.cooldown_until}",
            "is_cooldown": True,
        }

    # URL Safety & SSRF Check
    is_valid, error_reason = URLValidator.validate(url)
    if not is_valid:
        logger.error("URL KHÔNG HỢP LỆ HOẶC BỊ TỪ CHỐI BẢO MẬT: %s", error_reason)
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "access_profile": access_profile,
            "qualification_status": "INVALID_URL",
            "robots_status": "SKIPPED",
            "action": "SKIPPED",
            "reason": f"Invalid URL: {error_reason}",
        }

    # Robots.txt Preflight Check
    robots_policy = RobotsPolicy()
    eval_res = robots_policy.evaluate(url)
    if isinstance(eval_res, tuple) and not hasattr(eval_res, "decision"):
        decision = eval_res[0]
        robots_url = eval_res[1] if len(eval_res) > 1 else ""
        http_status = None
        matched_rule = "None"
    else:
        decision = getattr(eval_res, "decision", "ALLOWED")
        robots_url = getattr(eval_res, "robots_url", "")
        http_status = getattr(eval_res, "http_status", None)
        matched_rule = getattr(eval_res, "matched_rule", "None")

    if decision == "DENIED":
        logger.warning("CRAWL SKIP: Robots policy từ chối URL: %s (%s)", url, matched_rule)
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "access_profile": access_profile,
            "qualification_status": "DENIED_BY_ROBOTS",
            "robots_status": "DENIED",
            "action": "SKIPPED",
            "failure_reason": "ROBOTS_DENIED",
            "reason": f"Robots.txt Disallow rule matched: {matched_rule}",
        }

    if decision in ("UNREACHABLE", "ERROR"):
        domain = ""
        try:
            from urllib.parse import urlparse
            domain = (urlparse(url).hostname or "").lower()
        except Exception:
            pass
        err_details = robots_policy.get_error_details(domain) if domain and hasattr(robots_policy, "get_error_details") else None
        if err_details:
            failure_reason = err_details.get("failure_type") or ("ROBOTS_UNREACHABLE" if decision == "UNREACHABLE" else "ROBOTS_FETCH_ERROR")
            http_status = err_details.get("status_code", http_status)
        else:
            failure_reason = "ROBOTS_UNREACHABLE" if decision == "UNREACHABLE" else "ROBOTS_FETCH_ERROR"

        logger.warning(
            "Robots check trả về lỗi (%s, HTTP %s) cho %s",
            failure_reason,
            http_status,
            url,
        )
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "access_profile": access_profile,
            "qualification_status": "CHECK_FAILED",
            "failure_reason": failure_reason,
            "http_status": http_status,
            "robots_status": "UNREACHABLE" if decision == "UNREACHABLE" else "ERROR",
            "action": "SKIPPED",
            "reason": f"Robots check failed: {failure_reason} (HTTP {http_status})",
        }

    if decision == "UNAVAILABLE":
        # RFC 9309 Section 2.3.1.2: Client Error (4xx) trên robots.txt -> không có luật cấm (Explicit Denial: NO)
        # Tiếp tục chuyển tiếp sang bước cào nội dung
        logger.info(
            "Robots endpoint UNAVAILABLE (HTTP %s) cho %s. RFC 9309: Coi như không có hạn chế robots.",
            http_status or 404,
            url,
        )
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "access_profile": access_profile,
            "qualification_status": "READY",
            "robots_status": "UNAVAILABLE",
            "action": "QUALIFIED",
            "reason": f"robots.txt UNAVAILABLE (HTTP {http_status or 404}) - RFC 9309 no restrictions assumed",
        }

    return {
        "plan": plan,
        "source": source,
        "target_id": target_id,
        "target_url": url,
        "access_profile": access_profile,
        "qualification_status": "READY",
        "robots_status": "ALLOWED",
        "action": "QUALIFIED",
        "reason": "Target qualified and ready to crawl",
    }
