from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_int, get_str


@dataclass(frozen=True, slots=True)
class ClickHouseEnv:
    host: str
    http_port: int
    native_port: int
    user: str
    password: str
    database: str


def load_clickhouse_env() -> ClickHouseEnv:
    return ClickHouseEnv(
        host=get_str("CLICKHOUSE_HOST", default="clickhouse") or "clickhouse",
        http_port=get_int("CLICKHOUSE_HTTP_PORT", default=8123) or 8123,
        native_port=get_int("CLICKHOUSE_NATIVE_PORT", default=9000) or 9000,
        user=get_str("CLICKHOUSE_USER", default="default") or "default",
        password=get_str("CLICKHOUSE_PASSWORD", default="") or "",
        database=get_str("CLICKHOUSE_DATABASE", default="roombeacon_analytics") or "roombeacon_analytics",
    )
