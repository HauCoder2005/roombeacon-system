"""Small utilities shared by RoomBeacon notebooks."""

from pathlib import Path

from .project_path import add_src_layout_paths, setup_project_path

# Notebooks 02-07 only put the repository root on sys.path before importing
# notebooks.utils.*; the re-export shims need the src-layout packages too.
add_src_layout_paths(Path(__file__).resolve().parents[2])

__all__ = ["setup_project_path"]
