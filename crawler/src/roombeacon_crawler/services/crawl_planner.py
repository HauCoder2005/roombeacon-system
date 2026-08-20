from datetime import datetime, timedelta, timezone
import logging

from roombeacon_crawler.discovery.strategy_resolver import (
    DiscoveryStrategy,
    DiscoveryStrategyResolver,
)
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.repositories.crawl_state_repository import (
    CrawlStateRepository,
)

logger = logging.getLogger(__name__)


class CrawlPlanner:
    """Service lập kế hoạch cào dữ liệu tự động (Crawl Planner).

    Chịu trách nhiệm:
    1. Kiểm tra các target xem có đến hạn chạy (DUE) không.
    2. Tự động xác định chế độ BOOTSTRAP_FULL (nếu chưa từng crawl thành công) vs INCREMENTAL (nếu đã có checkpoint).
    3. Phân giải chiến lược khám phá (STANDARD vs ENHANCED_DISCOVERY) qua DiscoveryStrategyResolver.
    4. Tính toán khung thời gian overlap và watermark an toàn.
    5. Áp dụng bounded backoff nếu target gặp sự cố kỹ thuật liên tiếp.
    6. Tạo danh sách CrawlPlan gọn nhẹ, độc lập phục vụ Airflow Dynamic Task Mapping.
    """

    def __init__(
        self,
        state_repository: CrawlStateRepository,
        discovery_strategy_resolver: DiscoveryStrategyResolver | None = None,
    ) -> None:
        self.state_repository = state_repository
        self.discovery_strategy_resolver = (
            discovery_strategy_resolver or DiscoveryStrategyResolver()
        )

    def plan_all(
        self,
        seeds: list[CrawlSeed],
        current_time: datetime | None = None,
        override_mode: str | None = None,
    ) -> list[CrawlPlan]:
        """Tính toán kế hoạch cào dữ liệu cho tất cả các điểm vào (CrawlSeed)."""
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        plans: list[CrawlPlan] = []

        for seed in seeds:
            if not seed.enabled or not seed.url:
                logger.debug("Bỏ qua seed bị vô hiệu hóa: %s/%s", seed.source, seed.target_id)
                continue

            state = self.state_repository.get_state(seed.source, seed.target_id)

            # 1. Kiểm tra tính DUE
            is_due = self._is_target_due(seed, state, now, override_mode)
            if not is_due:
                logger.info(
                    "Target %s/%s chưa đến hạn chạy (next_run_at: %s)",
                    seed.source,
                    seed.target_id,
                    state.next_run_at if state else "N/A",
                )
                continue

            # 2. Xác định CrawlMode và Lý do
            mode, reason = self._resolve_mode_and_reason(state, override_mode)

            # 3. Phân giải chiến lược khám phá (STANDARD vs ENHANCED_DISCOVERY)
            discovery_strategy = self.discovery_strategy_resolver.resolve(seed.source)

            # 4. Tính toán Watermark & Overlap Window
            watermark_from = state.last_watermark_at if state else None
            overlap_from = None
            if watermark_from:
                try:
                    wm_dt = datetime.fromisoformat(watermark_from)
                    if wm_dt.tzinfo is None:
                        wm_dt = wm_dt.replace(tzinfo=timezone.utc)
                    overlap_dt = wm_dt - timedelta(hours=seed.incremental_overlap_hours)
                    overlap_from = overlap_dt.isoformat()
                except Exception as exc:
                    logger.warning("Lỗi tính toán overlap date từ %s: %s", watermark_from, exc)
                    overlap_from = None

            plan = CrawlPlan(
                source=seed.source,
                target_id=seed.target_id,
                target_url=seed.url,
                mode=mode,
                reason=reason,
                planned_at=now.isoformat(),
                watermark_from=watermark_from,
                overlap_from=overlap_from,
                crawl_details=seed.crawl_details,
                safety_max_pages=seed.bootstrap_safety_max_pages,
                safety_max_records=seed.bootstrap_safety_max_records,
                incremental_stop_after_known_pages=seed.incremental_stop_after_known_pages,
                max_details_per_run=seed.max_details_per_run,
                discovery_strategy=discovery_strategy,
            )
            plans.append(plan)

        logger.info(
            "CRAWL PLANNER HOÀN TẤT: %d/%d targets được lên kế hoạch (override_mode=%s)",
            len(plans),
            len(seeds),
            override_mode or "AUTO",
        )
        return plans

    def _is_target_due(
        self,
        seed: CrawlSeed,
        state,
        now: datetime,
        override_mode: str | None,
    ) -> bool:
        """Kiểm tra xem target đã đến thời điểm cần kích hoạt crawl hay chưa."""
        if override_mode in ("FORCE_FULL", "FORCE_INCREMENTAL", "DEBUG_SINGLE_TARGET"):
            return True

        if state is None or state.last_success_at is None:
            # Chưa từng có state hoặc chưa từng thành công -> Phải chạy ngay
            return True

        if state.next_run_at:
            try:
                next_dt = datetime.fromisoformat(state.next_run_at)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=timezone.utc)
                return now >= next_dt
            except Exception:
                pass

        if state.last_finished_at or state.last_started_at:
            try:
                last_dt = datetime.fromisoformat(state.last_finished_at or state.last_started_at)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                return now >= (last_dt + timedelta(minutes=seed.interval_minutes))
            except Exception:
                pass

        return True

    def _resolve_mode_and_reason(
        self, state, override_mode: str | None
    ) -> tuple[CrawlMode, str]:
        """Quyết định chế độ cào dữ liệu và lý do tương ứng."""
        if override_mode == "FORCE_FULL":
            return CrawlMode.FORCE_FULL, "FORCE_FULL_OVERRIDE"

        if override_mode == "FORCE_INCREMENTAL":
            return CrawlMode.FORCE_INCREMENTAL, "FORCE_INCREMENTAL_OVERRIDE"

        if state is None or state.last_success_at is None:
            return CrawlMode.BOOTSTRAP_FULL, "FIRST_SUCCESSFUL_CRAWL_NOT_FOUND"

        return CrawlMode.INCREMENTAL, "INCREMENTAL_SCHEDULED_DUE"
