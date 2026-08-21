from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from sqlalchemy import text

from roombeacon_crawler.application.persistence.persist_observations import PersistBronzeObservationsUseCase
from roombeacon_crawler.application.reconciliation.discovery import BronzeRunInfo
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import MySQLObservationRepository
from roombeacon_crawler.infrastructure.mysql.repositories.platform_repository import MySQLPlatformRepository
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
from roombeacon_crawler.infrastructure.mysql.repositories.rental_post_repository import MySQLRentalPostRepository
from roombeacon_crawler.infrastructure.mysql.schema import ensure_mysql_schema
from roombeacon_crawler.infrastructure.mysql.transaction import MySQLTransactionManager
from roombeacon_crawler.mappers.bronze_observation_loader import BronzeObservationLoader

logger = logging.getLogger("BRONZE_RECONCILER")


@dataclass
class ReconciliationSummary:
    dag_run_id: str = "UNKNOWN"
    runs_discovered: int = 0
    runs_selected: int = 0
    already_reconciled: int = 0
    partially_missing: int = 0
    fully_missing: int = 0
    runs_persisted_this_cycle: int = 0
    runs_failed_this_cycle: int = 0
    not_inspected_yet: int = 0
    remaining_real_backlog: int = 0

    observations_scanned: int = 0
    already_in_mysql: int = 0
    inserted_this_run: int = 0
    invalid: int = 0
    failed: int = 0

    mysql_before: int = 0
    mysql_after: int = 0
    observed_db_delta: int = 0
    concurrent_external_delta: int = 0

    duckdb_observations: int = 0
    mysql_equals_duckdb: str = "NO"
    status: str = "SUCCESS"

    def to_dict(self) -> dict:
        return asdict(self)


