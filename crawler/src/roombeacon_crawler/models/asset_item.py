from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib


class AssetStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    SKIPPED = "SKIPPED"


class AssetErrorCategory(str, Enum):
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    HTTP_CLIENT_ERROR = "HTTP_CLIENT_ERROR"
    INVALID_CONTENT_TYPE = "INVALID_CONTENT_TYPE"
    HTML_CHALLENGE = "HTML_CHALLENGE"
    INVALID_MAGIC_BYTES = "INVALID_MAGIC_BYTES"
    UPLOAD_ERROR = "UPLOAD_ERROR"
    INVALID_DATA_URL = "INVALID_DATA_URL"


@dataclass
class AssetItem:
    """Đại diện cho một tài nguyên hình ảnh được quản lý bởi Asset Pipeline."""

    asset_id: str
    source: str
    platform_post_id: str
    rental_post_id: int
    image_url: str
    position: int
    object_key: str
    status: AssetStatus = AssetStatus.PENDING
    attempt_count: int = 0
    max_retries: int = 3
    last_attempt_at: str | None = None
    last_error_category: AssetErrorCategory = AssetErrorCategory.NONE
    last_error_message: str | None = None
    content_type: str | None = None
    size_bytes: int = 0
    etag: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def generate_asset_id(cls, source: str, platform_post_id: str, image_url: str) -> str:
        """Tạo định danh băm đơn định (SHA256 16 hex chars) từ (source, platform_post_id, url)."""
        raw = f"{source}::{platform_post_id}::{image_url}".strip()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def generate_object_key(
        cls, source: str, platform_post_id: str, position: int, image_url: str, ext: str = "jpg"
    ) -> str:
        """Tạo object key đơn định trong MinIO: <source>/<platform_post_id>/img_<pos>_<url_hash>.<ext>"""
        clean_ext = ext.lstrip(".").lower() or "jpg"
        url_hash = hashlib.md5(image_url.encode("utf-8")).hexdigest()[:8]
        return f"{source}/{platform_post_id}/img_{position}_{url_hash}.{clean_ext}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["last_error_category"] = self.last_error_category.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AssetItem":
        d = dict(data)
        d["status"] = AssetStatus(d.get("status", AssetStatus.PENDING.value))
        d["last_error_category"] = AssetErrorCategory(
            d.get("last_error_category", AssetErrorCategory.NONE.value)
        )
        return cls(**d)


@dataclass
class SourceAssetMetrics:
    """Chỉ số chi tiết theo từng nguồn dữ liệu."""

    source: str
    total_metadata: int = 0
    stored: int = 0
    actionable_pending: int = 0
    selected_this_run: int = 0
    attempted: int = 0
    uploaded: int = 0
    already_stored: int = 0
    retryable_failed: int = 0
    terminal: int = 0
    remaining_actionable: int = 0


@dataclass
class AssetBatchResult:
    """Kết quả định lượng của một chu kỳ reconcile tài nguyên hình ảnh."""

    batch_budget: int = 50
    batch_used: int = 0
    unused_capacity: int = 0
    candidates_found: int = 0
    already_stored: int = 0
    attempted: int = 0
    downloaded: int = 0
    uploaded: int = 0
    skipped: int = 0
    retryable_failed: int = 0
    terminal_failed: int = 0
    remaining_pending: int = 0
    minio_objects_before: int = 0
    minio_objects_after: int = 0
    per_source: dict[str, SourceAssetMetrics] = field(default_factory=dict)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str | None = None

