# Báo Cáo Sự Cố: Tràn Số Cột area_value Trong MySQL Bronze (DataError 1264)

## 1. Thông Tin Sự Cố

- **Ngày ghi nhận (Date)**: 2026-08-23
- **Thành phần ảnh hưởng (Component)**: Ingestion & Bronze MySQL Persistence Layer
- **DAG**: `roombeacon_crawler`
- **Task**: `persist_bronze_mysql`
- **Trạng thái (Status)**: **Đã xử lý & Xác minh Runtime (RESOLVED)**

---

## 2. Triệu Chứng

Trong các chu kỳ cào dữ liệu định kỳ của DAG `roombeacon_crawler`, task `persist_bronze_mysql` (đặc biệt là subtask map_index số 4 cho nguồn `phongtro123`) bị lỗi liên tục và thất bại với ngoại lệ từ MySQL driver:

```text
pymysql.err.DataError: (1264, "Out of range value for column 'area_value' at row 1")
[SQL: 
    INSERT INTO post_details (
        rental_post_id, rental_post_version_id, area_raw, area_value, description_raw, property_type_raw,
        furnishing_raw, deposit_raw, posted_at_raw, seller_name_raw, seller_type_raw,
        seller_phone_raw, attributes, created_at
    )
    VALUES (
        %(post_id)s, %(version_id)s, %(area_raw)s, %(area_val)s, %(desc_raw)s, %(prop_type)s, %(furnishing)s, %(deposit)s,
        %(posted_at)s, %(seller_name)s, %(seller_type)s, %(seller_phone)s, %(attributes)s, NOW()
    )
]
[parameters: {'post_id': 740701, 'version_id': 5467348, 'area_raw': '120202748m', 'area_val': 120202748.0, ...}]
```

Sự cố này khiến toàn bộ transaction lưu trữ quan sát Bronze của phiên cào bị rollback, dẫn đến việc Airflow đánh dấu task thất bại.

---

## 3. Phạm Vi Ảnh Hưởng

- **Nguồn dữ liệu bị ảnh hưởng**: Nguồn `phongtro123` (task `persist_bronze_mysql`).
- **Tác động dòng chảy dữ liệu**: Các task cào thô (fetch, discovery, extract, write local Bronze) vẫn hoàn thành bình thường. Tuy nhiên, bước ghi vào MySQL Bronze bị chặn đứng do transaction bị rollback khi gặp bản ghi lỗi.
- **Tổn thất dữ liệu**: Không có dữ liệu bị mất (No data loss). Các tệp JSON Bronze thô trên đĩa vẫn còn nguyên vẹn và cơ chế đối soát/reconciliation sẽ tự động nạp lại các quan sát này trong chu kỳ tiếp theo sau khi lỗi được khắc phục.

---

## 4. Nguyên Nhân Gốc (Root Cause)

1. **Chuỗi dữ liệu thô bị dính lỗi từ nguồn / parser**: Bài đăng trên `phongtro123` có trường diện tích thô mang giá trị `'120202748m'` (mã listing ID bị dính chữ `m`).
2. **Logic trích xuất số quá lỏng lẻo**: Phương thức `MySQLBronzeMapper.parse_numeric_area(area_raw)` trước đây chỉ đơn thuần tìm chuỗi ký số đầu tiên `(\d+(?:\.\d+)?)` và chuyển thẳng thành số thực `float(match.group(1))` $\rightarrow$ sinh ra `120202748.0` mà không hề có rào chắn kiểm tra tính hợp lý (plausibility guard).
3. **Vượt ngưỡng kiểu dữ liệu `DECIMAL(10,2)` trong MySQL**: Trong bảng `post_details`, cột `area_value` có định dạng `DECIMAL(10,2)` (tối đa 10 chữ số tổng cộng, trong đó 2 chữ số thập phân, nghĩa là tối đa 8 chữ số phần nguyên: `99,999,999.99`). Số `120,202,748.00` có 9 chữ số phần nguyên, vượt quá giới hạn cột của MySQL dẫn đến lỗi `DataError 1264 Out of range`.

---

## 5. Dữ Liệu Ví Dụ

