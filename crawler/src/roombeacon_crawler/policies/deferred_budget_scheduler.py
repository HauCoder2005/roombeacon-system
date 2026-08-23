import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetAllocation:
    """Kết quả phân bổ ngân sách cào chi tiết."""
    total_budget: int
    deferred_quota: int
    immediate_quota: int


class DeferredBudgetScheduler:
    """Chính sách điều phối ngân sách cào chi tiết công bằng (Fair Budget Scheduling).

    Đảm bảo:
    1. Không làm bỏ đói hàng đợi hoãn (Deferred Backlog) trong các chu kỳ sau.
    2. Không làm bỏ đói luồng phát hiện tin mới (New Discovery) của chu kỳ hiện tại.
    3. Hỗ trợ cơ chế Dynamic Spillover: Nếu một bên không dùng hết hạn ngạch thì tự động
       nhượng lại ngân sách cho bên kia mà không vượt quá tổng `max_details_per_run`.
    """

    def __init__(
        self,
        deferred_share_ratio: float = 0.5,
        min_deferred_slots: int = 1,
    ) -> None:
        self.deferred_share_ratio = max(0.0, min(1.0, float(deferred_share_ratio)))
        self.min_deferred_slots = max(1, int(min_deferred_slots))

    def allocate(
        self,
        total_budget: int,
        deferred_pending_count: int,
    ) -> BudgetAllocation:
        if total_budget <= 0:
            return BudgetAllocation(total_budget=0, deferred_quota=0, immediate_quota=0)

        if deferred_pending_count <= 0:
            return BudgetAllocation(
                total_budget=total_budget,
                deferred_quota=0,
                immediate_quota=total_budget,
            )

        # Tính toán số slot phân bổ cho deferred
        desired_deferred = max(
            self.min_deferred_slots,
            int(math.ceil(total_budget * self.deferred_share_ratio)),
        )
        deferred_quota = min(deferred_pending_count, desired_deferred, total_budget)
        immediate_quota = total_budget - deferred_quota

        return BudgetAllocation(
            total_budget=total_budget,
            deferred_quota=deferred_quota,
            immediate_quota=immediate_quota,
        )

    def spillover_immediate_quota(
        self, total_budget: int, actual_deferred_used: int
    ) -> int:
        """Tính lại hạn ngạch cho immediate work dựa trên số lượng request deferred thực tế đã dùng."""
        return max(0, total_budget - max(0, actual_deferred_used))
