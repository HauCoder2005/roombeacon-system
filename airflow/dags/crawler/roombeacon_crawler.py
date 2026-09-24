"""Define the scheduled crawler DAG as a thin Airflow orchestration layer.

Task wrappers delegate business behavior to Airflow-free application workflows
and translate only the final scheduler failure boundary.
"""

from datetime import datetime, timedelta, timezone
import logging

from airflow.exceptions import AirflowException
from airflow.sdk import Param, dag, task
from airflow.task.trigger_rule import TriggerRule

from roombeacon_crawler.application.orchestration import crawler_workflow as workflow
from roombeacon_crawler.application.orchestration import checkpoint as checkpoint_workflow
from roombeacon_crawler.application.orchestration import planning as planning_workflow
from roombeacon_crawler.application.orchestration import qualification as qualification_workflow

logger = logging.getLogger(__name__)

# Backward-compatible test seams. Task wrappers synchronize these aliases into
# the Airflow-free workflow module immediately before execution.
LocalCrawlStateRepository = checkpoint_workflow.LocalCrawlStateRepository
LocalSourceHealthRepository = checkpoint_workflow.LocalSourceHealthRepository
RobotsPolicy = qualification_workflow.RobotsPolicy
URLValidator = qualification_workflow.URLValidator


def _sync_runtime_seams() -> None:
    """Synchronize backward-compatible patch seams used by DAG regression tests."""
    planning_workflow.LocalCrawlStateRepository = LocalCrawlStateRepository
    checkpoint_workflow.LocalCrawlStateRepository = LocalCrawlStateRepository
    checkpoint_workflow.LocalSourceHealthRepository = LocalSourceHealthRepository
    qualification_workflow.LocalSourceHealthRepository = LocalSourceHealthRepository
    qualification_workflow.RobotsPolicy = RobotsPolicy
    qualification_workflow.URLValidator = URLValidator


def _translate_failure(operation: str, callback, *args, **kwargs):
    """Invoke an application workflow and translate its safe error to Airflow."""
    _sync_runtime_seams()
    try:
        return callback(*args, **kwargs)
    except workflow.CrawlerWorkflowError as exc:
        logger.error(
            "Crawler workflow failed (operation=%s, error_class=%s)",
            operation,
            type(exc).__name__,
        )
        raise AirflowException(str(exc)) from exc


@task(task_id="01_config_load_sources")
def load_crawl_targets() -> list[dict]:
    """Load scheduled source targets through the application workflow."""
    return _translate_failure("load_crawl_targets", workflow.load_crawl_targets)


@task(task_id="02_config_plan_crawls")
def plan_crawls(targets: list[dict], **context) -> list[dict]:
    """Create crawl plans for due targets without embedding planning rules."""
    return _translate_failure("plan_crawls", workflow.plan_crawls, targets, **context)


@task(task_id="03_crawl_check_eligibility")
def qualify_target(plan: dict, **context) -> dict:
    """Evaluate URL and robots eligibility for one mapped crawl plan."""
    return _translate_failure("qualify_target", workflow.qualify_target, plan, **context)


@task(task_id="04_crawl_execute_source", execution_timeout=timedelta(minutes=180))
def execute_crawl(qual_payload: dict, **context) -> dict:
    """Execute one qualified crawl through the application boundary."""
    return _translate_failure("execute_crawl", workflow.execute_crawl, qual_payload, **context)


@task(task_id="05_storage_save_bronze")
def persist_bronze_mysql(result_payload: dict, **context) -> dict:
    """Persist a successful crawl artifact through the application use case."""
    return _translate_failure(
        "persist_bronze_mysql", workflow.persist_bronze_mysql, result_payload, **context
    )


@task(task_id="06_state_update_checkpoint")
def update_checkpoint(
    persist_payload: dict = None,
    result_payload: dict = None,
    **context,
) -> dict:
    """Update checkpoint and source health after persistence completes."""
    return _translate_failure(
        "update_checkpoint",
        workflow.update_checkpoint,
        persist_payload,
        result_payload,
        **context,
    )


@task(
    task_id="07_analytics_refresh_duckdb",
    trigger_rule=TriggerRule.ALL_DONE,
    pool="duckdb_analytics_pool",
)
def refresh_duckdb_analytics(checkpoints: list[dict], **context) -> dict:
    """Refresh analytics after all mapped checkpoint tasks have finished."""
    return _translate_failure(
        "refresh_duckdb_analytics",
        workflow.refresh_duckdb_analytics,
        checkpoints,
        **context,
    )


@task(task_id="08_assets_sync_minio", trigger_rule=TriggerRule.ALL_DONE)
def sync_assets_minio(analytics_summary: dict = None, **context) -> dict:
    """Reconcile one bounded image batch after the analytics stage finishes."""
    return _translate_failure("sync_assets_minio", workflow.sync_assets_minio)


@task(task_id="09_report_run_summary", trigger_rule=TriggerRule.ALL_DONE)
def summarize_run(
    plans: list[dict] = None,
    qualifications: list[dict] = None,
    crawl_results: list[dict] = None,
    persistence_results: list[dict] = None,
    checkpoints: list[dict] = None,
    analytics_summary: dict = None,
    asset_summary: dict = None,
    **context,
) -> dict:
    """Aggregate outcomes while keeping the DAG edge into reporting linear."""
    task_instance = context.get("ti") or context.get("task_instance")
    if task_instance is not None:
        # Pulling completed stage outputs here avoids six decorative XComArg
        # edges into the report node. Application reporting receives the same
        # payloads and the graph remains the operator-facing linear workflow.
        plans = plans if plans is not None else task_instance.xcom_pull(
            task_ids="02_config_plan_crawls"
        )
        qualifications = qualifications if qualifications is not None else task_instance.xcom_pull(
            task_ids=["03_crawl_check_eligibility"]
        )
        crawl_results = crawl_results if crawl_results is not None else task_instance.xcom_pull(
            task_ids=["04_crawl_execute_source"]
        )
        persistence_results = persistence_results if persistence_results is not None else task_instance.xcom_pull(
            task_ids=["05_storage_save_bronze"]
        )
        checkpoints = checkpoints if checkpoints is not None else task_instance.xcom_pull(
            task_ids=["06_state_update_checkpoint"]
        )
        analytics_summary = (
            analytics_summary
            if analytics_summary is not None
            else task_instance.xcom_pull(task_ids="07_analytics_refresh_duckdb")
        )
    return _translate_failure(
        "summarize_run",
        workflow.summarize_run,
        plans,
        qualifications,
        crawl_results,
        persistence_results,
        checkpoints,
        analytics_summary,
        asset_summary,
        **context,
    )


@dag(
    dag_id="roombeacon_crawler",
    schedule="*/5 * * * *",
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
    """Build the mapped crawler task graph with persistence before checkpoint."""
    targets = load_crawl_targets()
    plans = plan_crawls(targets)
    qualifications = qualify_target.expand(plan=plans)
    crawl_results = execute_crawl.expand(qual_payload=qualifications)
    persistence_results = persist_bronze_mysql.expand(result_payload=crawl_results)
    checkpoints = update_checkpoint.expand(persist_payload=persistence_results)
    analytics_summary = refresh_duckdb_analytics(checkpoints=checkpoints)
    asset_summary = sync_assets_minio(analytics_summary=analytics_summary)
    summarize_run(asset_summary=asset_summary)


roombeacon_crawler_dag = roombeacon_crawler()