| Trường Dữ Liệu | Trước Khi Sửa (Lỗi) | Sau Khi Sửa (Kỳ Vọng) |
| :--- | :--- | :--- |
| `area_raw` | `'120202748m'` | `'120202748m'` *(Bảo toàn 100%)* |
| `area_value` | `120202748.0` *(Tràn số)* | `NULL` |
| Kết quả INSERT | `DataError: 1264 Out of range` | `SUCCESS (Lưu thành công)` |

---

## 6. Giải Pháp Khắc Phục (Code-Level Fix)

Hệ thống đã triển khai giải pháp phòng vệ 2 lớp tại ranh giới chuẩn hóa và tầng lưu trữ:

1. **Bổ sung Plausibility Guard trong `MySQLBronzeMapper.parse_numeric_area`**:
   - Thiết lập giới hạn diện tích hợp lý cho bất động sản cho thuê tại Việt Nam: $0.5 \text{ m}^2 \le \text{area} \le 100,000.0 \text{ m}^2$ (10 ha).
   - Nếu chuỗi diện tích không chứa số, là từ khóa ("Liên hệ", "Thương lượng", "N/A"), hoặc giá trị số vượt ra ngoài khoảng hợp lý $\rightarrow$ mapper trả về `None` và ghi log cảnh báo có cấu trúc.
2. **Bổ sung Defensive Guard tại tầng Persistence (`MySQLPostChildrenRepository.persist_children`)**:
   - Trước khi thực thi câu lệnh SQL INSERT vào `post_details`, kiểm tra giá trị số của `area_val`. Nếu không phải số thực hữu hạn, số âm, hoặc vượt quá `99,999,999.99`, tự động gán `area_val = None` để MySQL lưu giá trị `NULL`.
   - Giữ nguyên vẹn 100% giá trị gốc `area_raw` (`'120202748m'`).

---

## 7. Tại Sao Không Mở Rộng Schema Database?

- Kiểu dữ liệu `DECIMAL(10,2)` cho phép lưu trữ diện tích lên tới $99,999,999.99 \text{ m}^2$ (~100 $\text{km}^2$), hoàn toàn dư sức đáp ứng cho mọi loại phòng trọ, căn hộ, biệt thự, nhà xưởng thực tế.
- Lỗi `120202748.0` phát sinh do chuỗi dữ liệu thô bị gán nhầm số ID/SĐT vào diện tích.
- Nếu mở rộng cột database sang `BIGINT` hoặc `DECIMAL(20,2)` chỉ để chấp nhận số rác này, hệ thống sẽ tự làm ô nhiễm dữ liệu phân tích và che giấu các lỗi trích xuất của parser. Ràng buộc của Database đóng vai trò là chốt chặn an toàn cuối cùng (Last Safety Guard).

---

## 8. Kiểm Thử (Testing)

Đã xây dựng bộ kiểm thử chuyên biệt tại `tests/test_area_normalization_and_persistence.py` bao phủ đầy đủ các trường hợp:
- Số nguyên hợp lệ: `"25 m²"`, `"30m2"`, `"45 m"` $\rightarrow$ `25.0`, `30.0`, `45.0`.
- Số thập phân (dấu chấm & dấu phẩy): `"25.5 m²"`, `"25,5 m²"`, `"40,75m2"` $\rightarrow$ `25.5`, `40.75`.
- Chuỗi rỗng / thiếu / không phải diện tích: `None`, `""`, `"Liên hệ"`, `"Thỏa thuận"`, `"N/A"` $\rightarrow$ `None`.
- Chuỗi tràn số dị biệt: `"120202748m"`, `"0912345678m"`, `"999999999 m2"` $\rightarrow$ `None`.
- Diện tích lớn nhưng hợp lệ: `"500 m²"`, `"2000 m2"`, `"50000 m²"` $\rightarrow$ `500.0`, `2000.0`, `50000.0`.
- Kiểm thử Persistence: `area_raw="120202748m"` được lưu giữ nguyên bản vào `post_details.area_raw` và `post_details.area_value` nhận giá trị `NULL`.
- **Toàn bộ 235 tests của dự án đều vượt qua (100% PASS)**.

---

## 9. Xác Minh Môi Trường Vận Hành (Runtime Verification)

