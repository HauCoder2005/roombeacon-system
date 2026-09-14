from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_str


@dataclass(frozen=True, slots=True)
class SecurityEnv:
    secret_key: str


def load_security_env() -> SecurityEnv:
    return SecurityEnv(
        secret_key=get_str("SECRET_KEY", default="") or "",
    )
