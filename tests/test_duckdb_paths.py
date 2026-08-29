from pathlib import Path
from unittest.mock import patch

from analytics.duckdb import connection


def test_container_data_path_maps_to_project_when_mount_is_not_writable(
    tmp_path: Path,
) -> None:
    with (
        patch.object(connection, "_find_project_root", return_value=tmp_path),
        patch.object(connection.os, "access", return_value=False),
        patch.dict(
            connection.os.environ,
            {"ROOMBEACON_CONTAINER_DATA_DIR": "/data"},
        ),
    ):
        resolved = connection.resolve_runtime_path(
            "/data/duckdb/roombeacon_analytics.duckdb"
        )

    assert resolved == (
        tmp_path / "data" / "duckdb" / "roombeacon_analytics.duckdb"
    ).resolve()


def test_writable_container_volume_keeps_container_path(tmp_path: Path) -> None:
    container_data = tmp_path / "mounted-data"
    container_data.mkdir()
    configured = container_data / "duckdb" / "roombeacon_analytics.duckdb"

    with patch.dict(
        connection.os.environ,
        {"ROOMBEACON_CONTAINER_DATA_DIR": str(container_data)},
    ):
        resolved = connection.resolve_runtime_path(str(configured))

    assert resolved == configured


def test_notebook_project_root_from_utils_is_reused(tmp_path: Path) -> None:
    with (
        patch.object(connection.os, "access", return_value=False),
        patch.object(
            connection,
            "_find_project_root",
            side_effect=AssertionError("Không được tự tìm lại project root"),
        ),
        patch.dict(
            connection.os.environ,
            {
                "ROOMBEACON_CONTAINER_DATA_DIR": "/data",
                "ROOMBEACON_PROJECT_ROOT": str(tmp_path),
            },
        ),
    ):
        resolved = connection.resolve_runtime_path(
            "/data/duckdb/roombeacon_analytics.duckdb"
        )

    assert resolved == (
        tmp_path / "data" / "duckdb" / "roombeacon_analytics.duckdb"
    ).resolve()