- Đã thực hiện kiểm chứng trực tiếp việc persist một bản ghi quan sát chứa `area_raw='120202748m'` vào MySQL Bronze thực tế:
  - `inserted=1, posts_created=1` (Giao dịch hoàn tất thành công 100%, không xảy ra DataError 1264).
  - Bản ghi được lưu chính xác: `area_raw = '120202748m'`, `area_value = NULL`.
- Lệnh kiểm tra DAG import errors (`airflow dags list-import-errors`) trả về `No data found` (0 lỗi).

---

## 10. Ảnh Hưởng Tới Khoa Học Dữ Liệu (Data Science Impact)

- **Bảo toàn tính chất thô của Bronze**: `area_raw` vẫn lưu giữ chính xác chuỗi gốc từ website (`'120202748m'`).
- **Minh bạch hóa chất lượng dữ liệu**: `area_value = NULL` phản ánh đúng thực tế rằng chuỗi thô không thể chuẩn hóa an toàn thành diện tích số học.
- **Hỗ trợ Initial EDA**: Trong giai đoạn **Phase A: Initial / Data Quality EDA**, các nhà khoa học dữ liệu có thể dễ dàng lọc các bản ghi `area_raw IS NOT NULL AND area_value IS NULL` để đo lường tỷ lệ lỗi parser và thiết lập quy tắc trích xuất nâng cao.

---

## 11. Phòng Ngừa Tái Diễn (Prevention)

1. **Rào chắn kiểm tra tính hợp lý tại Mapper**: Mọi hàm parse dữ liệu số (giá tiền, diện tích) đều có ngưỡng chặn trên và chặn dưới rõ ràng.
2. **Ghi log cảnh báo có cấu trúc**: Bắn log cảnh báo `logger.warning("Area normalization out of plausible range...")` kèm metadata để dễ dàng theo dõi trên hệ thống giám sát.
3. **Phòng vệ tại tầng Repository**: Không cho phép bất kỳ giá trị không hợp lệ nào đi tới câu lệnh INSERT SQL.
4. **Bộ kiểm thử hồi quy**: Luôn duy trì các kịch bản test biên trong test suite tự động.

---

## 12. Danh Sách Tệp Đã Sửa (Files Modified)

- `crawler/src/roombeacon_crawler/infrastructure/mysql/mappers/bronze_mapper.py`
- `crawler/src/roombeacon_crawler/infrastructure/mysql/repositories/post_children_repository.py`
- `crawler/src/roombeacon_crawler/sources/phongtro123/parsers/listing_parser.py`
- `tests/test_area_normalization_and_persistence.py`
- `docs/log/README.md`
- `docs/log/2026-08-23_area-value-overflow.md`

---

## 13. Lịch Sử Tái Hiện và Kiểm Tra Chu Kỳ Scheduled (Scheduled Runtime Regression)

- **Bối cảnh**: Lần chạy `scheduled__2026-08-23T07:45:00+00:00` (thực thi lúc `07:46:45Z`) xảy ra trước khi bản vá được triển khai trên host (`07:49Z`).
- **Thông số lỗi quan sát**:
  - DAG: `roombeacon_crawler`
  - Task: `persist_bronze_mysql` (map_index 4 cho `phongtro123`)
  - `area_raw = '120202748m'`, `area_val = 120202748.0` $\rightarrow$ `pymysql.err.DataError: 1264 Out of range`.
  - Kỳ vọng: `area_raw = '120202748m'`, `area_val = None` (NULL).

---

## 14. Mô Hình Triển Khai và Kiểm Tra Runtime (Runtime Deployment Root Cause)

- **Mô hình triển khai (Deployment Model)**: Mã nguồn `crawler/src` được gắn kết dạng **Bind-Mount** trực tiếp vào container Airflow:
  ```yaml
  volumes:
    - "./crawler/src:/opt/roombeacon/crawler/src:ro"
  environment:
    PYTHONPATH: "/opt/roombeacon/crawler/src"
  ```
- **Xác thực đường dẫn Module bên trong Container**:
  - `bronze_mapper`: `/opt/roombeacon/crawler/src/roombeacon_crawler/infrastructure/mysql/mappers/bronze_mapper.py`
  - `post_children_repository`: `/opt/roombeacon/crawler/src/roombeacon_crawler/infrastructure/mysql/repositories/post_children_repository.py`
