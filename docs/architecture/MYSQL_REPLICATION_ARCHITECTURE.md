# RoomBeacon — Kiến Trúc MySQL Primary & Host Read-Only Replica

> **Trạng thái: FUTURE / NOT IMPLEMENTED.** Repository hiện không triển khai read replica như mô tả dưới đây. Không dùng tài liệu này làm runbook vận hành hiện tại; xem [Current Architecture](CURRENT_ARCHITECTURE.md).

## 1. Tổng Quan Kiến Trúc (Architectural Overview)

Hệ thống RoomBeacon triển khai mô hình cơ sở dữ liệu phân tách rõ ràng giữa **Tác vụ Ghi chính (Primary R/W)** và **Bản sao đọc phân tán cục bộ (Read-Only Replica)** nhằm đáp ứng các tiêu chuẩn:
- **Redundancy (Tính sẵn sàng & Dự phòng dịch vụ)**: Duy trì một bản sao độc lập trên host Ubuntu phục vụ truy vấn, phân tích và giảm tải trực tiếp cho Primary.
- **Physical Isolation (Tách biệt tiến trình)**: Docker `mysql-bronze` hoạt động trong container; Ubuntu Native MySQL hoạt động dưới dạng daemon systemd riêng biệt trên host. Hai tiến trình KHÔNG chia sẻ chung thư mục dữ liệu vật lý `/var/lib/mysql`.
- **GTID Binary Log Replication**: Đồng bộ bất đồng bộ chuẩn xác dựa trên Global Transaction Identifier (`SOURCE_AUTO_POSITION = 1`), loại bỏ hoàn toàn cơ chế dual-write ở tầng ứng dụng.

```mermaid
flowchart TD
    subgraph Compute_Runtime["Docker Compute Runtime"]
        AF["Airflow Orchestrator / Worker"]
        CR["Crawler / Ingestion Pipeline"]
        DK["DuckDB Analytics Engine"]
        
        MP["Docker mysql-bronze (PRIMARY)<br/>Port: 3306 (Internal) / 3307 (Host)<br/>server_id: 101<br/>gtid_mode: ON<br/>Role: READ / WRITE"]
    end

    subgraph Host_Storage["Host Physical Disk (/data)"]
        HD["${ROOMBEACON_DATA_DIR}/mysql/bronze<br/>(Bind Mount Target)"]
        BK["${ROOMBEACON_DATA_DIR}/backups/mysql/<br/>(Logical Dump Backups)"]
    end

    subgraph Host_Native["Ubuntu Host Runtime"]
        MR["Ubuntu Native MySQL (REPLICA)<br/>Host: 127.0.0.1:3306<br/>server_id: 102<br/>gtid_mode: ON<br/>read_only / super_read_only: ON<br/>Role: READ ONLY"]
        DEV["Manual Inspection / BI Queries / Ad-hoc Analytics"]
    end

    AF -->|Writes / Persists| MP
    CR -->|Persists Bronze| MP
    DK -->|ATTACH (Read-Only)| MP

    MP -->|Bind Mount / Persistence| HD
    MP -->|mysqldump Scheduled| BK
    
    MP -.->|GTID Binlog Stream (127.0.0.1:3307)| MR
    DEV -->|Read-Only SELECT| MR
```

---

## 2. Phân Định Vai Trò & Cấu Hình Thành Phần

| Thuộc tính | PRIMARY (Docker Container) | REPLICA (Ubuntu Host Native) |
| :--- | :--- | :--- |
| **Định danh dịch vụ** | `mysql-bronze` (`roombeacon-mysql-bronze`) | `mysql.service` (Systemd Daemon) |
| **Endpoint mạng** | `mysql-bronze:3306` (Docker) / `127.0.0.1:3307` (Host) | `127.0.0.1:3306` (Host localhost) |
| **Phiên bản MySQL** | `8.4.11` (MySQL 8.4 LTS) | `8.4.10` (MySQL 8.4 LTS) |
| **Server ID** | `101` | `102` |
| **GTID Mode** | `ON` (`enforce_gtid_consistency = ON`) | `ON` (`enforce_gtid_consistency = ON`) |
| **Quyền hạn ghi** | `read_only = OFF` (Toàn quyền Read/Write) | `read_only = ON`, `super_read_only = ON` |
| **Đối tượng kết nối** | Airflow, Crawler, Persistence Use Cases | Developer, Truy vấn tra cứu, Kiểm tra độc lập |
| **Lưu trữ vật lý** | `${ROOMBEACON_DATA_DIR}/mysql/bronze` (Bind mount) | `/var/lib/mysql` (Host native storage) |

