"""Frozen schema and cardinality contract for canonical RoomBeacon Silver."""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd


class SilverContractError(ValueError):
    """Raised when a Silver frame violates its frozen golden contract."""


@dataclass(frozen=True)
class SilverContract:
    row_count: int
    columns: tuple[str, ...]

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, Any]) -> "SilverContract":
        return cls(
            row_count=int(manifest["row_count"]),
            columns=tuple(str(column) for column in manifest["columns"]),
        )

    def validate(self, frame: pd.DataFrame) -> None:
        errors: list[str] = []
        if len(frame) != self.row_count:
            errors.append(f"row_count={len(frame)} expected={self.row_count}")
        actual_columns: Sequence[str] = tuple(str(column) for column in frame.columns)
        if tuple(actual_columns) != self.columns:
            errors.append("ordered columns differ from the golden contract")
        if errors:
            raise SilverContractError("; ".join(errors))
