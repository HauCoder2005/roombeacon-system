# RoomBeacon — EDA & Data Quality Documentation

Official notebooks and execution instructions: [notebooks/README.md](../README.md).
Numeric results in the older methodology documents are **historical snapshots**;
current findings come from the executed official notebooks and their `RUN_CONTEXT`.
Refactor checks: [validation report](notebook_refactor_validation.json).
Detailed notebook architecture and per-cell guides (01–06):
[notebook explanations](./notebook_explanations/README.md), including
[06 Shadow Validation](./notebook_explanations/06_shadow_validation_explained.md).

PART 01 — Data Understanding & EDA
- [01 — Kiểm kê Dataset và Current Snapshot](./01_dataset_inventory_and_snapshot.md)
- [02 — Kiểm tra tính toàn vẹn cấu trúc](./02_structural_validation.md)
- [03 — Ngữ nghĩa dữ liệu thiếu](./03_missing_data_semantics.md)
- [04 — Phân tích định lượng dữ liệu thiếu](./04_missing_data_profiling.md)
- [05 — Trực quan hóa dữ liệu thiếu](./05_missing_data_visualization.md)
- [06 — Pattern và Nguyên nhân Dữ liệu thiếu](./06_missing_patterns_and_root_causes.md)
- [07 — Chiến lược Xử lý Dữ liệu thiếu](./07_missing_data_treatment_strategy.md)
- [PART 01 Summary](./part_01_summary.md)

PART 02 — Cleaning, Standardization & Validation
- [08 — Chuẩn hóa dữ liệu tổng quát](./08_data_standardization.md)
- [09 — Chuẩn hóa và phân tích cấu trúc địa chỉ](./09_address_standardization.md)
- [10 — Chuẩn hóa Phường/Xã và Administrative Mapping](./10_ward_normalization_and_mapping.md)
- [11 — Kiểm tra và phục hồi Price / Area](./11_price_area_validation.md)

PART 03 — Modeling & Training Architecture
- [12 — Kiến trúc Phân vùng Huấn luyện (TRAIN Partition Architecture)](./train_partition_architecture.md)
- [13 — Giải thích Bản chất TRAIN, VALIDATION và TEST trong Machine Learning & RoomBeacon](./train_validation_test_explained.md)

