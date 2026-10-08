import subprocess
import sys
from pathlib import Path

import pytest

from notebooks.utils.project_path import setup_project_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "shim",
    ["notebook_audit", "silver_processing", "location_analysis", "listing_semantics"],
)
def test_processing_shims_import_with_only_project_root_on_path(shim):
    # Notebooks 02-07 only insert PROJECT_ROOT before importing notebooks.utils.*.
    code = (
        "import sys; sys.path[:] = [p for p in sys.path if 'src' not in p]; "
        f"sys.path.insert(0, {str(PROJECT_ROOT)!r}); "
        f"import notebooks.utils.{shim}"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT / "notebooks",
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_setup_project_path_exposes_src_layout_packages(tmp_path, monkeypatch):
    for entry in ("analytics", "crawler/src", "processing/src", "warehouse/src", "notebooks"):
        (tmp_path / entry).mkdir(parents=True)
    (tmp_path / "docker-compose.yml").touch()
    monkeypatch.chdir(tmp_path / "notebooks")
    monkeypatch.setattr(sys, "path", [])
    monkeypatch.delenv("ROOMBEACON_PROJECT_ROOT", raising=False)

    root = setup_project_path()

    assert root == tmp_path.resolve()
    for entry in ("crawler/src", "processing/src", "warehouse/src"):
        assert str(tmp_path.resolve() / entry) in sys.path
