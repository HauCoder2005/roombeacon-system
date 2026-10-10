"""Reconcile Bronze image candidates into validated MinIO assets.

The application service applies fair scheduling, outbound URL safety, bounded
downloads and retry classification. Airflow ordering is outside this module.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import pymysql
import requests
from urllib.parse import urljoin

from roombeacon_crawler.application.assets.listing_photos import select_post_photos
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
from roombeacon_crawler.security.url_safety import (
    Resolver,
    UnsafeURLReason,
    URLSafetyError,
    resolve_host_addresses,
    validate_public_http_url,
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 RoomBeaconAssetReconciler/1.0"
)
MAX_ASSET_BYTES = 15 * 1024 * 1024  # 15 MB
DEFAULT_TIMEOUT_SECONDS = 12
MAX_REDIRECTS = 5
MYSQL_IO_TIMEOUT_SECONDS = 60
DEFAULT_ASSET_BATCH_SIZE = 100
# Newest posts are checked every run; older ones are backfilled from a saved cursor.
FRESH_POSTS_PER_SOURCE = 300
BACKFILL_POSTS_PER_SOURCE = 2000
POST_PAGE_SIZE = 200
RETRY_COOLDOWN = timedelta(hours=24)
NEWEST_CURSOR = ("9999-12-31 23:59:59", 9_223_372_036_854_775_807)

# One page of posts below a (last_observed_at, id) cursor with the images of every
# version: a card-only latest version must not hide an earlier detail gallery.
# LEFT JOIN keeps image-less posts so the cursor advances.
POST_IMAGES_PAGE_SQL = """
    SELECT
        p.id AS rental_post_id,
        p.platform_post_id,
        p.last_observed_at,
        pi.id AS image_id,
        pi.rental_post_version_id,
        pi.image_url,
        pi.position,
        %s AS source
    FROM (
        SELECT rp.id, rp.platform_post_id, rp.last_observed_at
        FROM rental_posts rp
        JOIN platforms pl ON pl.id = rp.platform_id
        WHERE pl.code = %s
          -- Spelled out (not a row comparison) so idx_platform_last_observed drives a range scan.
          AND (rp.last_observed_at < %s OR (rp.last_observed_at = %s AND rp.id < %s))
        ORDER BY rp.last_observed_at DESC, rp.id DESC
        LIMIT %s
    ) p
    LEFT JOIN post_images pi ON pi.rental_post_id = p.id
    ORDER BY p.last_observed_at DESC, p.id DESC, pi.rental_post_version_id DESC, pi.position ASC
