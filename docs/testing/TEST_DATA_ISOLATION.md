# CHÍNH SÁCH VÀ CƠ CHẾ CÔ LẬP DỮ LIỆU TEST (TEST DATA ISOLATION)

Tài liệu này quy định các tiêu chuẩn bảo vệ, cơ chế Fail-Closed Guard và quy trình cô lập tuyệt đối môi trường Unit Test / Integration Test nhằm đảm bảo môi trường dữ liệu Production của **RoomBeacon** không bao giờ bị ô nhiễm bởi dữ liệu giả lập (Synthetic/Mock Data).

---

## 1. Nguyên Tắc Cốt Lõi

1. **Test Tuyệt Đối Không Ghi Vào Production Database (`roombeacon_bronze`)**:
   - Môi trường Test chỉ được phép tương tác với Database test riêng biệt (`roombeacon_bronze_test`) hoặc Database In-Memory / SQLite.
2. **Cơ Chế Fail-Closed Isolation Guard**:
   - Nếu tiến trình Test phát hiện biến môi trường hoặc cấu hình cố tình/vô tình trỏ vào `roombeacon_bronze`, hệ thống sẽ lập tức ném ngoại lệ `TestEnvironmentIsolationError` và dừng tiến trình ngay lập tức trước khi bất kỳ kết nối hay câu lệnh nào được phát ra.
3. **Cô Lập Đĩa Host Vật Lý (File Storage Isolation)**:
   - Các Test Fixture tuyệt đối không ghi Bronze Data, Run Manifest hoặc Crawler State vào thư mục persistent thật (`/data/bronze`, `/data/state`, `/data/manifests`).
   - Mọi thao tác I/O trong Unit Test phải sử dụng thư mục tạm (`tempfile.mkdtemp()`) và tự động dọn dẹp sạch sẽ sau khi test hoàn tất (`tearDown`).

---

## 2. Kiến Trúc Bảo Vệ Fail-Closed Guard

Hệ thống triển khai 3 lớp bảo vệ độc lập:

```
┌─────────────────────────────────────────────────────────────┐
│                       TEST RUNTIME                          │
│                                                             │
│  [1. Config Layer]                                         │
│  load_bronze_mysql_env()                                   │
│  ──> Nếu ROOMBEACON_ENV=test && DB == roombeacon_bronze     │
│      ──> Ném TestEnvironmentIsolationError                │
│                                                             │
│  [2. Connection Layer]                                      │
│  MySQLConnectionFactory.get_engine()                       │
│  ──> Nếu is_test_runtime() && DB == roombeacon_bronze       │
│      ──> Chặn khởi tạo SQLAlchemy Engine                    │
│                                                             │
│  [3. Discovery / Reconciler Layer]                          │
│  BronzeRunDiscoveryService.scan_runs()                      │
│  ──> Tự động loại trừ các thư mục fake_* và test_*          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Lịch Sử Dọn Dẹp Ô Nhiễm và Khôi Phục Toàn Vẹn

### 3.1. Sự Cố Trước Đó
- File test cũ `test_generic_acquisition_layer.py` đã tạo nguồn giả lập `fake_test_source` với URL `https://rentals.test/listings` trực tiếp vào thư mục `/data/bronze/`.
- Airflow Bronze Reconciler quét tự động thư mục `/data/bronze/` và đã persist nguồn giả lập này vào MySQL Production.

### 3.2. Quy Trình Khôi Phục An Toàn Đã Thực Hiện
1. **Sao Lưu Dự Phòng**: Đã tạo bản sao lưu logic đầy đủ `data/backups/mysql/pre_fake_cleanup_backup.sql`.
2. **Dọn Dẹp Đĩa Host**: Đã xóa triệt để thư mục `data/bronze/fake_test_source/`.
3. **Xóa Có Kiểm Soát (Cascade)**: Đã xóa bản ghi nền tảng `fake_test_source` trên MySQL Primary (`127.0.0.1:3307`). Do thiết lập ràng buộc khóa ngoại `ON DELETE CASCADE`, toàn bộ các bài đăng và phiên bản giả lập liên quan đã được xóa sạch.
4. **Đồng Bộ Bản Sao (Replication Verification)**: GTID Binary Log replication đã đồng bộ việc xóa này sang Replica host (`127.0.0.1:3306`) với số lượng bản ghi khớp 100% trên tất cả 12 bảng Bronze.
