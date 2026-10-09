"""``sort=-field`` parsing against an explicit whitelist."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import InvalidParameterError


@dataclass(frozen=True)
class SortSpec:
    field: str
    descending: bool

    @classmethod
    def parse(cls, raw: str, allowed: frozenset[str]) -> "SortSpec":
        value = raw.strip()
        descending = value.startswith("-")
        name = value[1:] if descending else value
        if name not in allowed:
            raise InvalidParameterError("sort", "not_allowed", f"sort must be one of: {', '.join(sorted(allowed))}")
        return cls(name, descending)

    @property
    def token(self) -> str:
        return f"-{self.field}" if self.descending else self.field
