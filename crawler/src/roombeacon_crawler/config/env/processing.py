from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_int, get_str


@dataclass(frozen=True, slots=True)
class DuckDBEnv:
    database: str
    temp_directory: str
    memory_limit: str
    threads: int


@dataclass(frozen=True, slots=True)
class ProcessingEnv:
    silver_dir: str


@dataclass(frozen=True, slots=True)
class PipelineEnv:
    raw_dir: str
    bronze_dir: str
    silver_dir: str
    gold_dir: str


def load_duckdb_env() -> DuckDBEnv:
    return DuckDBEnv(
        database=get_str("DUCKDB_DATABASE", default="data/duckdb/roombeacon_analytics.duckdb") or "data/duckdb/roombeacon_analytics.duckdb",
        temp_directory=get_str("DUCKDB_TEMP_DIRECTORY", default="data/duckdb/tmp") or "data/duckdb/tmp",
        memory_limit=get_str("DUCKDB_MEMORY_LIMIT", default="2GB") or "2GB",
        threads=get_int("DUCKDB_THREADS", default=4) or 4,
    )


def load_processing_env() -> ProcessingEnv:
    return ProcessingEnv(
        silver_dir=get_str("PROCESSING_SILVER_DIR", default="data/silver") or "data/silver",
    )


def load_pipeline_env() -> PipelineEnv:
    return PipelineEnv(
        raw_dir=get_str("RAW_DATA_DIR", default="data/raw") or "data/raw",
        bronze_dir=get_str("BRONZE_DATA_DIR", default="data/bronze") or "data/bronze",
        silver_dir=get_str("SILVER_DATA_DIR", default="data/silver") or "data/silver",
        gold_dir=get_str("GOLD_DATA_DIR", default="data/gold") or "data/gold",
    )
