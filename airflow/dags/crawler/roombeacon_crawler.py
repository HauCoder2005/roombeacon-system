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
from roombeacon_crawler.models.source_health_state import (
    SourceHealthOutcome,
    SourceHealthState,
)
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
from roombeacon_crawler.repositories.local_source_health_repository import (
    LocalSourceHealthRepository,
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

    # 1. Source Health Gate: Kiểm tra Cooldown trước khi gửi bất kỳ request mạng nào
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

    # 2. URL Safety & SSRF Check
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

    # 3. Robots.txt Preflight Check
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
        "observations_written": getattr(result, "observations_written", len(getattr(result, "observed_listing_ids", []))),
        "bootstrap_completed": getattr(result, "bootstrap_completed", False),
        "bootstrap_start_page": getattr(result, "bootstrap_start_page", 1),
        "bootstrap_next_page": getattr(result, "bootstrap_next_page", None),
    }


# --------------------------------------------------------------------------
# Task 5: Persist Bronze to MySQL (Mapped per Crawl Result)
# --------------------------------------------------------------------------
@task
def persist_bronze_mysql(result_payload: dict, **context) -> dict:
    """5. Đọc Bronze Artifacts (listings.json, details.json) và persist vào MySQL Database qua Use Case."""
    source = result_payload.get("source", "unknown")
    target_id = result_payload.get("target_id", "default")
    run_id = result_payload.get("run_id") or result_payload.get("crawl_run_id")
    bronze_path = result_payload.get("bronze_path")
    action = result_payload.get("action", "UNKNOWN")
    crawl_status = result_payload.get("crawl_status", "unknown")

    logger.info("=" * 60)
    logger.info("STAGE 5: PERSIST BRONZE TO MYSQL")
    logger.info("Source: %s | Target ID: %s | Run ID: %s | Bronze Path: %s", source, target_id, run_id, bronze_path)
    logger.info("=" * 60)

    # 1. Bỏ qua persist nếu không có dữ liệu Bronze hợp lệ
    if action == "SKIPPED" or not bronze_path or crawl_status != CrawlStatus.SUCCESS.value:
        logger.info("Bỏ qua persist MySQL cho %s/%s (action=%s, status=%s, bronze_path=%s)", source, target_id, action, crawl_status, bronze_path)
        return {
            "source": source,
            "target_id": target_id,
            "run_id": run_id,
            "status": "SKIPPED_NO_DATA",
            "posts_created": 0,
            "posts_existing": 0,
            "observations_inserted": 0,
            "technical_duplicates": 0,
            "crawl_result": result_payload,
        }

    # 2. Khởi tạo và nạp BronzeObservation
    from roombeacon_crawler.application.persistence.persist_observations import PersistBronzeObservationsUseCase
    from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
    from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import MySQLObservationRepository
    from roombeacon_crawler.infrastructure.mysql.repositories.platform_repository import MySQLPlatformRepository
    from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
    from roombeacon_crawler.infrastructure.mysql.repositories.rental_post_repository import MySQLRentalPostRepository
    from roombeacon_crawler.infrastructure.mysql.schema import ensure_mysql_schema
    from roombeacon_crawler.infrastructure.mysql.transaction import MySQLTransactionManager
    from roombeacon_crawler.mappers.bronze_observation_loader import BronzeObservationLoader

    try:
        ensure_mysql_schema()
    except Exception as exc:
        logger.warning("Không thể ensure schema tự động: %s", exc)

    observations = BronzeObservationLoader.load_from_bronze_dir(bronze_path, run_id=run_id)
    if not observations:
        logger.info("Không tìm thấy observation nào tại %s -> SKIPPED_NO_DATA", bronze_path)
        return {
            "source": source,
            "target_id": target_id,
            "run_id": run_id,
            "status": "SKIPPED_NO_DATA",
            "posts_created": 0,
            "posts_existing": 0,
            "observations_inserted": 0,
            "technical_duplicates": 0,
            "crawl_result": result_payload,
        }

    tx_mgr = MySQLTransactionManager()
    use_case = PersistBronzeObservationsUseCase(
        platform_repo=MySQLPlatformRepository(connection=None),
        rental_post_repo=MySQLRentalPostRepository(connection=None),
        observation_repo=MySQLObservationRepository(connection=None),
        children_repo=MySQLPostChildrenRepository(connection=None),
        transaction_mgr=tx_mgr,
    )

    try:
        import_res = use_case.execute(observations)
        logger.info("=" * 60)
        logger.info("MYSQL BRONZE PERSISTENCE")
        logger.info("=" * 60)
        logger.info("Source                 : %s", source)
        logger.info("Target                 : %s", target_id)
        logger.info("Run ID                 : %s", run_id)
        logger.info("Bronze Path            : %s", bronze_path)
        logger.info("Observations Read      : %d", len(observations))
        logger.info("Posts Created          : %d", import_res.posts_created)
        logger.info("Posts Existing         : %d", import_res.posts_existing)
        logger.info("Observations Inserted  : %d", import_res.observations_inserted)
        logger.info("Technical Duplicates   : %d", import_res.technical_duplicates)
        logger.info("Status                 : SUCCESS")
        logger.info("=" * 60)
        return {
            "source": source,
            "target_id": target_id,
            "run_id": run_id,
            "status": "SUCCESS",
            "posts_created": import_res.posts_created,
            "posts_existing": import_res.posts_existing,
            "observations_inserted": import_res.observations_inserted,
            "technical_duplicates": import_res.technical_duplicates,
            "crawl_result": result_payload,
        }
    except Exception as exc:
        logger.exception("LỖI KHI PERSIST BRONZE MYSQL CHO %s/%s: %s", source, target_id, exc)
        raise AirflowException(f"MySQL persistence failed for {source}/{target_id} (run_id={run_id}): {exc}") from exc


