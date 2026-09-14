from dataclasses import dataclass
from typing import Optional
from roombeacon_crawler.config.env.loader import get_optional_str


@dataclass(frozen=True, slots=True)
class AirflowEnv:
    jwt_secret: Optional[str] = None
    fernet_key: Optional[str] = None

    def __repr__(self) -> str:
        jwt_masked = "***" if self.jwt_secret else "None"
        fernet_masked = "***" if self.fernet_key else "None"
        return f"AirflowEnv(jwt_secret={jwt_masked}, fernet_key={fernet_masked})"


def load_airflow_env() -> AirflowEnv:
    return AirflowEnv(
        jwt_secret=get_optional_str("AIRFLOW__API_AUTH__JWT_SECRET"),
        fernet_key=get_optional_str("AIRFLOW__CORE__FERNET_KEY"),
    )
