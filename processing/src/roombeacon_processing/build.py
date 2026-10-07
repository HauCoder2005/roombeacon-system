"""Snapshot-only application service for canonical Silver publication."""

from dataclasses import asdict, dataclass
from pathlib import Path
import time
from typing import Any

from analytics.bronze.snapshot import load_bronze_snapshot
from analytics.silver.materializer import SilverMaterializer

from .silver import build_silver_dataset, evaluate_pre_silver_quality_gate


EXPECTED_SILVER_COLUMN_COUNT = 80


class SilverBuildError(RuntimeError):
    """Raised when validated Silver cannot be built or published."""


@dataclass(frozen=True)
class SilverBuildResult:
    snapshot_id: str
    source_files: dict[str, Any]
    runtime_seconds: float
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    output_sha256: str
    schema_version: str
    processing_version: str
    output_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_silver(snapshot_dir: Path, output_dir: Path) -> SilverBuildResult:
    """Build Silver strictly from a validated local Parquet snapshot."""
    started = time.perf_counter()
    bronze, evidence, snapshot = load_bronze_snapshot(Path(snapshot_dir))
    silver = build_silver_dataset(bronze, evidence)
    gate = evaluate_pre_silver_quality_gate(bronze, silver)
    if not gate.passed:
        raise SilverBuildError("Pre-Silver quality gate failed; output was not published")
    if len(silver.columns) != EXPECTED_SILVER_COLUMN_COUNT:
        raise SilverBuildError(
            f"Silver column count is {len(silver.columns)}; "
            f"expected {EXPECTED_SILVER_COLUMN_COUNT}"
        )

    materializer = SilverMaterializer(output_dir=output_dir)
    metadata = materializer.materialize(
        silver,
        quality_gate_passed=True,
        source_snapshot=snapshot,
    )
    return SilverBuildResult(
        snapshot_id=str(snapshot["snapshot_id"]),
        source_files=dict(snapshot["files"]),
        runtime_seconds=time.perf_counter() - started,
        row_count=metadata.row_count,
        column_count=metadata.column_count,
        columns=tuple(metadata.columns),
        output_sha256=metadata.output_sha256,
        schema_version=metadata.schema_version,
        processing_version=metadata.processing_version,
        output_path=str(materializer.output_file),
    )