class BronzeReconcilerService:
    """Dịch vụ tự động đối soát và nạp bù dữ liệu Bronze lịch sử vào MySQL Database."""

    @classmethod
    def get_mysql_observations_count(cls, engine=None) -> int:
        """Đếm chính xác tổng số rental_post_versions hiện tại trong MySQL."""
        eng = engine or MySQLConnectionFactory.get_engine()
        ensure_mysql_schema(eng)
        with eng.connect() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM rental_post_versions")).scalar() or 0)

    @classmethod
    def get_mysql_posts_count(cls, engine=None) -> int:
        """Đếm chính xác tổng số rental_posts hiện tại trong MySQL."""
        eng = engine or MySQLConnectionFactory.get_engine()
        ensure_mysql_schema(eng)
        with eng.connect() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM rental_posts")).scalar() or 0)

    @classmethod
    def get_persisted_run_counts(cls, engine=None) -> dict[str, int]:
        """Truy vấn số lượng observation đã persist theo từng crawl_run_id từ MySQL."""
        eng = engine or MySQLConnectionFactory.get_engine()
        ensure_mysql_schema(eng)
        with eng.connect() as conn:
            query = text("SELECT crawl_run_id, COUNT(*) FROM rental_post_versions GROUP BY crawl_run_id")
            rows = conn.execute(query).fetchall()
            return {r[0]: r[1] for r in rows}

    @classmethod
    def audit_and_identify_missing_runs(
        cls,
        discovered_runs: list[BronzeRunInfo],
        batch_limit: int = 25,
        engine=None,
        persisted_counts: dict[str, int] | None = None,
    ) -> tuple[list[BronzeRunInfo], dict]:
        """So sánh toàn bộ danh sách Bronze runs với MySQL để phân loại chính xác tình trạng:

        - already_reconciled: Đã nạp đủ toàn bộ observations
        - partially_missing: Đã nạp một phần nhưng còn thiếu
        - fully_missing: Chưa nạp observation nào
        - not_inspected_yet: 0 (đã kiểm tra toàn bộ 100% discovered runs)
        """
        if persisted_counts is None:
            persisted_counts = cls.get_persisted_run_counts(engine)

        already_reconciled_list: list[BronzeRunInfo] = []
        partially_missing_list: list[BronzeRunInfo] = []
        fully_missing_list: list[BronzeRunInfo] = []

        for run in discovered_runs:
            mysql_count = persisted_counts.get(run.run_id, 0)
            if mysql_count == 0:
                fully_missing_list.append(run)
            elif mysql_count < run.record_count:
                partially_missing_list.append(run)
            else:
                already_reconciled_list.append(run)

        # Danh sách các run thực sự còn thiếu
        missing_runs = partially_missing_list + fully_missing_list
        batch = missing_runs[:batch_limit]

        audit_meta = {
            "runs_discovered": len(discovered_runs),
            "runs_selected": len(batch),
            "already_reconciled": len(already_reconciled_list),
            "partially_missing": len(partially_missing_list),
            "fully_missing": len(fully_missing_list),
            "not_inspected_yet": 0,
            "total_real_backlog": len(missing_runs),
        }

        logger.info(
            "Audit Bronze: %d discovered | %d reconciled | %d partially missing | %d fully missing | Selected %d for batch",
            audit_meta["runs_discovered"],
            audit_meta["already_reconciled"],
            audit_meta["partially_missing"],
            audit_meta["fully_missing"],
            audit_meta["runs_selected"],
        )
        return batch, audit_meta

    @classmethod
    def identify_missing_runs(
        cls,
        discovered_runs: list[BronzeRunInfo],
        batch_limit: int = 25,
        engine=None,
    ) -> tuple[list[BronzeRunInfo], int, int]:
        batch, meta = cls.audit_and_identify_missing_runs(discovered_runs, batch_limit, engine)
        return batch, meta["total_real_backlog"], meta["already_reconciled"]

    @classmethod
    def reconcile_single_run(cls, run_info: BronzeRunInfo, engine=None) -> dict:
        """Nạp một Bronze run vào MySQL sử dụng PersistBronzeObservationsUseCase (Idempotent)."""
        logger.info("Bắt đầu reconcile run %s (%s)...", run_info.run_id, run_info.source)
        observations = BronzeObservationLoader.load_from_bronze_dir(run_info.run_path, run_id=run_info.run_id)
        if not observations:
            logger.info("Run %s không có observations hợp lệ -> Bỏ qua.", run_info.run_id)
            return {
                "source": run_info.source,
                "run_id": run_info.run_id,
                "observations_scanned": 0,
                "observations_inserted": 0,
                "technical_duplicates": 0,
                "posts_created": 0,
                "posts_existing": 0,
                "status": "SKIPPED_EMPTY",
            }

        tx_mgr = MySQLTransactionManager(engine=engine)
        use_case = PersistBronzeObservationsUseCase(
            platform_repo=MySQLPlatformRepository(connection=None),
            rental_post_repo=MySQLRentalPostRepository(connection=None),
            observation_repo=MySQLObservationRepository(connection=None),
            children_repo=MySQLPostChildrenRepository(connection=None),
            transaction_mgr=tx_mgr,
        )

        import_res = use_case.execute(observations)
        logger.info(
            "Reconciled run %s: %d inserted, %d duplicate, %d posts new, %d posts exist",
            run_info.run_id,
            import_res.observations_inserted,
            import_res.technical_duplicates,
            import_res.posts_created,
            import_res.posts_existing,
        )
        return {
            "source": run_info.source,
            "run_id": run_info.run_id,
            "observations_scanned": len(observations),
            "observations_inserted": import_res.observations_inserted,
            "technical_duplicates": import_res.technical_duplicates,
            "posts_created": import_res.posts_created,
            "posts_existing": import_res.posts_existing,
            "status": "SUCCESS",
        }

    @classmethod
    def load_checkpoint(cls, path: str | Path = "/data/state/bronze_reconciler.json") -> dict:
        p = Path(path)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Không thể đọc checkpoint tại %s: %s", p, e)
        return {}

    @classmethod
    def save_checkpoint(cls, state: dict, path: str | Path = "/data/state/bronze_reconciler.json") -> None:
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Không thể ghi checkpoint tại %s: %s", p, e)
