# RoomBeacon Reset and Restore Operations

Script vận hành: `scripts/reset_roombeacon_data.py`. Wrapper host:
`scripts/run_reset_roombeacon.sh`.

Reset chạy **bên trong Airflow scheduler container hiện có** để tái sử dụng đúng
runtime configuration và Docker network của RoomBeacon. Operator không truyền
database host, username, password, replica socket hoặc MinIO credential. Script
không đọc `.env`; config runtime được application bootstrap sẵn trong container.

```text
Host operator
  └─ run_reset_roombeacon.sh
       └─ Airflow scheduler runtime
            ├─ MySQL Bronze primary (runtime config)
            ├─ /data crawler state
            └─ Airflow CLI

MySQL primary ── replication infrastructure ──> optional read-only replica
```

Replica là infrastructure concern để monitoring/failover. Nó không phải dependency
của crawler, backup hoặc reset. Reset tool không kết nối và không ghi replica.

MinIO object binaries cũng nằm ngoài reset scope. Reset không xóa bucket/object,
không cần MinIO authentication và không tạo inventory gate. Orphan cleanup là một
maintenance workflow riêng, có retention và audit riêng.

## Modes

```text
--dry-run
  verify runtime config → verify writable roombeacon_bronze primary/schema
  không backup, pause DAG, ghi database hoặc xóa filesystem

--backup-only
  verify primary → MySQL logical dump + crawler state backup → checksum verify
  không pause DAG và không reset

--confirm-reset-roombeacon
  verify primary → verified backup → pause/verify idle writers
  → reset primary business tables + application filesystem state → verify zero

--trigger-recrawl
  chỉ hợp lệ cùng --confirm-reset-roombeacon; unpause và trigger DAG
  roombeacon_crawler sau khi reset đã verify thành công
```

## Backup contract

Mỗi `reset_<timestamp>` bắt đầu với `BACKUP_MANIFEST.json` có trạng thái
`PARTIAL_UNVERIFIED`. Failure giữ nguyên trạng thái đó. Chỉ sau khi dump MySQL,
copy state và checksum read-back thành công, trạng thái mới là `VERIFIED`.

Valid backup set gồm:

- MySQL Bronze logical dump;
- crawler checkpoint, frontier và deferred-detail state trong `/data/state`;
- discovery state;
- run manifests;
- `SHA256SUMS.json` và verified manifest.

MinIO không nằm trong backup contract này vì reset không thay đổi MinIO objects.
Backup directory không nằm trong filesystem delete scope.

## Reset scope and fail-closed gates

MySQL reset chỉ áp dụng các Bronze business tables được liệt kê explicit trong
script. Nó giữ nguyên schema và Airflow metadata. Filesystem reset chỉ áp dụng:
`bronze`, `state`, `discovery`, `manifests` dưới configured data root. Không xóa
volume, backup hoặc MinIO data.

Destructive work không chạy nếu:

- runtime database không phải `roombeacon_bronze` writable primary;
- schema identity check thất bại;
- logical backup/copy/checksum không VERIFIED;
- mutating Airflow DAG vẫn còn active run;
- target filesystem vượt configured data root.

## Operator procedure

Chạy từ repository root. Không thêm credential hoặc network override vào command.

1. Read-only dry-run:

   ```bash
   bash scripts/run_reset_roombeacon.sh --dry-run
   ```

   Chỉ tiếp tục khi report là `DRY_RUN_READY`, `primary_verified: true`,
   `replica_dependency: false`, `minio_dependency: false`.

2. Tạo và verify backup, không reset:

   ```bash
   bash scripts/run_reset_roombeacon.sh --backup-only
   ```

   Chỉ chấp nhận report `BACKUP_COMPLETE` và manifest `VERIFIED`.

3. Actual reset cần authorization vận hành riêng:

   ```bash
   bash scripts/run_reset_roombeacon.sh --confirm-reset-roombeacon
   ```

4. Nếu muốn bắt đầu crawl chuẩn ngay sau verified reset:

   ```bash
   bash scripts/run_reset_roombeacon.sh \
     --confirm-reset-roombeacon \
     --trigger-recrawl
   ```

Không chạy bước 3 hoặc 4 trong readiness/audit task. Không dùng partial backup làm
restore point.
