from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import airflow
from airflow.decorators import dag, task
from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.models.param import Param
from airflow.utils.trigger_rule import TriggerRule

from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.models.source_qualification_result import (
    QualificationOverallStatus,
    RobotsQualificationStatus,
    UrlSafetyStatus,
)
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.services.crawl_planner import CrawlPlanner
from roombeacon_crawler.services.source_qualifier import SourceQualifier
from roombeacon_crawler.services.target_provider import (
    AdapterScheduledTargetProvider,
)
from roombeacon_crawler.sources.registry import source_registry
from roombeacon_crawler.sources.resolver import SourceResolver
from roombeacon_crawler.validators.url_validator import URLValidator

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Task 1: Load Crawl Targets (Discovery)
# --------------------------------------------------------------------------
@task
def load_crawl_targets() -> list[dict]:
    """1. Thu thập danh sách cấu hình tĩnh (CrawlSeed) từ tất cả các Source Adapter đã đăng ký."""
    logger.info("=" * 60)
    logger.info("STAGE 1: LOAD CRAWL TARGETS (DISCOVERY)")
    logger.info("=" * 60)

    provider = AdapterScheduledTargetProvider(registry=source_registry)
    seeds = provider.get_scheduled_targets()
    serialized = [s.to_dict() for s in seeds]

    logger.info("Đã phát hiện %d targets từ các Source Adapters.", len(serialized))
    return serialized


# --------------------------------------------------------------------------
# Task 2: Plan Crawls (Planning)
# --------------------------------------------------------------------------
@task
def plan_crawls(targets: list[dict], **context) -> list[dict]:
    """2. Lập kế hoạch cào dữ liệu tự động (CrawlPlanner) dựa trên Checkpoint State và cấu hình runtime."""
    logger.info("=" * 60)
    logger.info("STAGE 2: PLAN CRAWLS (PLANNING)")
    logger.info("=" * 60)

    params = context.get("params", {})
    execution_mode = str(params.get("execution_mode", "AUTO")).upper()
    debug_url = str(params.get("debug_target_url", "")).strip()
    debug_max_pages = int(params.get("debug_max_pages", 0) or 0)
    debug_max_records = int(params.get("debug_max_records", 0) or 0)
    debug_crawl_details = bool(params.get("debug_crawl_details", False))

    now = datetime.now(timezone.utc)
    repo = LocalCrawlStateRepository()
    planner = CrawlPlanner(state_repository=repo)

    # 1. Hỗ trợ chế độ DEBUG_SINGLE_TARGET dành cho lập trình viên
    if execution_mode == "DEBUG_SINGLE_TARGET":
        if not debug_url:
            raise AirflowException(
                "Chế độ DEBUG_SINGLE_TARGET yêu cầu nhập 'debug_target_url'."
            )
        resolved_adapter = SourceResolver.resolve(debug_url)
        source_name = resolved_adapter.SOURCE_NAME if resolved_adapter else "unknown"
        plan = CrawlPlan(
            source=source_name,
            target_id="debug_single_target",
            target_url=debug_url,
            mode=CrawlMode.FORCE_FULL,
            reason="DEBUG_SINGLE_TARGET_MANUAL_TRIGGER",
            planned_at=now.isoformat(),
            crawl_details=debug_crawl_details,
            safety_max_pages=debug_max_pages if debug_max_pages > 0 else 10,
            safety_max_records=debug_max_records if debug_max_records > 0 else 200,
        )
        logger.info("Tạo 1 CrawlPlan DEBUG cho URL: %s", debug_url)
        return [plan.to_dict()]

    # 2. Chế độ sản xuất tự động (AUTO, FORCE_FULL, FORCE_INCREMENTAL)
    seeds = [CrawlSeed.from_dict(t) for t in (targets or [])]
    override_mode = execution_mode if execution_mode in ("FORCE_FULL", "FORCE_INCREMENTAL") else None

    plans = planner.plan_all(seeds=seeds, current_time=now, override_mode=override_mode)
    serialized_plans = [p.to_dict() for p in plans]

    logger.info("Đã tạo %d plans hợp lệ sẵn sàng chuyển sang tầng qualification.", len(serialized_plans))
    return serialized_plans


