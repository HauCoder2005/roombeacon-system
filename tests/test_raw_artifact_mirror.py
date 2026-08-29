import json
from pathlib import Path
from unittest.mock import MagicMock

from roombeacon_crawler.infrastructure.storage.minio.raw_artifact_mirror import (
    MinIORawArtifactMirror,
)


def test_disabled_raw_mirror_has_no_side_effect(tmp_path: Path) -> None:
    client = MagicMock()
    mirror = MinIORawArtifactMirror(client=client, enabled=False)

    assert mirror.mirror_directory(
        tmp_path,
        source="nhatot",
        run_id="run-1",
    ) == []
    client.put_object.assert_not_called()


def test_raw_mirror_uploads_json_then_verified_success_marker(tmp_path: Path) -> None:
    bronze_dir = tmp_path / "bronze" / "nhatot" / "2026-08-29" / "run-1"
    bronze_dir.mkdir(parents=True)
    (bronze_dir / "listings.json").write_text('[{"id": 1}]', encoding="utf-8")
    (bronze_dir / "metadata.json").write_text("[]", encoding="utf-8")

    client = MagicMock()
    mirror = MinIORawArtifactMirror(
        client=client,
        bucket_name="roombeacon-raw",
        enabled=True,
    )

    uploaded = mirror.mirror_directory(
        bronze_dir,
        source="nhatot",
        run_id="run-1",
    )

    assert uploaded == [
        "bronze/nhatot/2026-08-29/run-1/listings.json",
        "bronze/nhatot/2026-08-29/run-1/metadata.json",
        "bronze/nhatot/2026-08-29/run-1/_SUCCESS",
    ]
    marker_call = client.put_object.call_args_list[-1].kwargs
    marker = json.loads(marker_call["Body"].decode("utf-8"))
    assert marker["run_id"] == "run-1"
    client.head_object.assert_called_once_with(
        Bucket="roombeacon-raw",
        Key="bronze/nhatot/2026-08-29/run-1/_SUCCESS",
    )
