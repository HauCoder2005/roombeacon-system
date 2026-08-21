from abc import ABC, abstractmethod
from typing import Any


class AnalyticsRepositoryPort(ABC):
    """Port giao tiếp tầng phân tích dữ liệu (DuckDB / OLAP)."""

    @abstractmethod
    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Thực thi câu truy vấn phân tích và trả về kết quả dạng dictionary."""
        pass