- **Kết quả kiểm thử trực tiếp trong Container**:
  - `MySQLBronzeMapper.parse_numeric_area('120202748m')` $\longrightarrow$ `None` (**Xác nhận code mới đã có hiệu lực ngay lập tức bên trong container**).

---

## 15. Quy Trình Khắc Phục Triển Khai (Deployment Correction)

- Do mô hình sử dụng Bind-Mount và LocalExecutor khởi tạo tiến trình con Python mới cho mỗi task execution, mã nguồn mới được nạp trực tiếp mà không cần rebuild container image.
- **Cam kết an toàn**:
  - KHÔNG xóa Docker volumes (`docker compose down -v` KHÔNG được gọi).
  - KHÔNG reset cơ sở dữ liệu MySQL Bronze hay Airflow metadata.
  - KHÔNG reset checkpoints cào dữ liệu.
  - KHÔNG thay đổi schema DDL cơ sở dữ liệu.

---

## 16. Xác Minh Luồng Chạy Thực Tế (Scheduled/Production Airflow Verification)

- **Phiên chạy thực tế**: `manual__2026-08-23T07:58:29.776327+00:00`
- **Kết quả thực thi các mapped tasks**:
  - `execute_crawl` map_index 0..4: **SUCCESS**
  - `persist_bronze_mysql` map_index 0..4 (bao gồm `phongtro123` map_index 4): **SUCCESS**
  - `update_checkpoint` map_index 0..4: **SUCCESS**
  - `refresh_duckdb_analytics`: **SUCCESS**
  - `summarize_run`: **SUCCESS**
  - **Lỗi `DataError 1264` tái diễn**: **KHÔNG (NO)**
- **Trạng thái sự cố**: **RESOLVED**

---

## 17. Xác Minh Lại Airflow UI Ngày 2026-08-24

- **Phân loại**: **HISTORICAL FAILURE**, không phải current regression. Airflow UI vẫn giữ task instance lỗi cũ trong lịch sử dù các run sau đã dùng bản vá.
- **Task instance lỗi cũ**:
  - `dag_id`: `roombeacon_crawler`
  - `run_id`: `scheduled__2026-08-23T07:45:00+00:00`
  - `logical_date`: `2026-08-23T07:45:00+00:00`
  - `task_id`: `persist_bronze_mysql`
  - `map_index`: `4` (`phongtro123`)
  - `try_number`: `1`
  - thời gian thực thi lỗi: `2026-08-23T07:46:45.142578Z` đến `2026-08-23T07:46:46.067672Z`
- Task instance trên chạy **trước** thời điểm triển khai area guard khoảng `2026-08-23T07:49:00Z`.
- **Run xác minh sau fix**: `manual__2026-08-23T07:58:29.776327+00:00`; `persist_bronze_mysql` map index `0..4`, bao gồm PhongTro123 map index `4`, đều `SUCCESS` và không tái diễn `DataError 1264`.
- **Run mới nhất được kiểm tra**: `scheduled__2026-08-24T02:30:00+00:00`; mọi mapped instance của `persist_bronze_mysql` trong run đều `SUCCESS`. Run này chỉ có hai target được planner chọn, nên không thay thế bằng chứng PhongTro123 của manual run nêu trên.
- Checksum SHA-256 của `bronze_mapper.py` và `post_children_repository.py` trong bind mount `/opt/roombeacon/crawler/src` khớp hoàn toàn với host; không có stale runtime source hoặc import-path divergence.
- Audit chỉ đọc 258.738 object trong Bronze artifacts ghi nhận 68 occurrence của mẫu chính xác `120202748m` và 167 candidate vượt plausibility guard; toàn bộ thuộc PhongTro123. Có 99 occurrence theo pattern khác ngoài mẫu chính xác, không phát hiện source khác. Không sửa artifact hay historical row.
- Đối chiếu aggregate trong MySQL không được thực hiện vì socket authentication từ CLI bị từ chối; không đọc credential để vượt qua giới hạn an toàn.
- **Kết luận**: không có bypass path mới và không cần sửa code. Incident tiếp tục ở trạng thái **RESOLVED**.
