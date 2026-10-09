"""Xác định repository RoomBeacon trước khi import các package của dự án."""

import os
import sys
from pathlib import Path

# Các package theo src-layout mà analytics và các shim trong notebooks/utils dùng.
SRC_LAYOUT_DIRS = (
    Path("crawler") / "src",
    Path("processing") / "src",
    Path("warehouse") / "src",
)


def add_src_layout_paths(project_root: Path) -> None:
    """Cho phép import ``roombeacon_crawler``, ``roombeacon_processing`` và warehouse."""
    for relative_dir in SRC_LAYOUT_DIRS:
        import_path_text = str(project_root / relative_dir)
        if import_path_text not in sys.path:
            sys.path.insert(0, import_path_text)


def setup_project_path() -> Path:
    """Tìm thư mục gốc RoomBeacon và cho phép import các package của dự án."""
    start_directory = Path.cwd().resolve()
    required_entries = ("analytics", "crawler", "docker-compose.yml")

    for candidate in (start_directory, *start_directory.parents):
        if all((candidate / entry).exists() for entry in required_entries):
            # Chia sẻ root đã xác định cho các module analytics. Nhờ đó những
            # module này không phải tự đoán lại vị trí project trong notebook.
            os.environ["ROOMBEACON_PROJECT_ROOT"] = str(candidate)

            # Thư mục gốc cung cấp ``analytics`` và ``notebooks``.
            for import_path in (candidate, candidate / "notebooks"):
                import_path_text = str(import_path)
                if import_path_text not in sys.path:
                    sys.path.insert(0, import_path_text)
            add_src_layout_paths(candidate)

            print(f"Đã phát hiện thư mục gốc của dự án RoomBeacon: {candidate}")
            return candidate

    raise RuntimeError(
        "Không thể tìm thấy thư mục gốc của dự án RoomBeacon khi bắt đầu từ "
        f"{start_directory}. Thư mục gốc phải chứa analytics/, crawler/ và "
        "docker-compose.yml."
    )
