"""Load scheduled targets and turn due work into bounded crawl plans.

This module is deliberately Airflow-free. Runtime adapters are composed inside the
relevant use-case boundary until Phase 3 introduces explicit composition roots.
"""

from datetime import datetime, timezone
import logging
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.services.crawl_planner import CrawlPlanner
from roombeacon_crawler.services.target_provider import (
    AdapterScheduledTargetProvider,
)
from roombeacon_crawler.sources.registry import source_registry
from roombeacon_crawler.sources.resolver import SourceResolver

logger = logging.getLogger(__name__)


from roombeacon_crawler.application.orchestration.errors import CrawlerWorkflowError


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
            raise CrawlerWorkflowError(
                "Chế độ DEBUG_SINGLE_TARGET yêu cầu nhập 'debug_target_url'."
            )
        resolved_adapter = SourceResolver.resolve(debug_url)
        source_name = resolved_adapter.SOURCE_NAME if resolved_adapter else "unknown"
        state = repo.get_state(source_name, "debug_single_target")
        start_page = (
            state.bootstrap_next_page
            if (state and not getattr(state, "bootstrap_completed", False) and state.bootstrap_next_page)
            else 1
        )
        plan_mode = (
            CrawlMode.BOOTSTRAP_CONTINUE
            if (state and not getattr(state, "bootstrap_completed", False) and state.bootstrap_next_page)
            else CrawlMode.FORCE_FULL
        )
        plan = CrawlPlan(
            source=source_name,
            target_id="debug_single_target",
            target_url=debug_url,
            mode=plan_mode,
            reason="DEBUG_SINGLE_TARGET_MANUAL_TRIGGER",
            planned_at=now.isoformat(),
            crawl_details=debug_crawl_details,
            safety_max_pages=debug_max_pages if debug_max_pages > 0 else 10,
            safety_max_records=debug_max_records if debug_max_records > 0 else 200,
            start_page=start_page,
        )
        logger.info("Tạo 1 CrawlPlan DEBUG cho URL: %s (start_page=%d, mode=%s)", debug_url, start_page, plan_mode.value if hasattr(plan_mode, "value") else str(plan_mode))
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
