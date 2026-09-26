# RoomBeacon notebooks

Chỉ hai notebooks ở root là official:

- [01 — EDA](01_roombeacon_eda.ipynb): Task 01–07.
- [02 — Processing & Validation](02_roombeacon_processing.ipynb): Task 08–16; hiện chỉ 08–11 implemented, 12–16 là placeholders.

Notebook 02 có **Analytical Preview — Radius-Based Local Market** sau Section 11.
Điền `REFERENCE_LOCATION` bằng một điểm thực tế để chạy radius → local price →
price/area filter. Giá trị mặc định `None` skip an toàn toàn bộ distance output;
notebook không suy khoảng cách từ address text hoặc ward/district centroid.

```text
notebooks/
├── 01_roombeacon_eda.ipynb
├── 02_roombeacon_processing.ipynb
├── README.md
├── requirements.txt
├── drafts/       # Non-official experiments / legacy notebooks
├── docs/         # Task methodology và historical findings
├── utils/        # Reusable helpers
├── configs/
├── enums/
└── sql/
```

`notebooks/processing/` không tồn tại. Thư mục [`../processing/`](../processing/) ở repository root được giữ nguyên; các legacy notebook scripts cần review, không thuộc official workflow.

Dùng Python environment cài [requirements.txt](requirements.txt), cấu hình `.env`, rồi chọn kernel tương ứng. Official notebooks hỗ trợ working directory là repository root hoặc `notebooks/`; mỗi lần Run All có snapshot riêng và dùng canonical read-only connection.

[Draft inventory và các references cần review](drafts/README.md). [Tài liệu](docs/README.md). Không chạy modeling hoặc Task 12–16 trong workflow hiện tại.
