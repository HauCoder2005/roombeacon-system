"""Update crawl checkpoints and source health after durable persistence.

This module is deliberately Airflow-free. Runtime adapters are composed inside the
relevant use-case boundary until Phase 3 introduces explicit composition roots.
"""

from datetime import datetime, timedelta, timezone
import logging
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.models.source_health_state import SourceHealthOutcome
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.repositories.local_source_health_repository import (
    LocalSourceHealthRepository,
)
from roombeacon_crawler.sources.registry import source_registry

logger = logging.getLogger(__name__)


def update_checkpoint(persist_payload: dict = None, result_payload: dict = None, **context) -> dict:
    """6. Cập nhật Checkpoint State, Health State sau khi đã cào và persist an toàn."""
    payload = persist_payload or result_payload or {}
    result_payload = payload.get("crawl_result") or payload
    source = payload.get("source") or result_payload.get("source", "unknown")
    target_id = payload.get("target_id") or result_payload.get("target_id", "default")
    crawl_status = result_payload.get("crawl_status", "unknown")
    plan_dict = result_payload.get("plan", {})
    action = result_payload.get("action", "UNKNOWN")
    persist_status = payload.get("status", "UNKNOWN")

    logger.info("=" * 60)
    logger.info("STAGE 6: UPDATE CHECKPOINT")
    logger.info("Source: %s | Target ID: %s | Status: %s | Action: %s | Persist: %s", source, target_id, crawl_status, action, persist_status)
    logger.info("=" * 60)

    repo = LocalCrawlStateRepository()
    health_repo = LocalSourceHealthRepository()
    state = repo.get_state(source, target_id) or CrawlTargetState(source=source, target_id=target_id)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    seed_interval = int(plan_dict.get("interval_minutes", 60) or 60)

    # 1. Trường hợp DEFERRED do Cooldown Active: Không thay đổi state hay health
    if action == "DEFERRED" or crawl_status == "cooldown_active":
        logger.info("Target %s/%s đang trong cooldown -> Giữ nguyên state.", source, target_id)
        return {
            "source": source,
            "target_id": target_id,
            "target_state_persisted": False,
            "success_checkpoint_advanced": False,
            "health_state_updated": False,
            "deferred_cooldown": True,
            "last_success_at": state.last_success_at,
            "next_run_at": state.next_run_at,
        }

    # 2. Trường hợp crawl thành công (hoặc hoàn thành phân trang hợp lệ)
    if crawl_status == CrawlStatus.SUCCESS.value:
        state.last_started_at = result_payload.get("started_at") or now_iso
        state.last_finished_at = now_iso
        state.last_success_at = now_iso
        state.last_watermark_at = now_iso
        state.last_status = crawl_status
        state.last_stop_reason = result_payload.get("stop_reason") or result_payload.get("failure_reason") or "SUCCESS"
        state.last_records_created = result_payload.get("records_created", 0)
        state.consecutive_failures = 0
        state.next_run_at = (now + timedelta(minutes=seed_interval)).isoformat()

        # Quản lý vòng đời Bootstrap / Forward-Only Acquisition
        plan_mode = plan_dict.get("mode")
        stop_reason_str = str(state.last_stop_reason).upper()

        adapter_cls = source_registry.get(source) if source_registry else None
        caps = getattr(adapter_cls, "CAPABILITIES", None) if adapter_cls else None
        is_forward_only_source = caps is not None and (
            not getattr(caps, "historical_backfill_supported", True)
            or not getattr(caps, "supports_pagination", True)
        )

        if is_forward_only_source or plan_mode in (
            CrawlMode.FORWARD_ONLY_INCREMENTAL.value,
            "FORWARD_ONLY_INCREMENTAL",
        ):
            state.bootstrap_completed = False
            state.bootstrap_completed_at = None
            state.bootstrap_next_page = None
            state.last_full_crawl_at = None
        elif stop_reason_str == "SOURCE_END":
            state.bootstrap_completed = True
            state.bootstrap_completed_at = now_iso
            state.bootstrap_next_page = None
            state.last_full_crawl_at = now_iso
        elif plan_mode in (
            CrawlMode.BOOTSTRAP_FULL.value,
            CrawlMode.BOOTSTRAP_CONTINUE.value,
            CrawlMode.FORCE_FULL.value,
            "BOOTSTRAP_FULL",
            "BOOTSTRAP_CONTINUE",
            "FORCE_FULL",
        ):
            b_next = result_payload.get("bootstrap_next_page")
            b_comp = result_payload.get("bootstrap_completed", False)
            state.bootstrap_completed = b_comp
            state.bootstrap_next_page = b_next
        elif plan_mode in (
            CrawlMode.INCREMENTAL.value,
            CrawlMode.FORCE_INCREMENTAL.value,
            "INCREMENTAL",
            "FORCE_INCREMENTAL",
        ):
            state.bootstrap_completed = True
            state.bootstrap_next_page = None

        # Lưu danh sách listing_ids đã thấy
        observed_ids = result_payload.get("observed_listing_ids", [])
        if observed_ids:
            repo.record_seen_listing_ids(source, target_id, observed_ids)

        repo.save_state(state)
        # Thành công: Reset Health State về HEALTHY
        health_repo.record_success(source, target_id, current_time=now)

        logger.info(
            "Đã cập nhật thành công checkpoint state cho %s/%s (bootstrap_completed=%s, next_page=%s)",
            source,
            target_id,
            state.bootstrap_completed,
            state.bootstrap_next_page,
        )
        return {
            "source": source,
            "target_id": target_id,
            "checkpoint_updated": True,
            "target_state_persisted": True,
            "success_checkpoint_advanced": True,
            "health_state_updated": True,
            "deferred_cooldown": False,
            "last_success_at": state.last_success_at,
            "next_run_at": state.next_run_at,
            "bootstrap_completed": state.bootstrap_completed,
            "bootstrap_next_page": state.bootstrap_next_page,
        }

    # 3. Trường hợp rào cản truy cập (Access Challenge), Robots Denied hoặc Robots Error
    if crawl_status in (
        CrawlStatus.CLOUDFLARE_CHALLENGE.value,
        CrawlStatus.ACCESS_DENIED.value,
        "denied_by_robots",
        "robots_denied",
        "invalid_url",
        "check_failed",
        "skipped",
    ) or action in ("ACCESS_CHALLENGE", "ROBOTS_DENIED", "SKIPPED"):
        state.last_finished_at = now_iso
        state.last_status = crawl_status
        state.last_stop_reason = result_payload.get("stop_reason") or result_payload.get("failure_reason") or "CONTROLLED_STOP"
        state.next_run_at = (now + timedelta(minutes=seed_interval)).isoformat()

        repo.save_state(state)

        # Phân loại SourceHealthOutcome tương ứng
        if action == "ACCESS_CHALLENGE" or crawl_status in (
            CrawlStatus.CLOUDFLARE_CHALLENGE.value,
            CrawlStatus.ACCESS_DENIED.value,
        ):
            outcome = SourceHealthOutcome.ACCESS_CHALLENGE
            http_status = 403
            reason = result_payload.get("failure_reason") or "Cloudflare challenge / Access Denied"
        elif result_payload.get("failure_reason") == "ROBOTS_FETCH_ERROR" or crawl_status == "check_failed":
            outcome = SourceHealthOutcome.ROBOTS_FETCH_ERROR
            http_status = result_payload.get("http_status") or 403
            reason = result_payload.get("failure_reason") or "Robots fetch error"
        elif crawl_status in ("denied_by_robots", "robots_denied"):
            outcome = SourceHealthOutcome.ROBOTS_DENIED
            http_status = None
            reason = "Robots.txt Disallow rule matched"
        else:
            outcome = SourceHealthOutcome.UNKNOWN
            http_status = None
            reason = result_payload.get("failure_reason") or "Controlled skip"

        health_repo.record_failure(
            source=source,
            target_id=target_id,
            outcome=outcome,
            reason=reason,
            http_status=http_status,
            current_time=now,
        )

        logger.info("Ghi nhận trạng thái kiểm soát (%s) cho %s/%s", crawl_status, source, target_id)
        return {
            "source": source,
            "target_id": target_id,
            "checkpoint_updated": True,
            "target_state_persisted": True,
            "success_checkpoint_advanced": False,
            "health_state_updated": True,
            "deferred_cooldown": False,
            "last_success_at": state.last_success_at,
            "next_run_at": state.next_run_at,
        }

    # 4. Trường hợp sự cố kỹ thuật (Technical Failure)
    state.last_finished_at = now_iso
    state.last_status = crawl_status
    state.last_stop_reason = result_payload.get("stop_reason") or result_payload.get("failure_reason") or "TECHNICAL_FAILURE"
    state.consecutive_failures += 1

    backoff_minutes = min(seed_interval * (2 ** max(0, state.consecutive_failures - 1)), 1440)
    state.next_run_at = (now + timedelta(minutes=backoff_minutes)).isoformat()

    repo.save_state(state)
    health_repo.record_failure(
        source=source,
        target_id=target_id,
        outcome=SourceHealthOutcome.TECHNICAL_FAILURE,
        reason=result_payload.get("failure_reason") or "Technical error",
        current_time=now,
    )

    return {
        "source": source,
        "target_id": target_id,
        "checkpoint_updated": True,
        "target_state_persisted": True,
        "success_checkpoint_advanced": False,
        "health_state_updated": True,
        "deferred_cooldown": False,
        "last_success_at": state.last_success_at,
        "next_run_at": state.next_run_at,
    }


# --------------------------------------------------------------------------
# Task 7: Refresh DuckDB Analytics (Once per DAG Run)
# --------------------------------------------------------------------------