# --------------------------------------------------------------------------
# Task 3: Qualify Target (Mapped per Plan)
# --------------------------------------------------------------------------
@task
def qualify_target(plan: dict, **context) -> dict:
    """3. Thẩm định URL an toàn và kiểm tra RobotsPolicy theo từng CrawlPlan."""
    source = plan.get("source", "unknown")
    target_id = plan.get("target_id", "default")
    url = plan.get("target_url", "")

    logger.info("=" * 60)
    logger.info("STAGE 3: QUALIFY TARGET")
    logger.info("Source: %s | Target ID: %s", source, target_id)
    logger.info("URL   : %s", url)
    logger.info("Mode  : %s | Reason: %s", plan.get("mode"), plan.get("reason"))
    logger.info("=" * 60)

    # 1. URL Safety & SSRF Check
    is_valid, error_reason = URLValidator.validate(url)
    if not is_valid:
        logger.error("URL KHÔNG HỢP LỆ HOẶC BỊ TỪ CHỐI BẢO MẬT: %s", error_reason)
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "qualification_status": "INVALID_URL",
            "robots_status": "SKIPPED",
            "action": "SKIPPED",
            "reason": f"Invalid URL: {error_reason}",
        }

    # 2. Robots.txt Preflight Check
    robots_policy = RobotsPolicy()
    decision, robots_url = robots_policy.evaluate(url)
    logger.info("Robots URL     : %s", robots_url)
    logger.info("Robots Decision: %s", decision)

    if decision == "DENIED":
        logger.warning("CRAWL SKIP: Robots policy từ chối URL: %s", url)
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "qualification_status": "DENIED_BY_ROBOTS",
            "robots_status": "DENIED",
            "action": "SKIPPED",
            "reason": "Robots.txt Disallow rule matched",
        }

    if decision == "ERROR":
        logger.warning("Robots check trả về lỗi mạng cho %s", url)
        return {
            "plan": plan,
            "source": source,
            "target_id": target_id,
            "target_url": url,
            "qualification_status": "CHECK_FAILED",
            "robots_status": "ERROR",
            "action": "SKIPPED",
            "reason": "Robots check network failure",
        }

    return {
        "plan": plan,
        "source": source,
        "target_id": target_id,
        "target_url": url,
        "qualification_status": "READY",
        "robots_status": "ALLOWED",
        "action": "QUALIFIED",
        "reason": "Target qualified and ready to crawl",
    }


# --------------------------------------------------------------------------
# Task 4: Execute Crawl (Mapped per Qualified Plan)
# --------------------------------------------------------------------------
@task
def execute_crawl(qual_payload: dict, **context) -> dict:
    """4. Thực thi cào dữ liệu cho từng plan đã qua bước thẩm định."""
    plan_dict = qual_payload.get("plan", {})
    source = qual_payload.get("source", "unknown")
    target_id = qual_payload.get("target_id", "default")
    url = qual_payload.get("target_url", "")
    qual_status = qual_payload.get("qualification_status", "UNKNOWN")

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
            "failure_reason": qual_payload.get("reason"),
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
        logger.exception("LỖI NGOẠI LỆ KHI THỰC THI CRAWLER CHO %s/%s: %s", source, target_id, exc)
        raise AirflowException(f"CrawlRunner technical failure for {url}: {exc}") from exc

    # Technical Failure Check
    if result.status in (
        CrawlStatus.CONNECTION_ERROR,
        CrawlStatus.SERVER_ERROR,
        CrawlStatus.TIMEOUT,
        CrawlStatus.PARSE_ERROR,
    ):
        err_msg = result.failure_reason or f"Technical error: {result.status.value}"
        logger.error("Crawl thất bại cho %s: %s", url, err_msg)
        raise AirflowException(f"Crawl run failed for {url}: {err_msg}")

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
    }


