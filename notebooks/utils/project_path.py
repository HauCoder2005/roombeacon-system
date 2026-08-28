"""Locate the RoomBeacon repository before importing project packages."""

import sys
from pathlib import Path


def setup_project_path() -> Path:
    """Find the RoomBeacon root and make project packages importable."""
    start_directory = Path.cwd().resolve()
    required_entries = ("analytics", "crawler", "docker-compose.yml")

    for candidate in (start_directory, *start_directory.parents):
        if all((candidate / entry).exists() for entry in required_entries):
            # The root exposes ``analytics``; crawler/src exposes the src-layout
            # ``roombeacon_crawler`` package imported by analytics modules.
            import_paths = (candidate, candidate / "crawler" / "src")
            for import_path in import_paths:
                import_path_text = str(import_path)
                if import_path_text not in sys.path:
                    sys.path.insert(0, import_path_text)

            print(f"Detected RoomBeacon project root: {candidate}")
            return candidate

    raise RuntimeError(
        "Unable to find the RoomBeacon project root starting from "
        f"{start_directory}. Expected analytics/, crawler/, and "
        "docker-compose.yml in the project root."
    )
