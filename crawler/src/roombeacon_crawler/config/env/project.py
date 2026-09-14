from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_str


@dataclass(frozen=True, slots=True)
class ProjectEnv:
    project_name: str
    environment: str


def load_project_env() -> ProjectEnv:
    return ProjectEnv(
        project_name=get_str("ROOMBEACON_PROJECT_NAME", default="roombeacon") or "roombeacon",
        environment=get_str("ROOMBEACON_ENV", default="development") or "development",
    )
