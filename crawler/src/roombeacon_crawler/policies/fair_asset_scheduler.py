import logging
from typing import TypeVar, Sequence

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FairAssetScheduler:
    """Điều phối công bằng đa nguồn với cơ chế Dynamic Spillover cho Asset Pipeline."""

    @staticmethod
    def allocate_fair_batch(
        source_candidates: dict[str, list[T]],
        batch_size: int,
    ) -> list[T]:
        """Phân bổ các phần tử từ nhiều nguồn với quota công bằng và dynamic spillover.

        Nếu một nguồn có ít phần tử hơn quota của nó, các slot chưa dùng sẽ tự động
        spillover sang các nguồn khác cho đến khi đủ batch_size hoặc hết ứng viên.
        """
        if batch_size <= 0 or not source_candidates:
            return []

        selected_per_source: dict[str, list[T]] = {s: [] for s in source_candidates}
        remaining_pool: dict[str, list[T]] = {
            s: list(items) for s, items in source_candidates.items()
        }

        slots_remaining = batch_size

        while slots_remaining > 0:
            active_sources = [s for s, items in remaining_pool.items() if items]
            if not active_sources:
                break

            quota_per_source = max(1, slots_remaining // len(active_sources))
            allocated_in_round = 0

            for s in active_sources:
                if slots_remaining <= 0:
                    break
                take_count = min(quota_per_source, slots_remaining, len(remaining_pool[s]))
                if take_count > 0:
                    selected_per_source[s].extend(remaining_pool[s][:take_count])
                    remaining_pool[s] = remaining_pool[s][take_count:]
                    slots_remaining -= take_count
                    allocated_in_round += take_count

            if allocated_in_round == 0:
                # Nếu không phân bổ được thêm phần tử nào trong vòng này (ví dụ slots_remaining < len(active_sources))
                for s in active_sources:
                    if slots_remaining <= 0:
                        break
                    if remaining_pool[s]:
                        selected_per_source[s].append(remaining_pool[s].pop(0))
                        slots_remaining -= 1
                break

        # Xen kẽ (interleave) các nguồn để đảm bảo quá trình tải được luân phiên công bằng
        final_batch: list[T] = []
        max_len = max((len(items) for items in selected_per_source.values()), default=0)
        for i in range(max_len):
            for s in source_candidates:
                if i < len(selected_per_source[s]):
                    final_batch.append(selected_per_source[s][i])

        return final_batch
