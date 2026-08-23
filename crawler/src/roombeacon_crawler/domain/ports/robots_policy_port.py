from abc import ABC, abstractmethod
from typing import Any
from roombeacon_crawler.policies.robots_policy import RobotsEvaluationResult


class RobotsPolicyPort(ABC):
    """Port giao tiếp thẩm định chính sách Robots Exclusion Protocol (RFC 9309)."""

    @abstractmethod
    def evaluate(self, url: str) -> RobotsEvaluationResult:
        """Đánh giá tính hợp lệ của URL theo robots.txt."""
        pass

    @abstractmethod
    def is_allowed(self, url: str) -> bool:
        """Trả về True nếu URL được phép truy cập theo robots.txt."""
        pass