# --------------------------------------------------------------------------
# Task 5: Update Checkpoint (Mapped per Result)
# --------------------------------------------------------------------------
@task
def update_checkpoint(result_payload: dict, **context) -> dict:
    """5. Cập nhật Checkpoint State và danh sách listing đã thấy vào State Repository."""
    source = result_payload.get("source", "unknown")
    target_id = result_payload.get("target_id", "default")
    crawl_status = result_payload.get("crawl_status", "unknown")
    plan_dict = result_payload.get("plan", {})
    action = result_payload.get("action", "UNKNOWN")

    logger.info("=" * 60)
    logger.info("STAGE 5: UPDATE CHECKPOINT")
    logger.info("Source: %s | Target ID: %s | Status: %s", source, target_id, crawl_status)
    logger.info("=" * 60)

    repo = LocalCrawlStateRepository()
    state = repo.get_state(source, target_id) or CrawlTargetState(source=source, target_id=target_id)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    seed_interval = int(plan_dict.get("interval_minutes", 60) or 60)

    # 1. Trường hợp crawl thành công (hoặc kết thúc phân trang hợp lệ)
    if crawl_status == CrawlStatus.SUCCESS.value:
        state.last_started_at = result_payload.get("started_at") or now_iso
        state.last_finished_at = now_iso
        state.last_success_at = now_iso
        state.last_watermark_at = now_iso
        if plan_dict.get("mode") in (CrawlMode.BOOTSTRAP_FULL.value, CrawlMode.FORCE_FULL.value):
            state.last_full_crawl_at = now_iso

        state.last_status = crawl_status
        state.last_stop_reason = result_payload.get("stop_reason") or result_payload.get("failure_reason") or "SUCCESS"
        state.last_records_created = result_payload.get("records_created", 0)
        state.consecutive_failures = 0
        state.next_run_at = (now + timedelta(minutes=seed_interval)).isoformat()

        # Lưu danh sách listing_ids đã thấy
        observed_ids = result_payload.get("observed_listing_ids", [])
        if observed_ids:
            repo.record_seen_listing_ids(source, target_id, observed_ids)

        repo.save_state(state)
        logger.info("Đã cập nhật thành công checkpoint state cho %s/%s", source, target_id)
        return {
            "source": source,
            "target_id": target_id,
            "checkpoint_updated": True,
            "last_success_at": state.last_success_at,
            "next_run_at": state.next_run_at,
        }

    # 2. Trường hợp rào cản truy cập (Access Challenge) hoặc Robots Denied
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
        # Không reset consecutive_failures nhưng cũng không tăng backoff sự cố kỹ thuật
        state.next_run_at = (now + timedelta(minutes=seed_interval)).isoformat()

        repo.save_state(state)
        logger.info("Ghi nhận trạng thái kiểm soát (%s) cho %s/%s", crawl_status, source, target_id)
        return {
            "source": source,
            "target_id": target_id,
            "checkpoint_updated": True,
            "last_success_at": state.last_success_at,
            "next_run_at": state.next_run_at,
        }

    # 3. Trường hợp sự cố kỹ thuật (Technical Failure)
    state.last_finished_at = now_iso
    state.last_status = crawl_status
    state.last_stop_reason = result_payload.get("stop_reason") or result_payload.get("failure_reason") or "TECHNICAL_FAILURE"
    state.consecutive_failures += 1

    # Bounded backoff
    backoff_minutes = min(seed_interval * (2 ** max(0, state.consecutive_failures - 1)), 1440)
    state.next_run_at = (now + timedelta(minutes=backoff_minutes)).isoformat()

    repo.save_state(state)
    logger.warning(
        "Ghi nhận failure liên tiếp lần %d cho %s/%s. Next run sau %d phút.",
        state.consecutive_failures,
        source,
        target_id,
        backoff_minutes,
    )
    return {
        "source": source,
        "target_id": target_id,
        "checkpoint_updated": True,
        "last_success_at": state.last_success_at,
        "next_run_at": state.next_run_at,
    }