"""


class AssetReconcilerService:
    """Service đối soát và nạp tài nguyên hình ảnh đa nguồn công bằng từ Bronze MySQL vào MinIO roombeacon-assets."""

    def __init__(
        self,
        state_repo: LocalAssetStateRepository | None = None,
        bucket_name: str | None = None,
        max_retries: int = 3,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        resolver: Resolver = resolve_host_addresses,
        fresh_posts: int = FRESH_POSTS_PER_SOURCE,
        backfill_posts: int = BACKFILL_POSTS_PER_SOURCE,
        post_page_size: int = POST_PAGE_SIZE,
    ) -> None:
        self.state_repo = state_repo or LocalAssetStateRepository()
        self.fresh_posts = fresh_posts
        self.backfill_posts = backfill_posts
        self.post_page_size = post_page_size
        self.minio_cfg = env.minio
        self.bucket_name = bucket_name or self.minio_cfg.bucket_assets
        self.max_retries = max_retries
        self.timeout = timeout
        self.resolver = resolver
        self._s3_client = None
        self._last_already_stored_by_source: dict[str, int] = {}

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
                    # Never hold a Bronze connection slot on a stuck read or lock wait.
                    read_timeout=MYSQL_IO_TIMEOUT_SECONDS,
                    write_timeout=MYSQL_IO_TIMEOUT_SECONDS,
                    init_command=(
                        f"SET SESSION MAX_EXECUTION_TIME={MYSQL_IO_TIMEOUT_SECONDS * 1000}, "
                        f"SESSION lock_wait_timeout={MYSQL_IO_TIMEOUT_SECONDS}"
                    ),
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

            last_error_class = "UnknownError"
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
                        # Reuse the provisioned bucket without ListBucket or
                        # CreateBucket. Scoped principals are verified by the
                        # actual HeadObject/PutObject operations below.
                        self._s3_client = client
                        logger.info("Đã kết nối MinIO thành công tại endpoint: %s", ep)
                        break
                    except Exception as exc:
                        last_error_class = type(exc).__name__
                if self._s3_client is not None:
                    break

            if self._s3_client is None:
                raise ConnectionError(
                    f"Không thể kết nối MinIO (error_class={last_error_class})"
                )

        return self._s3_client

    def count_minio_objects(self) -> int:
        """Đếm số lượng object hiện có trong bucket roombeacon-assets."""
        try:
            s3 = self.get_s3_client()
            res = s3.list_objects_v2(Bucket=self.bucket_name)
            return res.get("KeyCount", 0)
        except Exception as exc:
            logger.warning(
                "Không thể đếm MinIO objects (error_class=%s)",
                type(exc).__name__,
            )
            return 0

    def get_source_accounting(self) -> dict[str, SourceAssetMetrics]:
        """Per-source outcome counts from the durable asset state.

        Sources come from the small platforms table. Pending photos are not
        counted: that needs a GROUP BY over every post_images URL, which starved
        the single-CPU Bronze server twice per crawl run. total_metadata is the
        number of photos with a recorded outcome.
        """
        conn = self.get_mysql_connection()
        accounting: dict[str, SourceAssetMetrics] = {}

        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code AS source FROM platforms ORDER BY code ASC")
                for row in cur.fetchall():
                    accounting[row["source"]] = SourceAssetMetrics(source=row["source"])

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

            metrics.total_metadata = metrics.stored + metrics.terminal + metrics.retryable_failed
            metrics.actionable_pending = 0
            metrics.remaining_actionable = metrics.retryable_failed

        return accounting

    def discover_actionable_candidates_per_source(
        self,
        active_sources: list[str],
        max_per_source: int = 500,
        s3: Any | None = None,
    ) -> dict[str, list[AssetItem]]:
        """Own-photo candidates per source: the newest posts first, then a resumable backfill of older ones."""
        conn = self.get_mysql_connection()
        candidates_by_source: dict[str, list[AssetItem]] = {s: [] for s in active_sources}
        self._last_already_stored_by_source = {s: 0 for s in active_sources}

        with conn:
            with conn.cursor() as cur:
                for s in active_sources:
                    found = candidates_by_source[s]
                    seen_asset_ids: set[str] = set()
                    fresh_end, fresh_exhausted = self._scan_posts(
                        cur, s, NEWEST_CURSOR, self.fresh_posts, found, seen_asset_ids, max_per_source, s3
                    )
                    if fresh_exhausted:
                        self.state_repo.save_cursor(s, None)
                        continue
                    if len(found) >= max_per_source or self.backfill_posts <= 0:
                        continue
                    saved = self.state_repo.get_cursor(s)
                    start = saved if saved is not None and saved < fresh_end else fresh_end
                    end, exhausted = self._scan_posts(
                        cur, s, start, self.backfill_posts, found, seen_asset_ids, max_per_source, s3
                    )
                    self.state_repo.save_cursor(s, None if exhausted else end)

        return candidates_by_source

    def _scan_posts(
        self,
        cur: Any,
        source: str,
        start: tuple[str, int],
        max_posts: int,
        found: list[AssetItem],
        seen_asset_ids: set[str],
        max_per_source: int,
        s3: Any | None,
    ) -> tuple[tuple[str, int], bool]:
        """Walk posts below `start` newest-first; return the last post handled and whether the source ran out."""
        cursor, scanned = start, 0
        while scanned < max_posts and len(found) < max_per_source:
            limit = min(self.post_page_size, max_posts - scanned)
            cur.execute(POST_IMAGES_PAGE_SQL, (source, source, cursor[0], cursor[0], cursor[1], limit))
            posts = self._group_posts(cur.fetchall())
            if not posts:
                return cursor, True
            for post in posts:
                self._collect_post_photos(post, found, seen_asset_ids, s3)
                cursor = (str(post["last_observed_at"]), int(post["rental_post_id"]))
                scanned += 1
                if len(found) >= max_per_source:
                    return cursor, False
            if len(posts) < limit:
                return cursor, True
        return cursor, False

    @staticmethod
    def _group_posts(rows: list[dict]) -> list[dict]:
        posts: dict[int, dict] = {}
        for row in rows:
            post = posts.setdefault(int(row["rental_post_id"]), {
                "rental_post_id": int(row["rental_post_id"]),
                "platform_post_id": str(row["platform_post_id"]),
                "last_observed_at": row["last_observed_at"],
                "source": row["source"],
                "versions": {},
            })
            if row.get("image_url"):
                version = post["versions"].setdefault(row.get("rental_post_version_id"), [])
                version.append((int(row.get("position") or 1), row["image_url"]))
        return list(posts.values())

    def _collect_post_photos(
        self, post: dict, found: list[AssetItem], seen_asset_ids: set[str], s3: Any | None
    ) -> None:
        source, platform_post_id = post["source"], post["platform_post_id"]
        for position, image_url in select_post_photos(source, platform_post_id, post["versions"].values()):
            asset_id = AssetItem.generate_asset_id(source, platform_post_id, image_url)
            # Multiple observations may repeat the same canonical image.
            if asset_id in seen_asset_ids:
                continue
            seen_asset_ids.add(asset_id)

            existing_state = self.state_repo.get_asset(source, asset_id)
            if existing_state and existing_state.status == AssetStatus.SUCCESS:
                if s3 is None or self._object_exists(s3, existing_state.object_key):
                    self._last_already_stored_by_source[source] = self._last_already_stored_by_source.get(source, 0) + 1
                    continue
                # Durable state is not sufficient when the referenced object
                # was removed externally; make the item actionable again.
                existing_state.status = AssetStatus.PENDING
            if existing_state and existing_state.status == AssetStatus.TERMINAL_FAILURE:
                continue
            if (
                existing_state
                and existing_state.status == AssetStatus.RETRYABLE_FAILURE
                and existing_state.attempt_count >= self.max_retries
            ):
                if not self._retry_cooled_down(existing_state):
                    continue
                # Transient failures (timeouts, 5xx) get a fresh retry budget after the cooldown.
                existing_state.attempt_count = 0

            found.append(existing_state or AssetItem(
                asset_id=asset_id,
                source=source,
                platform_post_id=platform_post_id,
                rental_post_id=post["rental_post_id"],
                image_url=image_url,
                position=position,
                object_key=AssetItem.generate_object_key(source, platform_post_id, position, image_url),
                max_retries=self.max_retries,
            ))

    @staticmethod
    def _retry_cooled_down(item: AssetItem) -> bool:
        if not item.last_attempt_at:
            return True
        try:
            last = datetime.fromisoformat(item.last_attempt_at)
        except ValueError:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last >= RETRY_COOLDOWN

    def reconcile_batch(
        self,
        batch_size: int = DEFAULT_ASSET_BATCH_SIZE,
        max_scan_per_source: int = 500,
    ) -> AssetBatchResult:
        """Thực thi một chu kỳ đối soát đa nguồn công bằng với dynamic spillover."""
        result = AssetBatchResult(batch_budget=batch_size)

        # Thu thập kiểm kê ban đầu
        accounting = self.get_source_accounting()
        result.per_source = accounting
        result.pending_before = sum(
            metrics.actionable_pending + metrics.retryable_failed
            for metrics in accounting.values()
        )

        active_sources = list(accounting.keys())
        s3 = self.get_s3_client()
        candidates_by_source = self.discover_actionable_candidates_per_source(
            active_sources,
            max_per_source=max_scan_per_source,
            s3=s3,
        )

        for source, count in self._last_already_stored_by_source.items():
            result.already_stored += count
            if source in result.per_source:
                result.per_source[source].already_stored += count

        result.candidates_found = sum(len(items) for items in candidates_by_source.values())

        # Phân bổ batch công bằng qua FairAssetScheduler
        scheduled_items = FairAssetScheduler.allocate_fair_batch(
            candidates_by_source, batch_size=batch_size
        )
        result.batch_used = len(scheduled_items)
        result.unused_capacity = max(0, batch_size - result.batch_used)

        for item in scheduled_items:
            if item.source in result.per_source:
                result.per_source[item.source].selected_this_run += 1

        # Tải và nạp MinIO
        for item in scheduled_items:
            result.attempted += 1
            src_metrics = result.per_source.get(item.source)
            if src_metrics:
                src_metrics.attempted += 1

            self._process_single_asset(item, s3, result)

        result.finished_at = datetime.now(timezone.utc).isoformat()
        result.duration_seconds = max(
            0.0,
            (
                datetime.fromisoformat(result.finished_at)
                - datetime.fromisoformat(result.started_at)
            ).total_seconds(),
        )

        # Cập nhật lại remaining_actionable per source sau batch
        updated_accounting = self.get_source_accounting()
        for s, m in updated_accounting.items():
            if s in result.per_source:
                result.per_source[s].stored = m.stored
                result.per_source[s].terminal = m.terminal
                result.per_source[s].retryable_failed = m.retryable_failed
                result.per_source[s].actionable_pending = m.actionable_pending
                result.per_source[s].remaining_actionable = m.remaining_actionable

        result.remaining_pending = sum(
            m.actionable_pending + m.retryable_failed
            for m in result.per_source.values()
        )

        completed_outcomes = (
            result.post_upload_verified
            + result.terminal_failed
            + result.retryable_failed
        )
        if completed_outcomes != result.batch_used or result.attempted != result.batch_used:
            raise RuntimeError("Asset batch outcome accounting invariant violated")

        logger.info(
            "Asset Reconciler Batch Finish: Budget=%d, Selected=%d, Verified=%d, RetryableFailed=%d, TerminalFailed=%d, Pending=%d -> %d",
            result.batch_budget,
            result.batch_used,
            result.post_upload_verified,
            result.retryable_failed,
            result.terminal_failed,
            result.pending_before,
            result.remaining_pending,
        )
        return result

    def _process_single_asset(self, item: AssetItem, s3: Any, result: AssetBatchResult) -> None:
        """Tải, kiểm tra và đẩy một hình ảnh vào MinIO."""
        item.attempt_count += 1
        item.last_attempt_at = datetime.now(timezone.utc).isoformat()
        src_metrics = result.per_source.get(item.source)

        url = item.image_url

        # Kiểm tra data URL (không phải HTTP)
        if url.startswith("data:"):
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_DATA_URL
            item.last_error_message = "URL là data base64 URI thay vì HTTP/HTTPS."
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return

        if not url.startswith(("http://", "https://")):
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.HTTP_CLIENT_ERROR
            item.last_error_message = f"Giao thức URL không hợp lệ: {url[:30]}"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return

        # Validate every destination and follow redirects manually.
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = self._request_public_asset(url, headers=headers)
        except URLSafetyError as exc:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.SECURITY_REJECTED
            item.last_error_message = f"Outbound URL rejected: {exc.reason.value}"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return
        except requests.exceptions.Timeout as exc:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.TIMEOUT
            item.last_error_message = (
                f"Asset download timed out (error_class={type(exc).__name__})"
            )
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
                src_metrics.retryable_failed_this_run += 1
            return
        except requests.exceptions.RequestException as exc:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.NETWORK_ERROR
            item.last_error_message = (
                f"Asset download failed (error_class={type(exc).__name__})"
            )
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
                src_metrics.retryable_failed_this_run += 1
            return

        # Kiểm tra HTTP Status Code
        status_code = resp.status_code
        if status_code in (400, 403, 404, 410):
            resp.close()
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.HTTP_CLIENT_ERROR
            item.last_error_message = f"HTTP {status_code} client error"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return

        if status_code != 200:
            resp.close()
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.NETWORK_ERROR
            item.last_error_message = f"HTTP {status_code} server error"
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
                src_metrics.retryable_failed_this_run += 1
            return

        # Kiểm tra Content-Type
        content_type_header = resp.headers.get("Content-Type", "").lower()
        if "text/html" in content_type_header or "application/json" in content_type_header:
            resp.close()
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.HTML_CHALLENGE
            item.last_error_message = f"Phát hiện HTML/JSON phản hồi thay vì hình ảnh ({content_type_header})"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return

        # Stream body with a hard upper bound before buffering it in memory.
        try:
            content_bytes = self._read_bounded_content(resp)
        except ValueError:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_CONTENT_TYPE
            item.last_error_message = "Asset response exceeds maximum allowed size"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return
        finally:
            resp.close()
        if len(content_bytes) == 0:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_MAGIC_BYTES
            item.last_error_message = "Dữ liệu hình ảnh rỗng (0 bytes)."
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            result.invalid_magic += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_invalid_this_run += 1
                src_metrics.terminal_failed_this_run += 1
            return

        if len(content_bytes) > MAX_ASSET_BYTES:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_CONTENT_TYPE
            item.last_error_message = f"Dung lượng vượt quá giới hạn ({len(content_bytes)} > {MAX_ASSET_BYTES})"
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_failed_this_run += 1
            return

        # Kiểm tra Magic Bytes
        ext, validated_mime = self._detect_image_format(content_bytes)
        if not ext:
            item.status = AssetStatus.TERMINAL_FAILURE
            item.last_error_category = AssetErrorCategory.INVALID_MAGIC_BYTES
            item.last_error_message = "Không nhận diện được magic bytes hình ảnh hợp lệ (JPEG/PNG/WebP/GIF)."
            self.state_repo.save_asset(item)
            result.terminal_failed += 1
            result.invalid_magic += 1
            if src_metrics:
                src_metrics.terminal += 1
                src_metrics.terminal_invalid_this_run += 1
                src_metrics.terminal_failed_this_run += 1
            return

        # Cập nhật object_key với đúng extension thực tế
        item.object_key = AssetItem.generate_object_key(
            item.source, item.platform_post_id, item.position, item.image_url, ext=ext
        )
        item.content_type = validated_mime
        item.size_bytes = len(content_bytes)
        result.downloaded += 1
        if src_metrics:
            src_metrics.downloaded_valid += 1

        # Upload lên MinIO
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
            result.uploaded += 1
            if src_metrics:
                src_metrics.uploaded += 1
            if not self._object_exists(s3, item.object_key):
                raise RuntimeError("Uploaded MinIO object could not be verified")
            item.status = AssetStatus.SUCCESS
            item.last_error_category = AssetErrorCategory.NONE
            item.last_error_message = None
            self.state_repo.save_asset(item)
            result.post_upload_verified += 1
            if src_metrics:
                src_metrics.post_upload_verified += 1
            logger.debug("Đã tải và lưu thành công MinIO asset: %s", item.object_key)
        except Exception as exc:
            item.status = AssetStatus.RETRYABLE_FAILURE
            item.last_error_category = AssetErrorCategory.UPLOAD_ERROR
            item.last_error_message = (
                f"MinIO upload failed (error_class={type(exc).__name__})"
            )
            self.state_repo.save_asset(item)
            result.retryable_failed += 1
            if src_metrics:
                src_metrics.retryable_failed += 1
                src_metrics.retryable_failed_this_run += 1

    def _request_public_asset(self, url: str, headers: dict[str, str]) -> requests.Response:
        """Fetch one URL after validating DNS and every bounded redirect hop."""
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            validate_public_http_url(current_url, resolver=self.resolver)
            response = requests.get(
                current_url,
                headers=headers,
                timeout=self.timeout,
                stream=True,
                allow_redirects=False,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response

            location = response.headers.get("Location")
            response.close()
            if not location or redirect_count >= MAX_REDIRECTS:
                raise URLSafetyError(UnsafeURLReason.INVALID_URL)
            current_url = urljoin(current_url, location)

        raise URLSafetyError(UnsafeURLReason.INVALID_URL)

    def _object_exists(self, s3: Any, object_key: str) -> bool:
        """Return whether the configured bucket contains the durable state key.

        Authorization and service errors fail the reconciliation closed; only a
        definitive S3 not-found response makes the asset actionable again.
        """
        try:
            s3.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if str(error.get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    @staticmethod
    def _read_bounded_content(response: requests.Response) -> bytes:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > MAX_ASSET_BYTES:
                    raise ValueError("asset too large")
            except ValueError as exc:
                if str(exc) == "asset too large":
                    raise

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_ASSET_BYTES:
                raise ValueError("asset too large")
            chunks.append(chunk)
        return b"".join(chunks)

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
