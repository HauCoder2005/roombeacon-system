"""Execute a qualified crawl plan through the application runner boundary.

This module is Airflow-free and composes runtime adapters at the use-case boundary.
"""

import logging
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner

logger = logging.getLogger(__name__)


from roombeacon_crawler.application.orchestration.errors import CrawlerWorkflowError


def execute_crawl(qual_payload: dict, **context) -> dict:
    """Thực thi cào dữ liệu cho từng plan đã qua bước thẩm định."""
    plan_dict = qual_payload.get("plan", {})
    source = qual_payload.get("source", "unknown")
    target_id = qual_payload.get("target_id", "default")
    url = qual_payload.get("target_url", "")
    qual_status = qual_payload.get("qualification_status", "UNKNOWN")

    # Trường hợp target bị DEFER bởi Health Gate
    if qual_payload.get("action") == "DEFERRED" or qual_status == "COOLDOWN_ACTIVE":
        logger.info("Bỏ qua thực thi crawl cho %s/%s do COOLDOWN_ACTIVE", source, target_id)
        return {
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "crawl_run_id": None,
            "crawl_status": "cooldown_active",
            "stop_reason": "cooldown_active",
            "records_created": 0,
            "pages_attempted": 0,
            "pages_success": 0,
            "pages_failed": 0,
            "details_success": 0,
            "details_failed": 0,
            "manifest_path": None,
            "bronze_path": None,
            "technical_failure": False,
            "failure_reason": qual_payload.get("reason"),
            "action": "DEFERRED",
            "plan": plan_dict,
            "observed_listing_ids": [],
            "new_listing_ids": [],
            "is_cooldown": True,
        }

    # Nếu target bị skip ở bước qualification -> Chuyển tiếp payload an toàn
    if qual_payload.get("action") == "SKIPPED" or qual_status != "READY":
        logger.info("Bỏ qua thực thi crawl cho %s/%s do trạng thái: %s", source, target_id, qual_status)
        return {
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "crawl_run_id": None,
            "crawl_status": qual_status.lower(),
            "stop_reason": qual_status.lower(),
            "records_created": 0,
            "pages_attempted": 0,
            "pages_success": 0,
            "pages_failed": 0,
            "details_success": 0,
            "details_failed": 0,
            "manifest_path": None,
            "bronze_path": None,
            "technical_failure": False,
            "failure_reason": qual_payload.get("failure_reason") or qual_payload.get("reason"),
            "http_status": qual_payload.get("http_status"),
            "action": "SKIPPED",
            "plan": plan_dict,
            "observed_listing_ids": [],
            "new_listing_ids": [],
        }

    logger.info("=" * 60)
    logger.info("STAGE 4: EXECUTE CRAWL")
    logger.info("Source: %s | Target ID: %s | URL: %s", source, target_id, url)
    logger.info("Mode  : %s", plan_dict.get("mode"))
    logger.info("=" * 60)

    try:
        records, result = CrawlRunner.execute_crawl(plan=plan_dict)
    except Exception as exc:
        logger.error(
            "Crawler technical failure (source=%s, target=%s, error_class=%s)",
            source,
            target_id,
            type(exc).__name__,
        )
        raise CrawlerWorkflowError(
            f"CrawlRunner technical failure for {source}/{target_id}"
        ) from None

    if result.status in (
        CrawlStatus.NOT_FOUND,
        CrawlStatus.CONNECTION_ERROR,
        CrawlStatus.SERVER_ERROR,
        CrawlStatus.TIMEOUT,
        CrawlStatus.PARSE_ERROR,
    ):
        logger.error(
            "Crawler returned technical failure (source=%s, target=%s, status=%s)",
            source,
            target_id,
            result.status.value,
        )
        raise CrawlerWorkflowError(
            f"Crawl run failed for {source}/{target_id} (status={result.status.value})"
        )

    is_challenge = result.status in (
        CrawlStatus.CLOUDFLARE_CHALLENGE,
        CrawlStatus.ACCESS_DENIED,
    )

    action = "ACCESS_CHALLENGE" if is_challenge else "CRAWLED"
    stop_reason_val = result.stop_reason.value if hasattr(result.stop_reason, "value") else (str(result.stop_reason) if result.stop_reason else None)

    return {
        "source": source,
        "target_id": target_id,
        "target_url": url,
        "run_id": result.run_id,
        "crawl_run_id": result.run_id,
        "crawl_status": result.status.value,
        "stop_reason": stop_reason_val,
        "records_created": result.records_created,
        "records_seen": getattr(result, "records_seen", 0),
        "records_new": getattr(result, "records_new", 0),
        "records_known": getattr(result, "records_known", 0),
        "pages_attempted": getattr(result, "pages_attempted", 0),
        "pages_success": result.pages_success,
        "pages_failed": result.pages_failed,
        "details_success": result.details_success,
        "details_failed": result.details_failed,
        "manifest_path": result.manifest_path,
        "bronze_path": result.bronze_path,
        "technical_failure": False,
        "failure_reason": result.failure_reason,
        "action": action,
        "plan": plan_dict,
        "observed_listing_ids": getattr(result, "observed_listing_ids", []),
        "new_listing_ids": getattr(result, "new_listing_ids", []),
        "seen_metadata_updates": getattr(result, "seen_metadata_updates", {}),
        "source_end_confirmed": getattr(result, "source_end_confirmed", False),
        "observations_written": getattr(result, "observations_written", len(getattr(result, "observed_listing_ids", []))),
        "records_changed": getattr(result, "records_changed", 0),
        "detail_requests_skipped": getattr(result, "detail_requests_skipped", 0),
        "detail_requests_forced_by_change": getattr(result, "detail_requests_forced_by_change", 0),
        "detail_required": getattr(result, "detail_required", 0),
        "detail_requested": getattr(result, "detail_requested", 0),
        "detail_succeeded": getattr(result, "detail_succeeded", 0),
        "detail_failed": getattr(result, "detail_failed", 0),
        "detail_skipped": getattr(result, "detail_skipped", 0),
        "skipped_known_unchanged_ttl": getattr(result, "skipped_known_unchanged_ttl", 0),
        "skipped_no_detail_url": getattr(result, "skipped_no_detail_url", 0),
        "skipped_request_budget": getattr(result, "skipped_request_budget", 0),
        "skipped_deferred_for_discovery": getattr(
            result, "skipped_deferred_for_discovery", 0
        ),
        "skipped_source_policy": getattr(result, "skipped_source_policy", 0),
        "skipped_other": getattr(result, "skipped_other", 0),
        "deferred_backlog_before": getattr(result, "deferred_backlog_before", 0),
        "deferred_added": getattr(result, "deferred_added", 0),
        "deferred_attempted": getattr(result, "deferred_attempted", 0),
        "deferred_succeeded": getattr(result, "deferred_succeeded", 0),
        "deferred_failed": getattr(result, "deferred_failed", 0),
        "deferred_terminal": getattr(result, "deferred_terminal", 0),
        "deferred_remaining": getattr(result, "deferred_remaining", 0),
        "detail_coverage": getattr(result, "detail_coverage", 0.0),
        "full_address_present": getattr(result, "full_address_present", 0),
        "full_address_missing": getattr(result, "full_address_missing", 0),
        "coarse_only_address": getattr(result, "coarse_only_address", 0),
        "detail_address_extracted": getattr(result, "detail_address_extracted", 0),
        "detail_address_parse_failed": getattr(result, "detail_address_parse_failed", 0),
        "lightweight_only_listings": getattr(result, "lightweight_only_listings", 0),
        "unique_yield": getattr(result, "unique_yield", 0.0),
        "change_rate": getattr(result, "change_rate", 0.0),
        "bootstrap_completed": getattr(result, "bootstrap_completed", False),
        "bootstrap_start_page": getattr(result, "bootstrap_start_page", 1),
        "bootstrap_next_page": getattr(result, "bootstrap_next_page", None),
        "page_acquisition_seconds": result.page_acquisition_seconds,
        "listing_parse_seconds": result.listing_parse_seconds,
        "card_processing_seconds": result.card_processing_seconds,
        "detail_fetch_seconds": result.detail_fetch_seconds,
        "deferred_detail_seconds": result.deferred_detail_seconds,
        "frontier_seconds": result.frontier_seconds,
        "discovery_seconds": result.discovery_seconds,
        "bronze_serialization_seconds": result.bronze_serialization_seconds,
        "total_crawl_seconds": result.total_crawl_seconds,
        "http_client_count": result.http_client_count,
        "browser_launch_count": result.browser_launch_count,
        "browser_context_count": result.browser_context_count,
        "browser_page_count": result.browser_page_count,
    }
