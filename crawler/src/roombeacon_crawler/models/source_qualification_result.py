from dataclasses import asdict, dataclass
from enum import Enum


class UrlSafetyStatus(str, Enum):
    """Outcome of validating the target URL before network access."""
    VALID = "VALID"
    INVALID = "INVALID"


class RobotsQualificationStatus(str, Enum):
    """Outcome of the source robots-policy preflight."""
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    UNAVAILABLE = "UNAVAILABLE"
    UNREACHABLE = "UNREACHABLE"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class AdapterStatus(str, Enum):
    """Whether an installed source adapter can process the target."""
    REGISTERED = "REGISTERED"
    NOT_REGISTERED = "NOT_REGISTERED"


class QualificationOverallStatus(str, Enum):
    """Combined decision exposed to crawl orchestration."""
    READY = "READY"
    CANDIDATE_FOR_ADAPTER = "CANDIDATE_FOR_ADAPTER"
    DENIED_BY_ROBOTS = "DENIED_BY_ROBOTS"
    INVALID_URL = "INVALID_URL"
    CHECK_FAILED = "CHECK_FAILED"


@dataclass
class SourceQualificationResult:
    """Kết quả đánh giá và thẩm định độ phù hợp của một URL nguồn ứng viên."""

    target_url: str
    hostname: str
    robots_url: str
    url_status: UrlSafetyStatus
    robots_status: RobotsQualificationStatus
    adapter_status: AdapterStatus
    overall_status: QualificationOverallStatus
    source_name: str | None = None
    access_profile: str | None = None
    capabilities: dict | None = None
    reason: str | None = None
    failure_reason: str | None = None
    http_status: int | None = None
    checked_at: str = ""

    def to_dict(self) -> dict:
        """Serialize qualification output for Airflow XCom."""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Enum):
                data[key] = value.value
        return data

    def format_human_readable(self) -> str:
        """Render a concise operator-facing qualification report."""
        lines = [
            "Source Qualification",
            "-" * 50,
            f"Target URL : {self.target_url}",
            f"Hostname   : {self.hostname}",
            f"Robots URL : {self.robots_url}",
            f"URL Safety : {self.url_status.value}",
            f"Robots     : {self.robots_status.value}",
            f"Adapter    : {self.adapter_status.value}" + (f" ({self.source_name})" if self.source_name else ""),
            f"Access Profile: {self.access_profile or 'STANDARD_PAGINATION'}",
            f"Overall    : {self.overall_status.value}",
        ]
        if self.reason:
            lines.append(f"Reason     : {self.reason}")
        return "\n".join(lines)
