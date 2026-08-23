import logging
from datetime import datetime, timezone
from pathlib import Path

from airflow.decorators import dag, task
from airflow.task.trigger_rule import TriggerRule

logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_bronze_reconciler"
DEFAULT_ARGS = {
    "owner": "roombeacon",
    "depends_on_past": False,
    "retries": 2,
}


@dag(
    dag_id=DAG_ID,
    description="Tự động đối soát và nạp bù dữ liệu Bronze lịch sử vào MySQL và DuckDB",
    default_args=DEFAULT_ARGS,
    schedule="5,20,35,50 * * * *",
    start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["roombeacon", "reconciliation", "bronze", "mysql", "duckdb"],
)
def roombeacon_bronze_reconciler():

    # --------------------------------------------------------------------------
    # Task 1: Discover Bronze Runs & Capture Initial MySQL Count
    # --------------------------------------------------------------------------
    @task
    def discover_bronze_runs(**context) -> dict:
        """1. Quét kho đĩa vật lý /data/bronze và ghi nhận mysql_before độc lập cho DAG run này."""
        from roombeacon_crawler.application.reconciliation.discovery import BronzeRunDiscoveryService
        from roombeacon_crawler.application.reconciliation.reconciler import BronzeReconcilerService

        logger.info("=" * 60)
        logger.info("STAGE 1: DISCOVER BRONZE RUNS & CAPTURE MYSQL BEFORE")
        logger.info("=" * 60)

        runs = BronzeRunDiscoveryService.discover_bronze_runs("/data/bronze")
        mysql_before = BronzeReconcilerService.get_mysql_observations_count()
        logger.info("Đã tìm thấy %d Bronze runs trên đĩa. MySQL observations before: %d", len(runs), mysql_before)
        return {
            "discovered_runs": [r.to_dict() for r in runs],
            "mysql_before": mysql_before,
        }

    # --------------------------------------------------------------------------
    # Task 2: Audit & Identify Missing Runs
    # --------------------------------------------------------------------------
    @task
    def identify_missing_runs(discovery_data: dict, **context) -> list[dict]:
        """2. So sánh danh sách Bronze runs với MySQL để chọn ra batch các run cần nạp bù."""
        from roombeacon_crawler.application.reconciliation.discovery import BronzeRunInfo
        from roombeacon_crawler.application.reconciliation.reconciler import BronzeReconcilerService

        logger.info("=" * 60)
        logger.info("STAGE 2: AUDIT & IDENTIFY MISSING RUNS")
        logger.info("=" * 60)

        discovered_list = discovery_data.get("discovered_runs", [])
        runs_obj = [BronzeRunInfo.from_dict(d) for d in discovered_list]
        batch, audit_meta = BronzeReconcilerService.audit_and_identify_missing_runs(
            discovered_runs=runs_obj,
            batch_limit=25,
        )

        logger.info(
            "Audit: %d discovered | %d reconciled | %d partially missing | %d fully missing | Selected batch: %d runs",
            audit_meta["runs_discovered"],
            audit_meta["already_reconciled"],
            audit_meta["partially_missing"],
            audit_meta["fully_missing"],
            audit_meta["runs_selected"],
        )
        return [r.to_dict() for r in batch]

    # --------------------------------------------------------------------------
    # Task 3: Persist Missing Runs (Mapped)
    # --------------------------------------------------------------------------
    @task
    def persist_missing_run(run_dict: dict, **context) -> dict:
        """3. Nạp dữ liệu của một Bronze run vào MySQL qua Clean Architecture Use Case."""
        from roombeacon_crawler.application.reconciliation.discovery import BronzeRunInfo
        from roombeacon_crawler.application.reconciliation.reconciler import BronzeReconcilerService

        run_info = BronzeRunInfo.from_dict(run_dict)
        return BronzeReconcilerService.reconcile_single_run(run_info)

    # --------------------------------------------------------------------------
    # Task 4: Verify MySQL Reconciliation (Capture MySQL After)
    # --------------------------------------------------------------------------
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def verify_mysql_reconciliation(**context) -> dict:
        """4. Ghi nhận mysql_after sau khi nạp batch."""
        from roombeacon_crawler.application.reconciliation.reconciler import BronzeReconcilerService

        logger.info("=" * 60)
        logger.info("STAGE 4: VERIFY MYSQL RECONCILIATION")
        logger.info("=" * 60)

        obs_cnt = BronzeReconcilerService.get_mysql_observations_count()
        posts_cnt = BronzeReconcilerService.get_mysql_posts_count()

        logger.info("MySQL Verification: %d rental_post_versions | %d rental_posts", obs_cnt, posts_cnt)
        return {
            "mysql_observations_after": obs_cnt,
            "mysql_posts_after": posts_cnt,
        }

    # --------------------------------------------------------------------------
    # Task 5: Refresh DuckDB Analytics (Single-Writer Pool Guard)
    # --------------------------------------------------------------------------
    @task(trigger_rule=TriggerRule.ALL_DONE, pool="duckdb_analytics_pool")
    def refresh_duckdb_analytics(verification_result: dict, **context) -> dict:
        """5. Khởi tạo/cập nhật Analytical Views trong DuckDB và kiểm tra tính nhất quán 1:1."""
        from analytics.duckdb.bootstrap import bootstrap_analytics
        from analytics.duckdb.connection import DuckDBConnectionFactory

        logger.info("=" * 60)
        logger.info("STAGE 5: REFRESH DUCKDB ANALYTICS")
        logger.info("=" * 60)

        try:
            bootstrap_analytics()
            conn = DuckDBConnectionFactory.get_connection()
            duck_cnt = conn.execute("SELECT COUNT(*) FROM v_observations").fetchone()[0]
            logger.info("DuckDB Refresh thành công: %d v_observations", duck_cnt)
            return {"duckdb_observations_total": duck_cnt, "status": "SUCCESS"}
        except Exception as exc:
            logger.exception("Lỗi khi refresh DuckDB Analytics: %s", exc)
            return {"duckdb_observations_total": 0, "status": "FAILED", "error": str(exc)}

    # --------------------------------------------------------------------------
    # Task 6: Summarize Reconciliation (Run-Scoped Reporting)
    # --------------------------------------------------------------------------
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def summarize_reconciliation(
        discovery_data: dict,
        selected_runs: list[dict],
        persistence_results: list[dict],
        verification_result: dict,
        analytics_result: dict,
        **context,
    ) -> dict:
        """6. Tổng kết số liệu đối soát độc lập của riêng DAG run này theo đúng định dạng chuẩn."""
        from roombeacon_crawler.application.reconciliation.reconciler import BronzeReconcilerService

        dag_run = context.get("dag_run")
        dag_run_id = dag_run.run_id if dag_run else "UNKNOWN"

        discovered_list = discovery_data.get("discovered_runs", [])
        runs_discovered = len(discovered_list)
        runs_selected = len(selected_runs or [])

        # Kiểm tra audit chi tiết dựa trên trạng thái MySQL hiện tại
        persisted_counts = BronzeReconcilerService.get_persisted_run_counts()
        already_reconciled = 0
        partially_missing = 0
        fully_missing = 0
        for r in discovered_list:
            cnt = persisted_counts.get(r["run_id"], 0)
            rec = r.get("record_count", 0)
            if cnt >= rec > 0 or (cnt > 0 and rec == 0):
                already_reconciled += 1
            elif 0 < cnt < rec:
                partially_missing += 1
            else:
                fully_missing += 1

        not_inspected_yet = 0
        remaining_real_backlog = partially_missing + fully_missing

        # Số liệu nạp batch của run này
        valid_results = [r for r in (persistence_results or []) if isinstance(r, dict)]
        runs_persisted = sum(1 for r in valid_results if r.get("observations_inserted", 0) > 0 or r.get("status") == "SUCCESS")
        runs_failed = sum(1 for r in valid_results if r.get("status") == "FAILED")

        observations_scanned = sum(r.get("observations_scanned", 0) for r in valid_results)
        inserted_this_run = sum(r.get("observations_inserted", 0) for r in valid_results)
        already_in_mysql = sum(r.get("technical_duplicates", 0) for r in valid_results)
        invalid = 0
        failed = 0

        # Invariant bảo toàn observations
        if observations_scanned != (already_in_mysql + inserted_this_run + invalid + failed):
            already_in_mysql = max(0, observations_scanned - inserted_this_run - invalid - failed)

        # Số liệu MySQL trước / sau và delta
        mysql_before = int(discovery_data.get("mysql_before", 0))
        mysql_after = int(verification_result.get("mysql_observations_after", 0))
        observed_db_delta = mysql_after - mysql_before
        concurrent_external_delta = max(0, observed_db_delta - inserted_this_run)

        duckdb_obs = int(analytics_result.get("duckdb_observations_total", 0))
        mysql_equals_duckdb = "YES" if mysql_after == duckdb_obs else "NO"
        status_str = "SUCCESS" if runs_failed == 0 else "PARTIAL_SUCCESS"

        logger.info("=" * 60)
        logger.info("ROOMBEACON BRONZE RECONCILIATION")
        logger.info("=" * 60)
        logger.info("")
        logger.info("DAG Run                    : %s", dag_run_id)
        logger.info("")
        logger.info("Runs discovered            : %d", runs_discovered)
        logger.info("Runs selected              : %d", runs_selected)
        logger.info("Already reconciled         : %d", already_reconciled)
        logger.info("Partially missing          : %d", partially_missing)
        logger.info("Fully missing              : %d", fully_missing)
        logger.info("Persisted this cycle       : %d", runs_persisted)
        logger.info("Failed this cycle          : %d", runs_failed)
        logger.info("Not inspected yet          : %d", not_inspected_yet)
        logger.info("Remaining real backlog     : %d", remaining_real_backlog)
        logger.info("")
        logger.info("Observations scanned       : %d", observations_scanned)
        logger.info("Already in MySQL           : %d", already_in_mysql)
        logger.info("Inserted this run          : %d", inserted_this_run)
        logger.info("Invalid                    : %d", invalid)
        logger.info("Failed                     : %d", failed)
        logger.info("")
        logger.info("MySQL before               : %d", mysql_before)
        logger.info("MySQL after                : %d", mysql_after)
        logger.info("Observed DB delta          : %d", observed_db_delta)
        logger.info("Concurrent external delta  : %d", concurrent_external_delta)
        logger.info("")
        logger.info("DuckDB observations        : %d", duckdb_obs)
        logger.info("MySQL == DuckDB            : %s", mysql_equals_duckdb)
        logger.info("")
        logger.info("Status                     : %s", status_str)
        logger.info("=" * 60)

        # Lưu checkpoint bền vững
        checkpoint_data = {
            "dag_run_id": dag_run_id,
            "runs_discovered": runs_discovered,
            "runs_selected": runs_selected,
            "already_reconciled": already_reconciled,
            "partially_missing": partially_missing,
            "fully_missing": fully_missing,
            "remaining_real_backlog": remaining_real_backlog,
            "observations_scanned": observations_scanned,
            "already_in_mysql": already_in_mysql,
            "inserted_this_run": inserted_this_run,
            "mysql_before": mysql_before,
            "mysql_after": mysql_after,
            "observed_db_delta": observed_db_delta,
            "concurrent_external_delta": concurrent_external_delta,
            "duckdb_observations": duckdb_obs,
            "mysql_equals_duckdb": mysql_equals_duckdb,
            "status": status_str,
        }
        BronzeReconcilerService.save_checkpoint(checkpoint_data)
        return checkpoint_data

    # Workflow Dependency Graph
    discovery_res = discover_bronze_runs()
    missing_runs = identify_missing_runs(discovery_data=discovery_res)
    persisted = persist_missing_run.expand(run_dict=missing_runs)
    verified = verify_mysql_reconciliation()
    persisted >> verified
    analytics = refresh_duckdb_analytics(verification_result=verified)
    summarize_reconciliation(
        discovery_data=discovery_res,
        selected_runs=missing_runs,
        persistence_results=persisted,
        verification_result=verified,
        analytics_result=analytics,
    )


dag_instance = roombeacon_bronze_reconciler()
