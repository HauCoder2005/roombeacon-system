from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum


class UrlSafetyStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"


class RobotsQualificationStatus(str, Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class AdapterStatus(str, Enum):
    REGISTERED = "REGISTERED"
    NOT_REGISTERED = "NOT_REGISTERED"


class QualificationOverallStatus(str, Enum):
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
    reason: str | None = None
    checked_at: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Enum):
                data[key] = value.value
        return data

    def format_human_readable(self) -> str:
        lines = [
            "Source Qualification",
            "-" * 50,
            f"Target URL : {self.target_url}",
            f"Hostname   : {self.hostname}",
            f"Robots URL : {self.robots_url}",
            f"URL Safety : {self.url_status.value}",
            f"Robots     : {self.robots_status.value}",
            f"Adapter    : {self.adapter_status.value}" + (f" ({self.source_name})" if self.source_name else ""),
            f"Overall    : {self.overall_status.value}",
        ]
        if self.reason:
            lines.append(f"Reason     : {self.reason}")
        return "\n".join(lines)
