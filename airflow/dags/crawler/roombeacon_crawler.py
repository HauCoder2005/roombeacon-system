from datetime import datetime, timedelta
import logging

from airflow.decorators import dag, task
from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.models.param import Param
from airflow.utils.trigger_rule import TriggerRule

from roombeacon_crawler.enums.crawl_run_mode import CrawlRunMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.models.source_qualification_result import (
    QualificationOverallStatus,
    RobotsQualificationStatus,
    UrlSafetyStatus,
)
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.services.source_qualifier import SourceQualifier
from roombeacon_crawler.services.target_provider import (
    AdapterScheduledTargetProvider,
)
from roombeacon_crawler.sources.resolver import SourceResolver
from roombeacon_crawler.validators.url_validator import URLValidator

logger = logging.getLogger(__name__)

default_args = {
    "owner": "roombeacon",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


def _resolve_runtime_params(context: dict) -> dict:
    """Trích xuất và chuẩn hóa tham số thực thi trực tiếp từ context['params'] của DagRun hiện tại."""
    params = context.get("params") or {}
    if not params and isinstance(context, dict):
        params = context

    raw_target_url = params.get("target_url") or params.get("url") or ""
    target_url = str(raw_target_url).strip()

    raw_run_mode = params.get("run_mode")
    if raw_run_mode is not None and str(raw_run_mode).strip():
        run_mode = (
            CrawlRunMode.SINGLE_TARGET
            if str(raw_run_mode).upper() == CrawlRunMode.SINGLE_TARGET.value
            else CrawlRunMode.SCHEDULED_ALL
        )
    elif target_url:
        run_mode = CrawlRunMode.SINGLE_TARGET
    else:
        run_mode = CrawlRunMode.SCHEDULED_ALL

    raw_max_pages = params.get("max_pages")
    max_pages = int(raw_max_pages) if raw_max_pages is not None else 1

    raw_max_records = params.get("max_records")
    max_records = int(raw_max_records) if raw_max_records is not None else 20

    raw_crawl_details = params.get("crawl_details")
    if raw_crawl_details is None:
        crawl_details = False
    elif isinstance(raw_crawl_details, str):
        crawl_details = raw_crawl_details.strip().lower() in ("true", "1", "yes")
    else:
        crawl_details = bool(raw_crawl_details)

    raw_max_details = params.get("max_details_per_run")
    if (
        raw_max_details is not None
        and str(raw_max_details).strip() != ""
        and str(raw_max_details).lower() != "null"
    ):
        max_details_per_run = int(raw_max_details)
    else:
        max_details_per_run = None

    return {
        "run_mode": run_mode,
        "target_url": target_url,
        "max_pages": max_pages,
        "max_records": max_records,
        "crawl_details": crawl_details,
        "max_details_per_run": max_details_per_run,
    }


@task
def discover_scheduled_targets(**context) -> list[dict]:
    """Phát hiện và tạo danh sách các targets cần xử lý (hỗ trợ cả SINGLE_TARGET và SCHEDULED_ALL)."""
    runtime_params = _resolve_runtime_params(context)
    run_mode = runtime_params["run_mode"]
    target_url = runtime_params["target_url"]

    logger.info("=" * 60)
    logger.info("BẮT ĐẦU RESOLVE CRAWL TARGETS (Mode: %s)", run_mode.value)
    logger.info("=" * 60)

    if run_mode == CrawlRunMode.SINGLE_TARGET:
        if not target_url:
            logger.error("Chế độ SINGLE_TARGET yêu cầu cung cấp target_url hợp lệ.")
            raise AirflowException(
                "Target URL is required when running in SINGLE_TARGET mode."
            )

        # 1. URL Safety Check
        is_valid, error_reason = URLValidator.validate(target_url)
        if not is_valid:
            logger.error("URL KHÔNG HỢP LỆ HOẶC BỊ TỪ CHỐI BẢO MẬT: %s", error_reason)
            raise AirflowException(f"URL validation failed: {error_reason}")

        # 2. Source Registry Resolution
        resolved_source = SourceResolver.resolve_source_name(target_url)
        if not resolved_source:
            supported = ", ".join(SourceResolver.get_supported_sources())
            logger.error(
                "URL chưa được hỗ trợ bởi Adapter nào (Đang hỗ trợ: %s)",
                supported,
            )
            raise AirflowException(
                f"Unsupported source domain for target URL: {target_url}. Currently supported sources: {supported}"
            )

        logger.info("Single target resolved: source='%s', url='%s'", resolved_source, target_url)
        return [
            {
                "source": resolved_source,
                "url": target_url,
                "label": "manual_single_target",
                "enabled": True,
            }
        ]

    # Mode: SCHEDULED_ALL
    provider = AdapterScheduledTargetProvider()
    seeds = provider.get_scheduled_targets()

    targets_payload = [seed.to_dict() for seed in seeds]
    sources_list = sorted(list(set(t["source"] for t in targets_payload)))

    logger.info("=" * 60)
    logger.info("DISCOVERED SOURCES")
    logger.info("Count  : %d", len(sources_list))
    logger.info("Sources: %s", ", ".join(sources_list))
    logger.info("-" * 60)
    logger.info("SCHEDULED TARGETS")
    logger.info("Count  : %d", len(targets_payload))
    for idx, t in enumerate(targets_payload, start=1):
        logger.info("  [%d] Source: %-12s | URL: %s", idx, t["source"], t["url"])
    logger.info("=" * 60)

    return targets_payload


@task
def qualify_and_crawl_target(target: dict, **context) -> dict:
    """Thẩm định per-run robots/URL cho từng target và thực thi crawl nếu hợp lệ (độc lập giữa các sources)."""
    runtime_params = _resolve_runtime_params(context)
    run_mode = runtime_params["run_mode"]
    max_pages = runtime_params["max_pages"]
    max_records = runtime_params["max_records"]
    crawl_details = runtime_params["crawl_details"]
    max_details_per_run = runtime_params["max_details_per_run"]

    source = target.get("source", "unknown")
    url = target.get("url", "")

    # 1. Per-run Qualification
    qualifier = SourceQualifier()
    qual_result = qualifier.qualify(url)

    logger.info("=" * 60)
    logger.info("SOURCE QUALIFICATION")
    logger.info("Source : %s", source)
    logger.info("Target : %s", url)
    logger.info("Adapter: %s (%s)", qual_result.adapter_status.value, qual_result.source_name or "N/A")
    logger.info("Robots : %s", qual_result.robots_status.value)
    logger.info("Overall: %s", qual_result.overall_status.value)
    if qual_result.reason:
        logger.info("Reason : %s", qual_result.reason)
    logger.info("=" * 60)

    # 2. Xử lý theo kết quả thẩm định
    if qual_result.overall_status == QualificationOverallStatus.DENIED_BY_ROBOTS:
        logger.warning("=" * 60)
        logger.warning("CRAWL SKIP")
        logger.warning("Reason : ROBOTS_DENIED")
        logger.warning("Target : %s (Source: %s)", url, source)
        logger.warning("=" * 60)

        if run_mode == CrawlRunMode.SINGLE_TARGET:
            raise AirflowSkipException(
                f"Crawl stopped because robots.txt does not allow target: {url}"
            )

        return {
            "source": source,
            "target_url": url,
            "qualification_status": qual_result.overall_status.value,
            "crawl_status": "skipped",
            "run_id": None,
            "records_created": 0,
            "pages_attempted": 0,
            "pages_success": 0,
            "pages_failed": 0,
            "details_success": 0,
            "details_failed": 0,
            "bronze_path": None,
            "manifest_path": None,
            "action": "SKIPPED",
            "reason": qual_result.reason or "Robots denied",
        }

    if qual_result.overall_status == QualificationOverallStatus.CHECK_FAILED:
        err_msg = f"Robots check failed for {url}: {qual_result.reason}"
        logger.error(err_msg)
        raise AirflowException(err_msg)

    if qual_result.overall_status == QualificationOverallStatus.INVALID_URL:
        err_msg = f"Invalid target URL {url}: {qual_result.reason}"
        logger.error(err_msg)
        if run_mode == CrawlRunMode.SINGLE_TARGET:
            raise AirflowException(err_msg)
        return {
            "source": source,
            "target_url": url,
            "qualification_status": qual_result.overall_status.value,
            "crawl_status": "invalid",
            "run_id": None,
            "records_created": 0,
            "pages_attempted": 0,
            "pages_success": 0,
            "pages_failed": 0,
            "details_success": 0,
            "details_failed": 0,
            "bronze_path": None,
            "manifest_path": None,
            "action": "SKIPPED",
            "reason": qual_result.reason or "Invalid URL",
        }

    # 3. READY -> Thực thi crawl
    logger.info("=" * 60)
    logger.info("CRAWL START")
    logger.info("Target URL   : %s", url)
    logger.info("Source       : %s", source)
    logger.info("Max Pages    : %d", max_pages)
    logger.info("Max Records  : %d", max_records)
    logger.info("Crawl Details: %s", crawl_details)
    logger.info("=" * 60)

    try:
        records, result = CrawlRunner.execute_crawl(
            url=url,
            max_pages=max_pages,
            max_records=max_records,
            crawl_details=crawl_details,
            max_details_per_run=max_details_per_run,
        )
    except Exception as exc:
        logger.exception("LỖI NGOẠI LỆ KHI THỰC THI CRAWLER CHO %s: %s", url, exc)
        raise AirflowException(f"CrawlRunner failed for {url}: {exc}") from exc

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

    action = (
        "ACCESS_CHALLENGE"
        if result.status
        in (CrawlStatus.CLOUDFLARE_CHALLENGE, CrawlStatus.ACCESS_DENIED)
        else "CRAWLED"
    )

    return {
        "source": source,
        "target_url": url,
        "qualification_status": qual_result.overall_status.value,
        "crawl_status": result.status.value,
        "run_id": result.run_id,
        "records_created": result.records_created,
        "pages_attempted": getattr(result, "pages_attempted", 0),
        "pages_success": result.pages_success,
        "pages_failed": result.pages_failed,
        "details_success": result.details_success,
        "details_failed": result.details_failed,
        "bronze_path": result.bronze_path,
        "manifest_path": result.manifest_path,
        "action": action,
        "reason": (
            f"Access Challenge ({result.status.value})"
            if result.status in (CrawlStatus.CLOUDFLARE_CHALLENGE, CrawlStatus.ACCESS_DENIED)
            else result.failure_reason
        ),
    }


@task(trigger_rule=TriggerRule.ALL_DONE)
def summarize_crawl_results(results: list[dict], **context) -> dict:
    """Tổng kết toàn bộ kết quả của phiên crawl định kỳ hoặc thủ công."""
    if not results or not isinstance(results, list):
        results = []

    targets_discovered = len(results)
    sources_discovered = len(set(r.get("source", "") for r in results if r.get("source")))

    qualification_ready = sum(
        1 for r in results if r.get("qualification_status") == QualificationOverallStatus.READY.value
    )
    qualification_denied = sum(
        1 for r in results if r.get("qualification_status") == QualificationOverallStatus.DENIED_BY_ROBOTS.value
    )

    crawl_success = sum(1 for r in results if r.get("crawl_status") == CrawlStatus.SUCCESS.value)
    access_challenge = sum(
        1
        for r in results
        if r.get("crawl_status")
        in (
            CrawlStatus.CLOUDFLARE_CHALLENGE.value,
            CrawlStatus.ACCESS_DENIED.value,
        )
        or r.get("action") == "ACCESS_CHALLENGE"
    )
    crawl_skipped = sum(1 for r in results if r.get("action") == "SKIPPED")
    crawl_failed = sum(
        1
        for r in results
        if r.get("crawl_status")
        in (
            CrawlStatus.CONNECTION_ERROR.value,
            CrawlStatus.SERVER_ERROR.value,
            CrawlStatus.TIMEOUT.value,
            CrawlStatus.PARSE_ERROR.value,
        )
    )

    records_created = sum(r.get("records_created", 0) for r in results)
    details_created = sum(r.get("details_success", 0) for r in results)

    logger.info("=" * 60)
    logger.info("ROOMBEACON SCHEDULED RUN SUMMARY")
    logger.info("-" * 60)
    logger.info("Targets discovered : %d", targets_discovered)
    logger.info("Sources discovered : %d", sources_discovered)
    logger.info("READY              : %d", qualification_ready)
    logger.info("ROBOTS_DENIED      : %d", qualification_denied)
    logger.info("Crawl success      : %d", crawl_success)
    logger.info("Access challenge   : %d", access_challenge)
    logger.info("Crawl skipped      : %d", crawl_skipped)
    logger.info("Crawl failed       : %d", crawl_failed)
    logger.info("Records created    : %d", records_created)
    logger.info("Details created    : %d", details_created)
    logger.info("=" * 60)

    return {
        "targets_discovered": targets_discovered,
        "sources_discovered": sources_discovered,
        "qualification_ready": qualification_ready,
        "qualification_denied": qualification_denied,
        "crawl_success": crawl_success,
        "access_challenge": access_challenge,
        "crawl_skipped": crawl_skipped,
        "crawl_failed": crawl_failed,
        "records_created": records_created,
        "details_created": details_created,
    }


def task_validate_url(**context) -> dict:
    """Kiểm tra tính an toàn kỹ thuật của runtime Target URL và phân giải nguồn tương ứng."""
    runtime_params = _resolve_runtime_params(context)
    target_url = runtime_params["target_url"]

    logger.info("=" * 60)
    logger.info("KIỂM TRA RUNTIME URL: %s", target_url)
    logger.info("=" * 60)

    # 1. Generic URL & SSRF Validation (không hardcode domain)
    is_valid, error_reason = URLValidator.validate(target_url)
    if not is_valid:
        logger.error("URL KHÔNG HỢP LỆ HOẶC BỊ TỪ CHỐI BẢO MẬT: %s", error_reason)
        raise AirflowException(f"URL validation failed: {error_reason}")

    # 2. Source Registry Resolution
    resolved_source = SourceResolver.resolve_source_name(target_url)
    if not resolved_source:
        supported = ", ".join(SourceResolver.get_supported_sources())
        logger.error(
            "URL hợp lệ về mặt kỹ thuật nhưng chưa được hỗ trợ bởi Adapter nào (Đang hỗ trợ: %s)",
            supported,
        )
        raise AirflowException(
            f"Unsupported source domain for target URL: {target_url}. Currently supported sources: {supported}"
        )

    logger.info("✓ URL an toàn và hợp lệ. Source resolved: '%s'", resolved_source)
    return {
        "target_url": target_url,
        "source": resolved_source,
    }


def task_execute_crawl(**context) -> dict:
    """Wrapper thực thi crawl phục vụ cho legacy tests và manual single execution."""
    runtime_params = _resolve_runtime_params(context)
    target_url = runtime_params["target_url"]
    max_pages = runtime_params["max_pages"]
    max_records = runtime_params["max_records"]
    crawl_details = runtime_params["crawl_details"]
    max_details_per_run = runtime_params["max_details_per_run"]

    try:
        records, result = CrawlRunner.execute_crawl(
            url=target_url,
            max_pages=max_pages,
            max_records=max_records,
            crawl_details=crawl_details,
            max_details_per_run=max_details_per_run,
        )
    except Exception as exc:
        logger.exception("LỖI NGOẠI LỆ KHI THỰC THI CRAWLER: %s", exc)
        raise AirflowException(f"CrawlRunner execution failed: {exc}") from exc

    if (
        result.status == CrawlStatus.ROBOTS_DENIED
        or result.stop_reason == CrawlStatus.ROBOTS_DENIED
    ):
        raise AirflowSkipException(
            "Crawl stopped because robots.txt does not allow this target."
        )

    if result.status in (
        CrawlStatus.ACCESS_DENIED,
        CrawlStatus.CLOUDFLARE_CHALLENGE,
        CrawlStatus.UNSUPPORTED_TARGET,
    ):
        raise AirflowSkipException(
            f"Crawl stopped due to policy / target decision: {result.status.value}"
        )

    if result.status in (
        CrawlStatus.CONNECTION_ERROR,
        CrawlStatus.SERVER_ERROR,
        CrawlStatus.TIMEOUT,
        CrawlStatus.PARSE_ERROR,
    ):
        err_msg = result.failure_reason or f"Technical error encountered: {result.status.value}"
        raise AirflowException(f"Crawl run {result.run_id} failed: {err_msg}")

    return {
        "run_id": result.run_id,
        "source": result.source,
        "status": result.status.value,
        "records_created": result.records_created,
        "pages_success": result.pages_success,
        "pages_failed": result.pages_failed,
        "details_success": result.details_success,
        "details_failed": result.details_failed,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }


@dag(
    dag_id="roombeacon_crawler",
    default_args=default_args,
    description="RoomBeacon Generic Multi-Source Production Crawler — Lịch thu thập định kỳ và phân tích theo nguồn",
    schedule="0 */6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    render_template_as_native_obj=True,
    tags=["crawler", "roombeacon", "bronze", "multi-source", "scheduled"],
    params={
        "run_mode": Param(
            default=CrawlRunMode.SCHEDULED_ALL.value,
            type="string",
            enum=[CrawlRunMode.SCHEDULED_ALL.value, CrawlRunMode.SINGLE_TARGET.value],
            title="Execution Mode",
            description="Chế độ thực thi: SCHEDULED_ALL (tự động phát hiện và crawl tất cả nguồn được phép) hoặc SINGLE_TARGET (chỉ crawl target_url được chỉ định).",
        ),
        "target_url": Param(
            default="",
            type=["string", "null"],
            title="Target URL (khi run_mode=SINGLE_TARGET)",
            description="Đường dẫn danh mục cụ thể cần crawl khi chạy ở chế độ SINGLE_TARGET (ví dụ: https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/ hoặc https://phongtro123.com/cho-thue-phong-tro).",
        ),
        "max_pages": Param(
            default=1,
            type="integer",
            minimum=1,
            maximum=50,
            title="Max Pages",
            description="Số trang listing tối đa cần duyệt trên mỗi target (Maximum number of listing pages to crawl).",
        ),
        "max_records": Param(
            default=20,
            type="integer",
            minimum=1,
            maximum=1000,
            title="Max Records",
            description="Số lượng tin đăng tối đa cần trích xuất trên mỗi target (Stop when this many listing records have been collected).",
        ),
        "crawl_details": Param(
            default=False,
            type="boolean",
            title="Crawl Detail Pages",
            description="Bật/tắt việc thu thập thông tin chi tiết từng tin đăng (Whether detail pages should be fetched).",
        ),
        "max_details_per_run": Param(
            default=3,
            type=["null", "integer"],
            minimum=0,
            maximum=1000,
            title="Max Details Per Run",
            description="Giới hạn số request detail trang con khi bật crawl_details.",
        ),
    },
)
def roombeacon_crawler_dag():
    targets = discover_scheduled_targets()
    crawl_results = qualify_and_crawl_target.expand(target=targets)
    summarize_crawl_results(crawl_results)


dag = roombeacon_crawler_dag()