---

## 3. Nguyên Tắc Thiết Kế Trọng Yếu

### 3.1. Tuyệt đối không Dual-Write ở Tầng Ứng Dụng
- Pipeline thu thập (Crawler/Airflow) **CHỈ ghi vào Docker Primary**.
- Mọi cơ chế dual-write trong mã nguồn ứng dụng (ghi đồng thời 2 database) đều bị cấm triệt để vì:
  1. Gây hiện tượng bất đồng bộ khi 1 nhánh ghi thất bại (partial failure / split state).
  2. Làm tăng độ trễ pipeline và xung đột transaction khóa dòng (Deadlock).
  3. Khiến việc khôi phục lỗi trở nên bất khả thi.
- Cơ chế đồng bộ được ủy quyền hoàn toàn cho **MySQL Binary Log GTID Engine** ở mức kernel database.

### 3.2. Replica KHÔNG Phải Là Bản Sao Lưu (Replica != Backup)
- **Cơ chế bảo vệ của Replica**: Chống sập container Docker, lỗi runtime daemon MySQL Primary, cho phép tra cứu dữ liệu độc lập mà không ảnh hưởng tải ghi của Primary.
- **Giới hạn của Replica**: Nếu Primary thực thi lệnh `DROP TABLE` hoặc `DELETE` ngoài ý muốn, transaction đó **SẼ được replicate ngay lập tức** sang Replica.
- **Chính sách Backup**: Hệ thống duy trì các bản sao lưu logic định kỳ (`mysqldump --single-transaction`) được lưu trữ tại `${ROOMBEACON_DATA_DIR}/backups/mysql/`.

### 3.3. Cảnh Báo Giới Hạn Về Ổ Đĩa Vật Lý (Host Disk Disaster Recovery)
- Do cả Docker bind-mount (`/data/mysql/bronze`) và Ubuntu Native MySQL (`/var/lib/mysql`) hiện cùng nằm trên một ổ đĩa vật lý của host, mô hình này mang lại **Service-Level Redundancy** (dự phòng dịch vụ) chứ chưa phải là **Hardware Disaster Recovery** (chống thảm họa hỏng phần cứng ổ đĩa).
- **Khuyến nghị mở rộng tương lai**: Thiết lập Replica thứ 2 trên máy chủ vật lý khác hoặc đẩy logical backup định kỳ lên MinIO/S3 từ xa.

---

## 4. Kịch Bản Sự Cố & Hướng Dẫn Khôi Phục Thủ Công (Disaster Recovery Runbook)

### Kịch Bản 1: Ubuntu Native MySQL (Replica) Bị Dừng / Gặp Sự Cố
- **Ảnh hưởng**: Primary (Docker) và Airflow pipeline **HOÀN TOÀN KHÔNG BỊ ẢNH HƯỞNG**, dữ liệu tiếp tục ghi bình thường.
- **Khôi phục**: Khởi động lại dịch vụ trên host (`sudo systemctl start mysql`). Replica sẽ tự động kết nối lại Primary tại `127.0.0.1:3307`, đọc binlog qua GTID và đuổi kịp dữ liệu mới (`Seconds_Behind_Source = 0`).

### Kịch Bản 2: Docker MySQL (Primary) Bị Hỏng Container Hoặc Mất Dịch Vụ
- **Ảnh hưởng**: Airflow pipeline tạm thời dừng ghi. Replica trên host vẫn chứa đầy đủ dữ liệu đọc tính đến thời điểm giao dịch cuối cùng được replicate.
- **Quy trình thăng cấp thủ công (Manual Promotion - Tránh Split-Brain)**:
  1. Đảm bảo Primary cũ đã tắt hoàn toàn: `docker compose stop mysql-bronze`.
  2. Trên Ubuntu Replica, tắt chế độ Read-Only:
     ```sql
     STOP REPLICA;
     RESET REPLICA ALL;
     SET GLOBAL read_only = OFF;
     SET GLOBAL super_read_only = OFF;
     ```
  3. Cập nhật cấu hình cổng/kết nối trong `.env` để trỏ `BRONZE_MYSQL_PORT=3306` nếu cần chuyển hướng ứng dụng.
  4. Sau khi sự cố được khắc phục, khởi tạo lại mô hình Primary - Replica theo chiều ngược lại hoặc đồng bộ lại snapshot.
