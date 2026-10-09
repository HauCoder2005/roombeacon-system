"""Offset pagination with bounded page size and bounded depth."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Generic, TypeVar

from ..domain.errors import InvalidParameterError


T = TypeVar("T")
MAX_PER_PAGE = 100
# Deep offsets get slower and enable scraping; narrow the filters instead.
MAX_WINDOW = 10_000


@dataclass(frozen=True)
class PageRequest:
    page: int
    per_page: int

    def __post_init__(self) -> None:
        if self.page < 1:
            raise InvalidParameterError("page", "out_of_range", "page must be >= 1")
        if not 1 <= self.per_page <= MAX_PER_PAGE:
            raise InvalidParameterError("per_page", "out_of_range", f"per_page must be between 1 and {MAX_PER_PAGE}")
        if self.page * self.per_page > MAX_WINDOW:
            raise InvalidParameterError(
                "page", "window_too_deep", f"page * per_page must be <= {MAX_WINDOW}; narrow the filters"
            )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    total: int
    request: PageRequest

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.request.per_page) if self.total else 0

    @property
    def has_next(self) -> bool:
        return self.request.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.request.page > 1
