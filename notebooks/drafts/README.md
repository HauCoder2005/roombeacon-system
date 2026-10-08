# Non-official drafts / historical snapshots

Giữ nguyên bytes, code và outputs của từng phiên bản; không dùng findings ở đây làm current results:

| Notebook | Vai trò |
|---|---|
| [legacy_roombeacon_eda.ipynb](legacy_roombeacon_eda.ipynb) | Legacy EDA snapshot đã lưu từ lần refactor |
| [legacy_roombeacon_eda_with_outputs.ipynb](legacy_roombeacon_eda_with_outputs.ipynb) | Legacy EDA từ notebooks root khi cleanup; cùng cell sources nhưng khác outputs/metadata |
| [price_modeling_draft.ipynb](price_modeling_draft.ipynb) | Modeling draft đã lưu từ lần refactor |
| [price_modeling_draft_with_outputs.ipynb](price_modeling_draft_with_outputs.ipynb) | Modeling draft từ notebooks root khi cleanup; cùng cell sources nhưng khác outputs/metadata |

Không execute các drafts trong official pipeline. Modeling chờ Task 12–16. [Official notebooks](../README.md).

## Paths và review backlog

Drafts giữ nguyên bootstrap cũ (`from utils ...`), nên nếu sau này cần chạy thủ công, kernel working directory phải là `notebooks/`, hoặc cấu hình `PYTHONPATH` chứa repository root và `notebooks/` trước khi khởi động kernel. Working directory `drafts/` mặc định không resolve được import đầu tiên của modeling draft. Cleanup không sửa code hoặc chạy drafts.

`notebooks/processing/` không tồn tại. `processing/` ở repository root được giữ nguyên: có Docker runtime hợp lệ, script EDA cũ, queries ad hoc và HTML/JSON scratch artifacts; official notebooks không import folder này. **REVIEW_NEEDED** cho các scripts legacy, không xóa tự động.

Có **29 Python scripts** còn tham chiếu path legacy `notebooks/roombeacon_eda.ipynb`: 20 trong `scripts/` và 9 trong `processing/`. Chúng là tools kiểm tra/generate/rewrite notebook cũ, không được redirect sang official notebooks vì có thể ghi đè analysis. Giữ nguyên để review riêng; không chạy chúng như current validation.

Các tên helper trùng cần review semantics, chưa phải bằng chứng implementation trùng: `validate_area` (`area_validator.py`, `price_area_validation.py`), `validate_price` (`price_validator.py`, `price_area_validation.py`), `remove_vietnamese_accents` (`ward_normalization.py`, `location_normalizer.py`). Không sửa helpers trong cleanup.

## legacy_builders/

Scripts that used to generate Notebooks 03–07. The notebooks are now edited directly and are the source of truth; these scripts are kept for history only and must not be run (they would overwrite the curated notebooks).
