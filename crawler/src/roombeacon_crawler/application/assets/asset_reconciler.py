import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import boto3
from botocore.client import Config
import pymysql
import requests

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.asset_item import (
    AssetBatchResult,
    AssetErrorCategory,
    AssetItem,
    AssetStatus,
    SourceAssetMetrics,
)
from roombeacon_crawler.policies.fair_asset_scheduler import FairAssetScheduler
from roombeacon_crawler.repositories.local_asset_state_repository import (
    LocalAssetStateRepository,
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 RoomBeaconAssetReconciler/1.0"
)
MAX_ASSET_BYTES = 15 * 1024 * 1024  # 15 MB
DEFAULT_TIMEOUT_SECONDS = 12


class AssetReconcilerService:
    """Service đối soát và nạp tài nguyên hình ảnh đa nguồn công bằng từ Bronze MySQL vào MinIO roombeacon-assets."""

    def __init__(
        self,
        state_repo: LocalAssetStateRepository | None = None,
        bucket_name: str | None = None,
        max_retries: int = 3,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.state_repo = state_repo or LocalAssetStateRepository()
        self.minio_cfg = env.minio
        self.bucket_name = bucket_name or self.minio_cfg.bucket_assets
        self.max_retries = max_retries
        self.timeout = timeout
        self._s3_client = None

    def get_mysql_connection(self) -> pymysql.Connection:
        """Tạo kết nối MySQL Bronze an toàn với danh sách candidate hosts."""
        mysql_cfg = env.mysql_bronze
        hosts = [
            (mysql_cfg.host, mysql_cfg.port),
            ("127.0.0.1", 3307),
            ("localhost", 3307),
        ]
        seen = set()
        unique_hosts = []
        for h, p in hosts:
            if (h, p) not in seen:
                seen.add((h, p))
                unique_hosts.append((h, p))

        for h, p in unique_hosts:
            try:
                return pymysql.connect(
                    host=h,
                    port=p,
                    user=mysql_cfg.user,
                    password=mysql_cfg.password,
                    database=mysql_cfg.database,
                    cursorclass=pymysql.cursors.DictCursor,
                    connect_timeout=5,
                )
            except Exception:
                continue

        raise ConnectionError("Không thể kết nối MySQL Bronze.")

    def get_s3_client(self) -> Any:
        """Khởi tạo hoặc trả về client S3/MinIO với cơ chế fallback endpoint và credentials an toàn."""
        if self._s3_client is None:
            endpoints = [
                f"http://{self.minio_cfg.host}:{self.minio_cfg.port}",
                f"http://127.0.0.1:{self.minio_cfg.port}",
                f"http://localhost:{self.minio_cfg.port}",
            ]
            seen = set()
            unique_endpoints = []
            for ep in endpoints:
                if ep not in seen:
                    seen.add(ep)
                    unique_endpoints.append(ep)

            cred_candidates = [
                (self.minio_cfg.access_key, self.minio_cfg.secret_key),
                (self.minio_cfg.root_user, self.minio_cfg.root_password),
            ]
            valid_creds = [(ak, sk) for ak, sk in cred_candidates if ak and sk]

            last_exc = None
            for ep in unique_endpoints:
                for ak, sk in valid_creds:
                    try:
                        client = boto3.client(
                            "s3",
                            endpoint_url=ep,
                            aws_access_key_id=ak,
                            aws_secret_access_key=sk,
                            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=5),
                            region_name="us-east-1",
                        )
                        buckets = client.list_buckets()
                        b_names = [b["Name"] for b in buckets.get("Buckets", [])]
                        if self.bucket_name not in b_names:
                            client.create_bucket(Bucket=self.bucket_name)
                            logger.info("Đã tạo MinIO bucket: %s", self.bucket_name)
                        self._s3_client = client
                        logger.info("Đã kết nối MinIO thành công tại endpoint: %s", ep)
                        break
                    except Exception as exc:
                        last_exc = exc
                if self._s3_client is not None:
                    break

            if self._s3_client is None:
                raise ConnectionError(f"Không thể kết nối MinIO sau khi thử các endpoints ({last_exc})")

        return self._s3_client

    def count_minio_objects(self) -> int:
        """Đếm số lượng object hiện có trong bucket roombeacon-assets."""
        try:
            s3 = self.get_s3_client()
            res = s3.list_objects_v2(Bucket=self.bucket_name)
            return res.get("KeyCount", 0)
        except Exception as exc:
            logger.warning("Không thể đếm MinIO objects: %s", exc)
            return 0

    def get_source_accounting(self) -> dict[str, SourceAssetMetrics]:
        """Tính toán bảng kiểm kê chính xác (Accounting Invariant) cho từng nguồn.

        Total Metadata = Stored + Actionable Pending + Retryable Failed + Terminal
        """
        conn = self.get_mysql_connection()
        accounting: dict[str, SourceAssetMetrics] = {}

        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        pl.code AS source,
                        COUNT(pi.id) AS total_rows,
                        SUM(CASE WHEN pi.image_url LIKE 'http://%' OR pi.image_url LIKE 'https://%' THEN 1 ELSE 0 END) AS http_rows,
                        SUM(CASE WHEN pi.image_url NOT LIKE 'http://%' AND pi.image_url NOT LIKE 'https://%' THEN 1 ELSE 0 END) AS non_http_rows
                    FROM platforms pl
                    JOIN rental_posts p ON p.platform_id = pl.id
                    JOIN post_images pi ON pi.rental_post_id = p.id
                    GROUP BY pl.code
                    ORDER BY pl.id ASC
                """)
                for row in cur.fetchall():
                    s = row["source"]
                    total_m = int(row["total_rows"])
                    non_http_m = int(row["non_http_rows"] or 0)
                    accounting[s] = SourceAssetMetrics(
                        source=s,
                        total_metadata=total_m,
                        terminal=non_http_m,
                    )

        for s, metrics in accounting.items():
            s_dir = self.state_repo.base_dir / s
            if s_dir.exists():
                for json_file in s_dir.glob("*.json"):
                    asset_id = json_file.stem
                    item = self.state_repo.get_asset(s, asset_id)
                    if item:
                        if item.status == AssetStatus.SUCCESS:
                            metrics.stored += 1
                        elif item.status == AssetStatus.RETRYABLE_FAILURE:
                            if item.attempt_count >= self.max_retries:
                                metrics.terminal += 1
                            else:
                                metrics.retryable_failed += 1
                        elif item.status == AssetStatus.TERMINAL_FAILURE:
                            metrics.terminal += 1

            metrics.actionable_pending = max(
                0,
                metrics.total_metadata
                - metrics.stored
                - metrics.terminal
                - metrics.retryable_failed,
            )
            metrics.remaining_actionable = metrics.actionable_pending

        return accounting

    def discover_actionable_candidates_per_source(
        self,
        active_sources: list[str],
        max_per_source: int = 500,
    ) -> dict[str, list[AssetItem]]:
        """Truy vấn các ứng viên actionable pending cho từng nguồn, sắp xếp theo ID tăng dần (oldest first)."""
        conn = self.get_mysql_connection()
        candidates_by_source: dict[str, list[AssetItem]] = {s: [] for s in active_sources}

        with conn:
            with conn.cursor() as cur:
                for s in active_sources:
                    cur.execute(
                        """
                        SELECT 
                            pi.id AS image_id,
                            pi.rental_post_id,
                            pi.image_url,
                            pi.position,
                            p.platform_post_id,
                            pl.code AS source
                        FROM post_images pi
                        JOIN rental_posts p ON pi.rental_post_id = p.id
                        JOIN platforms pl ON p.platform_id = pl.id
                        WHERE pl.code = %s 
                          AND (pi.image_url LIKE 'http://%%' OR pi.image_url LIKE 'https://%%')
                        ORDER BY pi.id ASC
                        LIMIT %s
                        """,
                        (s, max_per_source * 2),
                    )
                    rows = cur.fetchall()

                    for row in rows:
                        source = row["source"]
                        platform_post_id = str(row["platform_post_id"])
                        image_url = row["image_url"]
                        position = int(row.get("position", 1))

                        asset_id = AssetItem.generate_asset_id(source, platform_post_id, image_url)
                        object_key = AssetItem.generate_object_key(source, platform_post_id, position, image_url)

                        existing_state = self.state_repo.get_asset(source, asset_id)

                        if existing_state and existing_state.status == AssetStatus.SUCCESS:
                            continue
                        if existing_state and existing_state.status == AssetStatus.TERMINAL_FAILURE:
                            continue
                        if (
                            existing_state
                            and existing_state.status == AssetStatus.RETRYABLE_FAILURE
                            and existing_state.attempt_count >= self.max_retries
                        ):
                            continue

                        if existing_state:
                            item = existing_state
                        else:
                            item = AssetItem(
                                asset_id=asset_id,
                                source=source,
                                platform_post_id=platform_post_id,
                                rental_post_id=row["rental_post_id"],
                                image_url=image_url,
                                position=position,
                                object_key=object_key,
                                max_retries=self.max_retries,
                            )

                        candidates_by_source[source].append(item)
                        if len(candidates_by_source[source]) >= max_per_source:
                            break

        return candidates_by_source

    def reconcile_batch(
        self,
        batch_size: int = 50,
        max_scan_per_source: int = 500,
    ) -> AssetBatchResult:
        """Thực thi một chu kỳ đối soát đa nguồn công bằng với dynamic spillover."""
        result = AssetBatchResult(batch_budget=batch_size)
        result.minio_objects_before = self.count_minio_objects()

        # 1. Thu thập kiểm kê ban đầu
        accounting = self.get_source_accounting()
        result.per_source = accounting

        active_sources = list(accounting.keys())
        candidates_by_source = self.discover_actionable_candidates_per_source(
            active_sources, max_per_source=max_scan_per_source
        )

        result.candidates_found = sum(len(items) for items in candidates_by_source.values())

        # 2. Phân bổ batch công bằng qua FairAssetScheduler
        scheduled_items = FairAssetScheduler.allocate_fair_batch(
            candidates_by_source, batch_size=batch_size
        )
        result.batch_used = len(scheduled_items)
        result.unused_capacity = max(0, batch_size - result.batch_used)

        for item in scheduled_items:
            if item.source in result.per_source:
                result.per_source[item.source].selected_this_run += 1

        # 3. Tải và nạp MinIO
        s3 = self.get_s3_client()
        for item in scheduled_items:
            result.attempted += 1
            src_metrics = result.per_source.get(item.source)
            if src_metrics:
                src_metrics.attempted += 1

            self._process_single_asset(item, s3, result)

        result.minio_objects_after = self.count_minio_objects()
        result.finished_at = datetime.now(timezone.utc).isoformat()

        # 4. Cập nhật lại remaining_actionable per source sau batch
        updated_accounting = self.get_source_accounting()
        for s, m in updated_accounting.items():
            if s in result.per_source:
                result.per_source[s].stored = m.stored
                result.per_source[s].terminal = m.terminal
                result.per_source[s].retryable_failed = m.retryable_failed
                result.per_source[s].actionable_pending = m.actionable_pending
                result.per_source[s].remaining_actionable = m.remaining_actionable

        result.remaining_pending = sum(m.remaining_actionable for m in result.per_source.values())

        logger.info(
            "Asset Reconciler Batch Finish: Budget=%d, Used=%d, Uploaded=%d, RetryableFailed=%d, TerminalFailed=%d, MinIO Objects=%d -> %d",
            result.batch_budget,
            result.batch_used,
            result.uploaded,
            result.retryable_failed,
            result.terminal_failed,
            result.minio_objects_before,
            result.minio_objects_after,
        )
        return result

    def _process_single_asset(self, item: AssetItem, s3: Any, result: AssetBatchResult) -> None:
        """Tải, kiểm tra và đẩy một hình ảnh vào MinIO."""
        item.attempt_count += 1
        item.last_attempt_at = datetime.now(timezone.utc).isoformat()
        src_metrics = result.per_source.get(item.source)

        url = item.image_url

        # 1. Kiểm tra data URL (không phải HTTP)
        if url.startswith("data:"):
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_DATA_URL
            item.last_error_message = "URL là data base64 URI thay vì HTTP/HTTPS."
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        if not url.startswith(("http://", "https://")):
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.HTTP_CLIENT_ERROR
            item.last_error_message = f"Giao thức URL không hợp lệ: {url[:30]}"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        # 2. Tải HTTP(S) với timeout
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout, stream=True)
        except requests.exceptions.Timeout as exc:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.TIMEOUT
            item.last_error_message = f"Timeout sau {self.timeout}s: {exc}"
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
            return
        except requests.exceptions.RequestException as exc:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.NETWORK_ERROR
            item.last_error_message = f"Network error: {exc}"
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
            return

        # 3. Kiểm tra HTTP Status Code
        status_code = resp.status_code
        if status_code in (400, 403, 404, 410):
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.HTTP_CLIENT_ERROR
            item.last_error_message = f"HTTP {status_code} client error"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        if status_code != 200:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.NETWORK_ERROR
            item.last_error_message = f"HTTP {status_code} server error"
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
            return

        # 4. Kiểm tra Content-Type
        content_type_header = resp.headers.get("Content-Type", "").lower()
        if "text/html" in content_type_header or "application/json" in content_type_header:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.HTML_CHALLENGE
            item.last_error_message = f"Phát hiện HTML/JSON phản hồi thay vì hình ảnh ({content_type_header})"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        # 5. Đọc body và kiểm tra dung lượng
        content_bytes = resp.content
        if len(content_bytes) == 0:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_MAGIC_BYTES
            item.last_error_message = "Dữ liệu hình ảnh rỗng (0 bytes)."
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        if len(content_bytes) > MAX_ASSET_BYTES:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_CONTENT_TYPE
            item.last_error_message = f"Dung lượng vượt quá giới hạn ({len(content_bytes)} > {MAX_ASSET_BYTES})"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        # 6. Kiểm tra Magic Bytes
        ext, validated_mime = self._detect_image_format(content_bytes)
        if not ext:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_MAGIC_BYTES
            item.last_error_message = "Không nhận diện được magic bytes hình ảnh hợp lệ (JPEG/PNG/WebP/GIF)."
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
            return

        # Cập nhật object_key với đúng extension thực tế
        item.object_key = AssetItem.generate_object_key(
            item.source, item.platform_post_id, item.position, item.image_url, ext=ext
        )
        item.content_type = validated_mime
        item.size_bytes = len(content_bytes)
        result.downloaded += 1

        # 7. Upload lên MinIO
        try:
            s3.put_object(
                Bucket=self.bucket_name,
                Key=item.object_key,
                Body=content_bytes,
                ContentType=validated_mime,
                Metadata={
                    "source": item.source,
                    "platform_post_id": str(item.platform_post_id),
                    "rental_post_id": str(item.rental_post_id),
                    "asset_id": item.asset_id,
                },
            )
            item.status = AssetStatus.SUCCESS
            item.last_error_category = AssetErrorCategory.NONE
            item.last_error_message = None
            self.state_repo.save_asset(item)
            result.uploaded += 1
            if src_metrics:
                src_metrics.uploaded += 1
            logger.debug("Đã tải và lưu thành công MinIO asset: %s", item.object_key)
        except Exception as exc:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.UPLOAD_ERROR
            item.last_error_message = f"Lỗi upload MinIO: {exc}"
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1

    def _detect_image_format(self, data: bytes) -> tuple[str | None, str | None]:
        """Phát hiện định dạng hình ảnh và MIME type dựa trên Magic Bytes."""
        if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
            return "jpg", "image/jpeg"
        if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
            return "png", "image/png"
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp", "image/webp"
        if len(data) >= 4 and data[:4] == b"GIF8":
            return "gif", "image/gif"
        return None, None
