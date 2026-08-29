"""Mirror durable local Bronze artifacts into the MinIO raw bucket."""

import json
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config

from roombeacon_crawler.config.get_env import env


class MinIORawArtifactMirror:
    """Sao lưu một Bronze run lên MinIO và ghi marker sau khi hoàn tất."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        bucket_name: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.config = env.minio
        self.enabled = (
            self.config.raw_mirror_enabled if enabled is None else enabled
        )
        self.bucket_name = bucket_name or self.config.bucket_raw
        self._client = client

    def _get_client(self) -> Any:
        """Tạo S3 client dùng path-style endpoint tương thích MinIO."""
        if self._client is None:
            if not self.config.access_key or not self.config.secret_key:
                raise RuntimeError("Thiếu credentials để mirror Bronze lên MinIO.")
            scheme = "https" if self.config.secure else "http"
            endpoint = self.config.endpoint
            if not endpoint.startswith(("http://", "https://")):
                endpoint = f"{scheme}://{endpoint}"
            self._client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    def mirror_directory(
        self,
        bronze_path: str | Path,
        *,
        source: str,
        run_id: str,
    ) -> list[str]:
        """Upload toàn bộ JSON và chỉ ghi _SUCCESS sau khi tất cả upload thành công."""
        if not self.enabled:
            return []

        directory = Path(bronze_path).resolve()
        if not directory.is_dir():
            raise FileNotFoundError(f"Không tìm thấy thư mục Bronze: {directory}")

        date_partition = directory.parent.name
        object_prefix = f"bronze/{source}/{date_partition}/{run_id}"
        client = self._get_client()
        uploaded_keys: list[str] = []

        for artifact in sorted(directory.glob("*.json")):
            object_key = f"{object_prefix}/{artifact.name}"
            client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=artifact.read_bytes(),
                ContentType="application/json",
                Metadata={"source": source, "run_id": run_id},
            )
            uploaded_keys.append(object_key)

        if not uploaded_keys:
            raise RuntimeError("Bronze run không chứa JSON artifact để mirror.")

        marker_key = f"{object_prefix}/_SUCCESS"
        marker_body = json.dumps(
            {"source": source, "run_id": run_id, "artifacts": uploaded_keys},
            ensure_ascii=False,
        ).encode("utf-8")
        client.put_object(
            Bucket=self.bucket_name,
            Key=marker_key,
            Body=marker_body,
            ContentType="application/json",
        )
        client.head_object(Bucket=self.bucket_name, Key=marker_key)
        uploaded_keys.append(marker_key)
        return uploaded_keys