# --------------------------------------------------------------------------
# Task 6: Update Checkpoint (Mapped per Persist Result)
# --------------------------------------------------------------------------
@task
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
        ):
            state.bootstrap_completed = False
            state.bootstrap_next_page = result_payload.get("bootstrap_next_page")
        elif plan_mode in (
            CrawlMode.INCREMENTAL.value,
            CrawlMode.FORCE_INCREMENTAL.value,
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
@task(trigger_rule=TriggerRule.ALL_DONE, pool="duckdb_analytics_pool")
def refresh_duckdb_analytics(checkpoints: list[dict], **context) -> dict:
    """7. Khởi tạo/cập nhật Analytical Views trong DuckDB từ dữ liệu MySQL Bronze (READ_ONLY)."""
    logger.info("=" * 60)
    logger.info("STAGE 7: REFRESH DUCKDB ANALYTICS")
    logger.info("=" * 60)

    from analytics.duckdb.bootstrap import bootstrap_analytics

    try:
        bootstrap_analytics()
        logger.info("DuckDB Analytics views refreshed successfully.")
        return {"status": "SUCCESS"}
    except Exception as exc:
        logger.exception("Lỗi khi refresh DuckDB Analytics: %s", exc)
        return {"status": "FAILED", "error": str(exc)}


# --------------------------------------------------------------------------
# Task 8: Summarize Run (Finalization)
# --------------------------------------------------------------------------
@task(trigger_rule=TriggerRule.ALL_DONE)
def summarize_run(
    plans: list[dict] = None,
    qualifications: list[dict] = None,
    crawl_results: list[dict] = None,
    persistence_results: list[dict] = None,
    checkpoints: list[dict] = None,
    analytics_summary: dict = None,
    **context,
) -> dict:
    """8. Tổng hợp số liệu thống kê toàn diện của toàn bộ fleet sau phiên cào."""
    plans = plans or []
    qualifications = qualifications or []
    crawl_results = crawl_results or []
    persistence_results = persistence_results or []
    checkpoints = checkpoints or []
    analytics_summary = analytics_summary or {}

    targets_due = len(plans)
    targets_deferred_cooldown = sum(1 for q in qualifications if q.get("qualification_status") == "COOLDOWN_ACTIVE")
    targets_executable = targets_due - targets_deferred_cooldown

    bootstrap_planned = sum(1 for p in plans if p.get("mode") == CrawlMode.BOOTSTRAP_FULL.value)
    bootstrap_continue_planned = sum(1 for p in plans if p.get("mode") == CrawlMode.BOOTSTRAP_CONTINUE.value)
    incremental_planned = sum(
        1
        for p in plans
        if p.get("mode") in (CrawlMode.INCREMENTAL.value, CrawlMode.FORWARD_ONLY_INCREMENTAL.value)
    )

    qualification_allowed = sum(1 for q in qualifications if q.get("qualification_status") == "READY")
    robots_denied = sum(1 for q in qualifications if q.get("qualification_status") == "DENIED_BY_ROBOTS")
    robots_unavailable = sum(1 for q in qualifications if q.get("qualification_status") == "CHECK_FAILED")

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
    observations_written = sum(r.get("observations_written", 0) for r in crawl_results)
    details_created = sum(r.get("details_success", 0) for r in crawl_results)

    mysql_posts_created = sum(p.get("posts_created", 0) for p in persistence_results)
    mysql_posts_existing = sum(p.get("posts_existing", 0) for p in persistence_results)
    mysql_obs_inserted = sum(p.get("observations_inserted", 0) for p in persistence_results)
    mysql_tech_duplicates = sum(p.get("technical_duplicates", 0) for p in persistence_results)

    target_states_persisted = sum(1 for c in checkpoints if c.get("target_state_persisted"))
    success_checkpoints_advanced = sum(1 for c in checkpoints if c.get("success_checkpoint_advanced"))
    health_states_updated = sum(1 for c in checkpoints if c.get("health_state_updated"))

    logger.info("=" * 60)
    logger.info("ROOMBEACON INGESTION SUMMARY")
    logger.info("=" * 60)
    logger.info("Targets due                  : %d", targets_due)
    logger.info("Targets executable           : %d", targets_executable)
    logger.info("Targets deferred cooldown    : %d", targets_deferred_cooldown)
    logger.info("Bootstrap planned            : %d", bootstrap_planned)
    logger.info("Bootstrap continue planned   : %d", bootstrap_continue_planned)
    logger.info("Incremental planned          : %d", incremental_planned)
    logger.info("Qualification allowed        : %d", qualification_allowed)
    logger.info("Robots denied                : %d", robots_denied)
    logger.info("Robots unavailable           : %d", robots_unavailable)
    logger.info("Crawl success                : %d", crawl_success)
    logger.info("Access challenge             : %d", access_challenge)
    logger.info("Technical failure            : %d", technical_failure)
    logger.info("Records created (new)        : %d", records_created)
    logger.info("Observations written (Bronze): %d", observations_written)
    logger.info("Details created              : %d", details_created)
    logger.info("-" * 60)
    logger.info("MYSQL PERSISTENCE SUMMARY:")
    logger.info("Posts Created                : %d", mysql_posts_created)
    logger.info("Posts Existing               : %d", mysql_posts_existing)
    logger.info("Observations Inserted        : %d", mysql_obs_inserted)
    logger.info("Technical Duplicates         : %d", mysql_tech_duplicates)
    logger.info("-" * 60)
    logger.info("CHECKPOINT & HEALTH:")
    logger.info("Target states persisted      : %d", target_states_persisted)
    logger.info("Success checkpoints advanced : %d", success_checkpoints_advanced)
    logger.info("Health states updated        : %d", health_states_updated)
    logger.info("-" * 60)
    logger.info("SOURCE COVERAGE & ACQUISITION SUMMARY:")
    for r in crawl_results:
        src = r.get("source", "unknown")
        recs = r.get("records_created", 0)
        obs_w = r.get("observations_written", 0)
        seen_cnt = r.get("records_seen", 0)
        new_cnt = r.get("records_new", 0)
        known_cnt = r.get("records_known", 0)
        b_path = r.get("bronze_path") or "NONE"

        p_res = next((p for p in persistence_results if p.get("source") == src), {})
        m_status = p_res.get("status", "NONE")
        m_p_created = p_res.get("posts_created", 0)
        m_p_exist = p_res.get("posts_existing", 0)
        m_obs_ins = p_res.get("observations_inserted", 0)
        m_dups = p_res.get("technical_duplicates", 0)

        logger.info("-" * 40)
        logger.info("Source: %s", src)
        logger.info("Crawl")
        logger.info("  Mode                 : %s", r.get("plan", {}).get("mode", "UNKNOWN"))
        logger.info("  Status               : %s", r.get("crawl_status", "UNKNOWN"))
        logger.info("  Seen                 : %d", seen_cnt)
        logger.info("  New                  : %d", new_cnt)
        logger.info("  Known                : %d", known_cnt)
        logger.info("Bronze")
        logger.info("  Observations Written : %d", obs_w)
        logger.info("  Path                 : %s", b_path)
        logger.info("MySQL")
        logger.info("  Status               : %s", m_status)
        logger.info("  Posts Created        : %d", m_p_created)
        logger.info("  Posts Existing       : %d", m_p_exist)
        logger.info("  Observations Inserted: %d", m_obs_ins)
        logger.info("  Technical Duplicates : %d", m_dups)
        logger.info("Checkpoint")
        logger.info("  Persisted            : YES" if target_states_persisted else "NO")

    logger.info("=" * 60)
    logger.info("DuckDB")
    logger.info("  Refresh              : %s", analytics_summary.get("status", "UNKNOWN") if analytics_summary else "UNKNOWN")
    logger.info("=" * 60)

    return {
        "targets_due": targets_due,
        "targets_executable": targets_executable,
        "targets_deferred_cooldown": targets_deferred_cooldown,
        "bootstrap_planned": bootstrap_planned,
        "bootstrap_continue_planned": bootstrap_continue_planned,
        "incremental_planned": incremental_planned,
        "qualification_allowed": qualification_allowed,
        "robots_denied": robots_denied,
        "robots_unavailable": robots_unavailable,
        "crawl_success": crawl_success,
        "access_challenge": access_challenge,
        "technical_failure": technical_failure,
        "records_created": records_created,
        "observations_written": observations_written,
        "details_created": details_created,
        "mysql_posts_created": mysql_posts_created,
        "mysql_posts_existing": mysql_posts_existing,
        "mysql_observations_inserted": mysql_obs_inserted,
        "mysql_technical_duplicates": mysql_tech_duplicates,
        "target_states_persisted": target_states_persisted,
        "success_checkpoints_advanced": success_checkpoints_advanced,
        "health_states_updated": health_states_updated,
        "checkpoints_updated": sum(1 for c in checkpoints if c.get("checkpoint_updated") or c.get("target_state_persisted")),
        "duckdb_refresh": analytics_summary.get("status", "UNKNOWN") if analytics_summary else "UNKNOWN",
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

    # 5. Persist Bronze Observations vào MySQL Database (Dynamic Mapping)
    persistence_results = persist_bronze_mysql.expand(result_payload=crawl_results)

    # 6. Cập nhật Checkpoint State và danh sách tin đã thấy (Dynamic Mapping)
    checkpoints = update_checkpoint.expand(persist_payload=persistence_results)

    # 7. Khởi tạo/cập nhật DuckDB Analytics views một lần cho toàn bộ run
    analytics_summary = refresh_duckdb_analytics(checkpoints=checkpoints)

    # 8. Tổng kết toàn diện phiên chạy
    summarize_run(
        plans=plans,
        qualifications=qualifications,
        crawl_results=crawl_results,
        persistence_results=persistence_results,
        checkpoints=checkpoints,
        analytics_summary=analytics_summary,
    )


# Khởi tạo DAG object
roombeacon_crawler_dag = roombeacon_crawler()