# --------------------------------------------------------------------------
# Task 6: Summarize Run (Finalization)
# --------------------------------------------------------------------------
@task(trigger_rule=TriggerRule.ALL_DONE)
def summarize_run(
    plans: list[dict],
    qualifications: list[dict],
    crawl_results: list[dict],
    checkpoints: list[dict],
    **context,
) -> dict:
    """6. Tổng hợp số liệu thống kê toàn diện của toàn bộ fleet sau phiên cào."""
    plans = plans or []
    qualifications = qualifications or []
    crawl_results = crawl_results or []
    checkpoints = checkpoints or []

    targets_due = len(plans)
    bootstrap_planned = sum(1 for p in plans if p.get("mode") in (CrawlMode.BOOTSTRAP_FULL.value, CrawlMode.FORCE_FULL.value))
    incremental_planned = sum(1 for p in plans if p.get("mode") in (CrawlMode.INCREMENTAL.value, CrawlMode.FORCE_INCREMENTAL.value))

    qualification_allowed = sum(1 for q in qualifications if q.get("qualification_status") == "READY")
    robots_denied = sum(1 for q in qualifications if q.get("qualification_status") == "DENIED_BY_ROBOTS")

    crawl_success = sum(1 for r in crawl_results if r.get("crawl_status") == CrawlStatus.SUCCESS.value)
    access_challenge = sum(
        1
        for r in crawl_results
        if r.get("crawl_status") in (CrawlStatus.CLOUDFLARE_CHALLENGE.value, CrawlStatus.ACCESS_DENIED.value)
        or r.get("action") == "ACCESS_CHALLENGE"
    )
    technical_failure = sum(
        1
        for r in crawl_results
        if r.get("crawl_status")
        in (
            CrawlStatus.CONNECTION_ERROR.value,
            CrawlStatus.SERVER_ERROR.value,
            CrawlStatus.TIMEOUT.value,
            CrawlStatus.PARSE_ERROR.value,
        )
    )

    records_created = sum(r.get("records_created", 0) for r in crawl_results)
    details_created = sum(r.get("details_success", 0) for r in crawl_results)
    checkpoints_updated = sum(1 for c in checkpoints if c.get("checkpoint_updated"))

    logger.info("=" * 60)
    logger.info("ROOMBEACON AUTOMATED CRAWL RUN SUMMARY")
    logger.info("-" * 60)
    logger.info("Targets due          : %d", targets_due)
    logger.info("Bootstrap planned    : %d", bootstrap_planned)
    logger.info("Incremental planned  : %d", incremental_planned)
    logger.info("Qualification allowed: %d", qualification_allowed)
    logger.info("Robots denied        : %d", robots_denied)
    logger.info("Crawl success        : %d", crawl_success)
    logger.info("Access challenge     : %d", access_challenge)
    logger.info("Technical failure    : %d", technical_failure)
    logger.info("Records created      : %d", records_created)
    logger.info("Details created      : %d", details_created)
    logger.info("Checkpoints updated  : %d", checkpoints_updated)
    logger.info("=" * 60)

    return {
        "targets_due": targets_due,
        "bootstrap_planned": bootstrap_planned,
        "incremental_planned": incremental_planned,
        "qualification_allowed": qualification_allowed,
        "robots_denied": robots_denied,
        "crawl_success": crawl_success,
        "access_challenge": access_challenge,
        "technical_failure": technical_failure,
        "records_created": records_created,
        "details_created": details_created,
        "checkpoints_updated": checkpoints_updated,
    }


# --------------------------------------------------------------------------
# DAG Definition: roombeacon_crawler
# --------------------------------------------------------------------------
@dag(
    dag_id="roombeacon_crawler",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["roombeacon", "crawler", "production", "automated"],
    params={
        "execution_mode": Param(
            "AUTO",
            type="string",
            enum=[
                "AUTO",
                "FORCE_FULL",
                "FORCE_INCREMENTAL",
                "DEBUG_SINGLE_TARGET",
            ],
            description=(
                "Chế độ chạy: AUTO (Tự động theo lịch & checkpoint), FORCE_FULL"
                " (Ép full crawl), FORCE_INCREMENTAL (Ép incremental),"
                " DEBUG_SINGLE_TARGET (Chạy 1 URL debug)"
            ),
        ),
        "debug_target_url": Param(
            "",
            type="string",
            description="URL debug (chỉ áp dụng khi chọn DEBUG_SINGLE_TARGET)",
        ),
        "debug_max_pages": Param(
            0,
            type="integer",
            description="Số trang tối đa debug (0 = dùng mặc định theo cấu hình nguồn)",
        ),
        "debug_max_records": Param(
            0,
            type="integer",
            description="Số tin tối đa debug (0 = dùng mặc định theo cấu hình nguồn)",
        ),
        "debug_crawl_details": Param(
            False,
            type="boolean",
            description="Debug: Có crawl chi tiết tin không",
        ),
    },
)
def roombeacon_crawler():
    """DAG chính thu thập dữ liệu bất động sản/phòng trọ đa nguồn RoomBeacon."""
    # 1. Khám phá static targets từ tất cả các Source Adapters
    targets = load_crawl_targets()

    # 2. Lập kế hoạch cào (BOOTSTRAP vs INCREMENTAL, DUE status, Overlap window)
    plans = plan_crawls(targets)

    # 3. Thẩm định URL & Robots Policy theo từng plan (Dynamic Mapping)
    qualifications = qualify_target.expand(plan=plans)

    # 4. Thực thi cào dữ liệu theo plan đã được thẩm định (Dynamic Mapping)
    crawl_results = execute_crawl.expand(qual_payload=qualifications)

    # 5. Cập nhật Checkpoint State và danh sách tin đã thấy (Dynamic Mapping)
    checkpoints = update_checkpoint.expand(result_payload=crawl_results)

    # 6. Tổng kết toàn diện phiên chạy
    summarize_run(
        plans=plans,
        qualifications=qualifications,
        crawl_results=crawl_results,
        checkpoints=checkpoints,
    )


# Khởi tạo DAG object
roombeacon_crawler_dag = roombeacon_crawler()
