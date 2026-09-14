from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_int, get_str


@dataclass(frozen=True, slots=True)
class BackendEnv:
    host: str
    port: int


def load_backend_env() -> BackendEnv:
    return BackendEnv(
        host=get_str("BACKEND_HOST", default="0.0.0.0") or "0.0.0.0",
        port=get_int("BACKEND_PORT", default=8000) or 8000,
    )
