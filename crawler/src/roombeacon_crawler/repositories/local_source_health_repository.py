from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.source_health_state import (
    SourceHealthOutcome,
    SourceHealthState,
)
from roombeacon_crawler.policies.source_health_policy import SourceHealthPolicy
from roombeacon_crawler.repositories.source_health_repository import (
    SourceHealthRepository,
)

logger = logging.getLogger(__name__)


class LocalSourceHealthRepository(SourceHealthRepository):
    """Triển khai lưu trữ trạng thái sức khỏe nguồn cục bộ filesystem dưới /data/state/health/.

    Cấu trúc:
    <base_dir>/state/health/{source}__{target_id}.json
    """

    def __init__(
        self,
        base_data_dir: str | Path | None = None,
        policy: SourceHealthPolicy | None = None,
    ) -> None:
        raw_dir = base_data_dir or env.crawler.data_dir
        self.base_dir = Path(raw_dir).resolve() / "state" / "health"
        self.policy = policy or SourceHealthPolicy()
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            fallback_base = Path("./data/state/health").resolve()
            self.base_dir = fallback_base
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def _health_file(self, source: str, target_id: str) -> Path:
        return self.base_dir / f"{source}__{target_id}.json"

    def get_health(self, source: str, target_id: str) -> SourceHealthState | None:
        path = self._health_file(source, target_id)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SourceHealthState.from_dict(data)
        except Exception as exc:
            logger.warning("Lỗi đọc health state từ %s: %s", path, exc)
            return None

    def save_health(self, state: SourceHealthState) -> None:
        path = self._health_file(state.source, state.target_id)
        temp_file = path.with_suffix(".tmp")
        data = state.to_dict()
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, path)
            logger.debug("Đã lưu an toàn health state cho %s/%s tại %s", state.source, state.target_id, path)
        except Exception as exc:
            if temp_file.is_file():
                temp_file.unlink(missing_ok=True)
            logger.error("Lỗi lưu health state tại %s: %s", path, exc)
            raise

    def record_failure(
        self,
        source: str,
        target_id: str,
        outcome: SourceHealthOutcome,
        reason: str | None = None,
        http_status: int | None = None,
        current_time: datetime | None = None,
    ) -> SourceHealthState:
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_iso = now.isoformat()

        current = self.get_health(source, target_id) or SourceHealthState(
            source=source,
            target_id=target_id,
        )

        failures = current.consecutive_failures + 1
        cd_dt = self.policy.calculate_cooldown(outcome, failures, current_time=now)
        cd_iso = cd_dt.isoformat() if cd_dt else None
        backoff_minutes = self.policy.get_backoff_duration_minutes(outcome, failures)

        updated_state = SourceHealthState(
            source=source,
            target_id=target_id,
            last_outcome=outcome,
            last_failure_reason=reason,
            consecutive_failures=failures,
            last_checked_at=now_iso,
            last_failure_at=now_iso,
            last_access_success_at=current.last_access_success_at,
            cooldown_until=cd_iso,
            last_http_status=http_status,
            updated_at=now_iso,
        )
        self.save_health(updated_state)

        logger.info("=" * 60)
        logger.info("SOURCE HEALTH UPDATE")
        logger.info("Source               : %s", source)
        logger.info("Target               : %s", target_id)
        logger.info("Outcome              : %s", outcome.value)
        logger.info("Consecutive failures : %d", failures)
        logger.info("Backoff              : %d minutes", backoff_minutes)
        logger.info("Next retry           : %s", cd_iso or "IMMEDIATE")
        logger.info("=" * 60)

        return updated_state

    def record_success(
        self,
        source: str,
        target_id: str,
        current_time: datetime | None = None,
    ) -> SourceHealthState:
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_iso = now.isoformat()

        updated_state = SourceHealthState(
            source=source,
            target_id=target_id,
            last_outcome=SourceHealthOutcome.HEALTHY,
            last_failure_reason=None,
            consecutive_failures=0,
            last_checked_at=now_iso,
            last_failure_at=None,
            last_access_success_at=now_iso,
            cooldown_until=None,
            last_http_status=200,
            updated_at=now_iso,
        )
        self.save_health(updated_state)
        logger.info("Source Health phục hồi HEALTHY cho %s/%s", source, target_id)
        return updated_state
