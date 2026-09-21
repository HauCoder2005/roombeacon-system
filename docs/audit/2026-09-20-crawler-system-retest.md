# Kiểm thử lại crawler — 20/09/2026

Thời điểm kiểm tra runtime: khoảng 11:10–11:12 giờ Việt Nam. Phạm vi: kiểm thử host, đọc code, đọc metadata Airflow và MySQL. Không kích hoạt lượt crawl mới, không restart, không sửa dữ liệu production. Trong lượt kiểm tra này chỉ bổ sung báo cáo.

## Kết luận

Hệ thống có phân lớp tương đối rõ nhưng chưa đạt trạng thái sạch và ổn định toàn bộ. Crawler vẫn fetch được dữ liệu; chưa chứng minh luồng end-to-end hiện tại hoàn tất, chưa có geocoding tự động, và bộ test chưa xanh.

## Kiểm thử

Lệnh đã chạy:

```sh
ROOMBEACON_ENV=test BRONZE_MYSQL_DATABASE=roombeacon_bronze_test .venv/bin/python -m pytest -q --continue-on-collection-errors --tb=short
```

Kết quả: **441 passed, 15 failed, 3 collection errors, 40 subtests passed**, 16.77 giây. Log tại `/tmp/roombeacon-crawler-audit-tests.txt`.

Phân loại 15 failed theo output pytest (bao gồm subtest):

- 7 lỗi do host không cài Airflow (`airflow.exceptions` / `airflow.sdk`). Ba collection errors cũng cùng nguyên nhân. Container có Airflow nhưng không có pytest; không thay đổi môi trường container đang chạy để cài thêm.
- 3 lỗi ngân sách detail: cấu hình 5000 khác kỳ vọng 20/40. Đây là bất đồng hợp đồng cấu hình/test, không tự động chứng minh giá trị kỳ vọng là tối ưu.
- 3 lỗi persistence: nguồn kết thúc hợp lệ với 0 bài bị trả `SKIPPED_NO_DATA`; crawl khai báo thành công nhưng thiếu artifact cũng bị skip thay vì báo lỗi.
- 2 lỗi hợp đồng quyền MinIO: policy có `ListBucket` và thêm phạm vi raw objects, khác kỳ vọng object-only trong test. Cần đối chiếu yêu cầu vận hành trước khi sửa policy hoặc test.

`git diff --check` không qua: whitespace ở 9 vị trí. Workspace có 102 dòng modified/untracked tại thời điểm đo; đây là trạng thái quản lý thay đổi, không phải 102 lỗi code. Có script thử/patch nằm trong `crawler/src`.

## Runtime

Các container Airflow scheduler/API/triggerer và MySQL đang healthy. Dag processor/MinIO đang Up. Healthy không chứng minh crawler đã hoàn tất nghiệp vụ.

Lượt `scheduled__2026-09-19T17:25:00+00:00` (00:25 ngày 20/09 Việt Nam):

- DAG vẫn `running`; 9 mapped crawl tasks success, một task running.
- Task còn chạy: `04_crawl_execute_source`, map index 8, nguồn PhongTro123, `BOOTSTRAP_CONTINUE`.
- Attempt 2 bắt đầu 10:50:39 ngày 20/09 Việt Nam; heartbeat còn cập nhật lúc 11:10:41, fetch tiếp đến 11:11:41.
- Log ghi 395 lần bắt đầu fetch tại lần đọc cuối. Không thể gọi đây là task treo dựa trên bằng chứng hiện có.
- Các bước persistence/checkpoint/analytics của lượt đang chờ. Run cũ từ 00:25 không có nghĩa attempt hiện tại đã chạy liên tục hơn 10 giờ; attempt hiện tại mới chạy khoảng 21 phút.
- DAG schedule 5 phút, `max_active_runs=1`; ngân sách 5000 detail/nguồn làm lượt dài có khả năng chặn lượt mới. Chưa có benchmark đủ để quy toàn bộ thời gian dài cho duy nhất ngân sách này.
- Bốn lượt trước có trạng thái success; trong đó một lượt mất khoảng 55 phút 26 giây.

## Các vấn đề ưu tiên

1. **P1 — Ngân sách và giới hạn thời gian lượt cào.** `sources/phongtro123/adapter.py:104`, `sources/nhatrovn/adapter.py:102`, `sources/scheduled_source.py:63` đặt 5000. DAG không đặt execution timeout ngay trên task cào. Cần chia batch có giới hạn thời gian, tiếp tục bằng backlog/checkpoint, xác minh partial progress trước khi tăng throughput.
2. **P1 — Phân biệt kết thúc nguồn hợp lệ và thiếu artifact.** `application/orchestration/persistence.py:32` gộp các trường hợp thành `SKIPPED_NO_DATA`. `checkpoint.py:65` không tiến checkpoint khi persistence không success; nguồn rỗng hợp lệ vì vậy có thể bị lên lịch lặp lại. Đồng thời thiếu artifact bất thường có thể không làm task Airflow thất bại.
3. **P1 — Geocoding chưa được nối vào vận hành.** Không có bảng `map_geocodes` trong database hiện tại. Không có lời gọi `GeocodeEnrichmentJob` từ DAG/entry point khác. `v_latest_posts_enriched` là optional, thiếu cache thì bỏ qua. `v_latest_posts` gốc vẫn không dùng geocoded address. Chưa thể kết luận hệ thống đang tự chuyển Maps sang địa chỉ.
4. **P2 — Raw mirror chưa hoạt động ở persistence.** `application/orchestration/persistence.py:61` ghi `minio bypassed`, vẫn import `MinIORawArtifactMirror` nhưng trả `raw_objects_mirrored=0`. Tách biệt với task sync ảnh ở bước 8; ảnh có task riêng không chứng minh raw artifact đã mirror.
5. **P2 — Dọn code và hợp đồng test.** Script thử trong src, import không dùng, whitespace, test môi trường Airflow chưa tái lập được trên host, policy/config chưa đồng bộ với test. Không nên sửa test để chỉ đạt màu xanh mà chưa xác định hợp đồng đúng.

## Luồng hiện tại

1. Airflow 5 phút: load source → planner đọc checkpoint và chọn nguồn đến hạn.
2. Qualification: kiểm tra URL/robots/health/cooldown.
3. Crawl runner: adapter từng nguồn → discovery/listing → card → detail theo ngân sách, TTL và backlog; fetch coordinator xử lý request/retry/rate limit/browser theo chính sách.
4. Parser: title/price/area/address; Maps extractor giữ tọa độ/query. Bronze mapper tạo bản ghi nguồn và local artifacts.
5. Persistence: đọc Bronze artifacts → transaction MySQL → post/version và các bảng con. Dedupe/provenance thuộc lớp persistence.
6. Checkpoint và source health cập nhật sau persistence.
7. Refresh DuckDB views → sync assets MinIO → tổng hợp báo cáo.
8. Nhánh geocode hiện tách rời: map coordinates → job thủ công → cache MySQL → optional enriched view. Nhánh này chưa được kích hoạt trong runtime đã kiểm tra.

Điểm tốt: orchestration tách khỏi application, source adapter có trách nhiệm riêng, checkpoint nằm sau persistence, có test cho địa chỉ/provenance/cache/HTTP failure và nhiều hành vi crawl. Điểm chưa đạt: chưa có lần kiểm thử end-to-end mới hoàn tất; geocode chưa vận hành; các lỗi nêu trên chưa sửa trong lượt audit này.
