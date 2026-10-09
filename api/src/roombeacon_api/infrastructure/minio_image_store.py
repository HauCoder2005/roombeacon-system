"""Read-only MinIO adapter for listing images.

The crawler stores images as <source>/<source_listing_id>/img_<position>_<8 hex>.<ext>
in the assets bucket. Only keys of exactly that shape under the listing's own
prefix are served; identifiers are validated before any S3 call. Objects that
are not images or are larger than MAX_IMAGE_BYTES are refused. Prefix listings
are cached briefly because cards request them in bulk.
"""

from __future__ import annotations

from collections import OrderedDict
import logging
import re
import threading
import time
from typing import Any, Callable

from ..config import MinioSettings
from ..domain.errors import DependencyUnavailableError
from ..domain.models import IMAGE_CONTENT_TYPES as ALLOWED_TYPES, ImageObject, ImageRef


logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_LISTING = 50
CACHE_TTL_SECONDS = 600.0
CACHE_ENTRIES = 5_000
MISSING_CODES = frozenset({"NoSuchKey", "404", "NotFound"})


def _safe(name: str | None) -> bool:
    """A single path segment: allowed characters, never '.', '..' or any '..' run."""
    return bool(name) and SAFE_ID.fullmatch(name) is not None and ".." not in name and name != "."


class MinioImageStore:
    def __init__(
        self,
        settings: MinioSettings | None = None,
        *,
        bucket: str | None = None,
        client: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._bucket = bucket or (settings.bucket if settings else "")
        self._client = client
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, tuple[float, list[ImageRef]]] = OrderedDict()
        self._index: tuple[float, frozenset[tuple[str, str]]] | None = None

    def list_images(self, source: str, source_listing_id: str) -> list[ImageRef]:
        if not (_safe(source) and _safe(source_listing_id)):
            return []
        prefix = f"{source}/{source_listing_id}/"
        now = self._clock()
        with self._lock:
            hit = self._cache.get(prefix)
            if hit and now - hit[0] < CACHE_TTL_SECONDS:
                return hit[1]
        pattern = re.compile(rf"^{re.escape(prefix)}img_(\d{{1,4}})_[0-9a-f]{{8}}\.(jpe?g|png|webp|gif)$")
        try:
            response = self._s3().list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=MAX_IMAGES_PER_LISTING * 2)
        except Exception as exc:
            logger.warning("image listing failed: %s", type(exc).__name__)
            raise DependencyUnavailableError("images") from exc
        refs: dict[int, ImageRef] = {}
        for item in response.get("Contents", []):
            match = pattern.match(item.get("Key", ""))
            if match:
                position = int(match.group(1))
                refs.setdefault(position, ImageRef(position, item["Key"]))
        result = [refs[p] for p in sorted(refs)][:MAX_IMAGES_PER_LISTING]
        with self._lock:
            self._cache[prefix] = (now, result)
            self._cache.move_to_end(prefix)
            while len(self._cache) > CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return result

    def listings_with_images(self) -> frozenset[tuple[str, str]]:
        """Index of <source>/<listing>/ prefixes, rebuilt at most every CACHE_TTL_SECONDS."""
        now = self._clock()
        with self._lock:
            if self._index and now - self._index[0] < CACHE_TTL_SECONDS:
                return self._index[1]
        try:
            pairs = set()
            for source in self._common_prefixes(""):
                if not _safe(source):
                    continue
                for listing in self._common_prefixes(f"{source}/"):
                    if _safe(listing):
                        pairs.add((source, listing))
        except Exception as exc:
            logger.warning("image index failed: %s", type(exc).__name__)
            raise DependencyUnavailableError("images") from exc
        index = frozenset(pairs)
        with self._lock:
            self._index = (now, index)
        return index

    def _common_prefixes(self, prefix: str) -> list[str]:
        names, token = [], None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix, "Delimiter": "/", "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            response = self._s3().list_objects_v2(**kwargs)
            names.extend(p["Prefix"][len(prefix):].rstrip("/") for p in response.get("CommonPrefixes", []))
            if not response.get("IsTruncated"):
                return names
            token = response.get("NextContinuationToken")

    def get_image(self, key: str) -> ImageObject | None:
        try:
            response = self._s3().get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
            if code in MISSING_CODES:
                return None
            logger.warning("image read failed: %s", type(exc).__name__)
            raise DependencyUnavailableError("images") from exc
        content_type = (response.get("ContentType") or "").split(";")[0].strip().lower()
        length = int(response.get("ContentLength") or 0)
        if content_type not in ALLOWED_TYPES or length > MAX_IMAGE_BYTES:
            response["Body"].close()
            return None
        content = response["Body"].read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            return None
        return ImageObject(content, content_type, response.get("ETag"), len(content))

    def _s3(self) -> Any:
        with self._lock:
            if self._client is None:
                import boto3
                from botocore.config import Config

                s = self._settings
                self._client = boto3.client(
                    "s3",
                    endpoint_url=f"{'https' if s.secure else 'http'}://{s.endpoint}",
                    aws_access_key_id=s.access_key,
                    aws_secret_access_key=s.secret_key.get_secret_value(),
                    region_name="us-east-1",
                    config=Config(
                        signature_version="s3v4",
                        connect_timeout=3,
                        read_timeout=10,
                        retries={"max_attempts": 2},
                        s3={"addressing_style": "path"},
                    ),
                )
            return self._client
