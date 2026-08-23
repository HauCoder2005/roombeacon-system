from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum


class DiscoveryType(str, Enum):
    """Loại hình khám phá URL mục tiêu."""

    SITEMAP_INDEX = "sitemap_index"
    SITEMAP_URLSET = "sitemap_urlset"
    FEED = "feed"
    API = "api"
    MANUAL = "manual"


class DiscoveryStatus(str, Enum):
    """Trạng thái hoàn thành của tiến trình khám phá URL."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    EMPTY = "empty"
    ROBOTS_DENIED = "robots_denied"
    ACCESS_CHALLENGE = "access_challenge"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DiscoveredUrl:
    """Mô hình dữ liệu đại diện cho một URL ứng viên được khám phá từ sitemap/feed."""

    source: str
    url: str
    discovered_from: str
    discovery_type: DiscoveryType = DiscoveryType.SITEMAP_URLSET
    lastmod: str | None = None
    target_hint: str | None = None
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "url": self.url,
            "discovered_from": self.discovered_from,
            "discovery_type": (
                self.discovery_type.value
                if isinstance(self.discovery_type, DiscoveryType)
                else str(self.discovery_type)
            ),
            "lastmod": self.lastmod,
            "target_hint": self.target_hint,
            "discovered_at": self.discovered_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveredUrl":
        disc_type = data.get("discovery_type", DiscoveryType.SITEMAP_URLSET)
        if isinstance(disc_type, str):
            try:
                disc_type = DiscoveryType(disc_type)
            except ValueError:
                disc_type = DiscoveryType.SITEMAP_URLSET

        return cls(
            source=data["source"],
            url=data["url"],
            discovered_from=data.get("discovered_from", ""),
            discovery_type=disc_type,
            lastmod=data.get("lastmod"),
            target_hint=data.get("target_hint"),
            discovered_at=data.get(
                "discovered_at", datetime.now(timezone.utc).isoformat()
            ),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryArtifact:
    """Mô hình lưu trữ artifact danh sách URL khám phá tại /data/discovery/<source>/<run_id>/."""

    source: str
    run_id: str
    discovered_at: str
    count: int
    urls: list[dict]
    artifact_path: str

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "run_id": self.run_id,
            "discovered_at": self.discovered_at,
            "count": self.count,
            "urls": self.urls,
            "artifact_path": self.artifact_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveryArtifact":
        return cls(
            source=data["source"],
            run_id=data["run_id"],
            discovered_at=data.get(
                "discovered_at", datetime.now(timezone.utc).isoformat()
            ),
            count=data.get("count", len(data.get("urls", []))),
            urls=data.get("urls", []),
            artifact_path=data.get("artifact_path", ""),
        )


@dataclass(slots=True)
class DiscoveryResult:
    """Kết quả tóm tắt trả về từ SitemapDiscoveryEngine (Lightweight metadata cho Airflow XCom)."""

    source: str
    run_id: str
    status: DiscoveryStatus
    discovered_at: str
    count: int
    new_count: int = 0
    changed_count: int = 0
    artifact_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "run_id": self.run_id,
            "status": (
                self.status.value
                if isinstance(self.status, DiscoveryStatus)
                else str(self.status)
            ),
            "discovered_at": self.discovered_at,
            "count": self.count,
            "new_count": self.new_count,
            "changed_count": self.changed_count,
            "artifact_path": self.artifact_path,
            "error": self.error,
        }


@dataclass(slots=True)
class DiscoveryTargetState:
    """Trạng thái lưu vết checkpoint của tiến trình khám phá URL cho từng nguồn lớn."""

    source: str
    last_discovery_at: str | None = None
    last_discovery_status: str | None = None
    last_discovered_count: int = 0
    last_new_count: int = 0
    last_changed_count: int = 0
    last_sitemap_lastmod: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "last_discovery_at": self.last_discovery_at,
            "last_discovery_status": self.last_discovery_status,
            "last_discovered_count": self.last_discovered_count,
            "last_new_count": self.last_new_count,
            "last_changed_count": self.last_changed_count,
            "last_sitemap_lastmod": self.last_sitemap_lastmod,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveryTargetState":
        return cls(
            source=data["source"],
            last_discovery_at=data.get("last_discovery_at"),
            last_discovery_status=data.get("last_discovery_status"),
            last_discovered_count=data.get("last_discovered_count", 0),
            last_new_count=data.get("last_new_count", 0),
            last_changed_count=data.get("last_changed_count", 0),
            last_sitemap_lastmod=data.get("last_sitemap_lastmod"),
            last_error=data.get("last_error"),
        )
