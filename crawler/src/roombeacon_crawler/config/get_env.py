from dataclasses import dataclass

from roombeacon_crawler.config.env.airflow import AirflowEnv, load_airflow_env
from roombeacon_crawler.config.env.clickhouse import (
    ClickHouseEnv,
    load_clickhouse_env,
)
from roombeacon_crawler.config.env.crawler import CrawlerEnv, load_crawler_env
from roombeacon_crawler.config.env.minio import MinIOEnv, load_minio_env
from roombeacon_crawler.config.env.mysql import (
    BronzeMySQLEnv,
    load_bronze_mysql_env,
)
from roombeacon_crawler.config.env.processing import (
    DuckDBEnv,
    PipelineEnv,
    ProcessingEnv,
    load_duckdb_env,
    load_pipeline_env,
    load_processing_env,
)
from roombeacon_crawler.config.env.project import ProjectEnv, load_project_env
from roombeacon_crawler.config.env.security import (
    SecurityEnv,
    load_security_env,
)
from roombeacon_crawler.config.env.serving import BackendEnv, load_backend_env


@dataclass(frozen=True, slots=True)
class Environment:
    """Tập hợp cấu hình toàn bộ các domain của RoomBeacon."""

    project: ProjectEnv
    crawler: CrawlerEnv
    mysql_bronze: BronzeMySQLEnv
    minio: MinIOEnv
    duckdb: DuckDBEnv
    processing: ProcessingEnv
    pipeline: PipelineEnv
    clickhouse: ClickHouseEnv
    backend: BackendEnv
    security: SecurityEnv
    airflow: AirflowEnv


def load_environment() -> Environment:
    """Nạp và trả về đối tượng cấu hình trung tâm của toàn bộ ứng dụng."""
    return Environment(
        project=load_project_env(),
        crawler=load_crawler_env(),
        mysql_bronze=load_bronze_mysql_env(),
        minio=load_minio_env(),
        duckdb=load_duckdb_env(),
        processing=load_processing_env(),
        pipeline=load_pipeline_env(),
        clickhouse=load_clickhouse_env(),
        backend=load_backend_env(),
        security=load_security_env(),
        airflow=load_airflow_env(),
    )


# Singleton configuration instance for application runtime
env: Environment = load_environment()

__all__ = [
    "Environment",
    "env",
    "load_environment",
]
