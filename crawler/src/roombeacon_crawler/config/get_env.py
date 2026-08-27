from dataclasses import dataclass
from threading import RLock
from typing import Any

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


_environment: Environment | None = None
_environment_lock = RLock()


def get_environment() -> Environment:
    """Load configuration lazily on first runtime access."""
    global _environment
    if _environment is None:
        with _environment_lock:
            if _environment is None:
                _environment = load_environment()
    return _environment


def configure_environment(environment: Environment) -> None:
    """Inject an explicit environment, primarily for isolated tests."""
    global _environment
    with _environment_lock:
        _environment = environment


def reset_environment() -> None:
    """Clear the lazy environment cache without reading runtime configuration."""
    global _environment
    with _environment_lock:
        _environment = None


def bootstrap_runtime_environment(*, load_dotenv_file: bool = False) -> Environment:
    """Explicit runtime bootstrap; optionally load local dotenv before config."""
    if load_dotenv_file:
        from roombeacon_crawler.config.env.loader import load_runtime_dotenv

        load_runtime_dotenv()
    reset_environment()
    return get_environment()


class _LazyEnvironment:
    """Compatibility proxy: importing `env` does not load configuration."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_environment(), name)

    def __repr__(self) -> str:
        return "<LazyEnvironment unloaded>" if _environment is None else repr(_environment)


env = _LazyEnvironment()

__all__ = [
    "Environment",
    "bootstrap_runtime_environment",
    "configure_environment",
    "env",
    "get_environment",
    "load_environment",
    "reset_environment",
]
