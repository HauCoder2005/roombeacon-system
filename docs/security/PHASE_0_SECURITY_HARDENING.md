# RoomBeacon Phase 0 Security Hardening

Ngày hoàn thành: 2026-08-23.

## 1. Phạm vi

Phase 0 chỉ sửa bốn nhóm đã được audit: deadlock persistence correctness, SSRF trong asset downloader, DuckDB credential-safe errors và sensitive logging tại persistence/analytics/Airflow boundaries. Không refactor `CrawlRunner`, không tách DAG, không đổi schema/data pipeline.

## 2. Deadlock Persistence Correctness

Root cause: nhánh deadlock rollback rồi gọi `PersistResult()`, trong khi contract thực là `BronzeImportResult`. Call không hợp lệ đã được loại bỏ. Mỗi attempt tạo một `BronzeImportResult` mới, rollback trước retry, tối đa ba attempts, exponential backoff + jitter theo convention sẵn có. Success trả đúng result; exhausted/non-deadlock được chuyển thành `PersistenceError` an toàn và không mang raw DB exception/SQL parameters.

Focused tests bao phủ: deadlock rồi success, deadlock đến limit, non-deadlock không retry, first-attempt success và synthetic SQL-parameter marker không leak.

## 3. Asset Downloader SSRF Protection

`image_url` được coi là untrusted. Helper `security/url_safety.py`:

- chỉ cho HTTP/HTTPS; từ chối credentials trong URL;
- chặn localhost và mọi IP không `is_global`: loopback, private/ULA, link-local, multicast, reserved, unspecified;
- resolve toàn bộ A/AAAA; nếu DNS fail, empty hoặc bất kỳ address nào không public thì fail closed;
- asset downloader tắt automatic redirect, kiểm tra lại từng `Location`, giới hạn 5 redirects;
- unsafe URL thành `TERMINAL_FAILURE / SECURITY_REJECTED`; data URI giữ taxonomy `INVALID_DATA_URL`;
- request giữ TLS verification mặc định; không có `verify=False`;
- body được stream theo chunk, kiểm tra `Content-Length` nếu có và hard cap 15 MiB trước khi upload.

Fair scheduling, asset identity/object key, retry count, terminal semantics và MinIO upload contract không đổi.

Residual risk: validator resolve hostname rồi Requests resolve lại khi connect. Đây là DNS TOCTOU/rebinding window. Current implementation giảm risk bằng fail-closed all-address validation và revalidation mỗi redirect, nhưng chưa pin socket connection vào IP đã kiểm tra. Để loại bỏ hoàn toàn cần transport adapter kiểm soát DNS/connect đồng thời với TLS SNI/certificate; nằm ngoài minimal Phase 0.

## 4. DuckDB Credential-safe Error Handling

DuckDB vẫn tạo ATTACH statement nội bộ vì API hiện tại yêu cầu. Raw statement không được log. Raw ATTACH exception không còn được retain, interpolate hoặc propagate; failure chỉ log event/alias chung và tiếp tục standalone như semantics trước đây. Cả hai duplicate helpers (`analytics/...` và `crawler/src/analytics/...`) được harden nhất quán.

Test inject marker giả vào password và fake DuckDB exception echo toàn SQL; captured logs không chứa marker hoặc `password=`.

## 5. Sensitive Logging Hardening

Đã harden các boundary có rủi ro cao:

- persistence không log/chaining raw SQLAlchemy exception;
- MySQL engine initialization chỉ log operation + exception class;
- crawler Airflow persistence không log raw exception, URL hoặc failure payload;
- DuckDB refresh trả/log exception class thay vì raw exception;
- MinIO connection/count không propagate raw client exception.

Status: **PARTIAL**. Parser, sitemap và local-state paths vẫn có một số log raw exception text. Không thấy log intentional seller phone, Authorization/Cookie, full observation/model, HTTP headers hoặc runtime environment trong paths audited. Remaining sites cần một logging-only cleanup riêng với redaction tests; không mở rộng Phase 0 thành repository-wide refactor.

## 6. Test Strategy

Tests sử dụng fake repositories/transactions, mocked DNS resolver, mocked `requests.get`, fake DuckDB connection và temporary asset-state directory. Không request network, không kết nối MySQL/MinIO, không ghi `/data`, không trigger Airflow.

Kết quả:

- Phase 0 focused: 14 PASS.
- Existing asset reconciler: 10 PASS.
- Existing persistence/analytics unit subset: 7 PASS.
- Existing URL validator: 4 PASS.
- Compile/static: PASS.
- Full suite: BLOCKED BY UNSAFE CONFIG BOOTSTRAP và vì một số integration-style paths có thể dùng default development services.
- DAG import execution: BLOCKED; chỉ compile/AST-safe validation được chạy, vì import graph có eager dotenv bootstrap.

Tests được chạy từ `/tmp`, với source paths explicit, để `find_dotenv(usecwd=True)` không tìm repository `.env`.

## 7. Những gì không thay đổi

Không đổi MySQL schema/identity constraints, repositories SQL, source adapters, robots/retry/rate/source-health policies, `CrawlRunner`, DAG topology, Bronze/Silver/Gold/EDA semantics, Docker runtime hoặc production state.

## 8. Remaining Risks

1. DNS connect-time pinning chưa có; residual TOCTOU được mô tả ở trên.
2. Generic crawler fetch/sitemap paths không thuộc asset downloader và chưa áp dụng cùng outbound policy.
3. Một số raw exception logs ngoài persistence/analytics boundary còn lại.
4. Duplicate DuckDB package vẫn tồn tại; Phase 0 chỉ harden cả hai, không consolidate.
5. Asset network error string còn được lưu trong local durable state để retry diagnostics; không được operational logger emit, nhưng state access cần được giới hạn.

## 9. Acceptance

| Gate | Result |
|---|---|
| Invalid `PersistResult` call | REMOVED |
| Deadlock bounded / contract preserved | YES |
| Scheme/private/loopback/link-local/IPv6 block | PASS |
| DNS-to-private and redirect-to-private | PASS |
| Real internal requests | NONE |
| Redirect bound / response-size bound | PASS |
| Raw DuckDB ATTACH/connection string logged | NO |
| Synthetic credential marker leaked | NO |
| SQL parameter marker leaked | NO |
| Sensitive logging | PARTIAL; high-risk boundaries fixed |
| Useful operational context | YES: component/operation/source/run/error class |
| `.env` read or indirectly loaded | NO |
| Runtime environment/secrets printed | NO |
| Production data/state/schema modified | NO |

### Phase 0.5 — Config Testability & Logging

Ngày hoàn thành: 2026-08-23.

#### Config bootstrap

Root cause cũ gồm hai import side effects: `config.env.loader` tự gọi dotenv discovery/load, và `config.get_env` tự tạo toàn bộ `Environment`. `SourceSettings` cũng đọc config khi class được định nghĩa.

Remediation:

- dotenv loading được chuyển thành `load_runtime_dotenv()` và không được gọi khi import;
- `env` trở thành compatibility proxy lazy; `Environment` chỉ được tạo khi runtime code truy cập lần đầu;
- `configure_environment()` cho phép unit tests inject object explicit; `reset_environment()` cô lập cache giữa tests;
- `bootstrap_runtime_environment(load_dotenv_file=True)` chỉ được gọi explicit trong local crawler CLI, backup CLI và runtime verification script;
- Airflow/Docker không gọi dotenv bootstrap; process environment chỉ được đọc lazy khi task thực thi;
- default fields của `SourceSettings` dùng `default_factory`, không resolve config lúc import.

#### DAG import safety

Test import trực tiếp cả 5 DAG files trong khi `load_environment()` bị patch để raise nếu được gọi. Tất cả DAG import PASS, không access project runtime config, không tạo MySQL/MinIO client và không execute task. Airflow tạo DAG objects bình thường; deprecation warnings của Airflow API hiện tại không phải security blocker.

#### Logging hardening

Raw exception interpolation đã được loại khỏi parser, sitemap, local state, discovery registry/storage, fetch coordination, robots, reconciliation checkpoint/JSON discovery, analytics view/materializer và backup paths audited. Logs giữ event, source/domain/adapter/path khi an toàn, attempt/position và `error_class`; không log raw URL/payload/SQL parameters/credential/contact value.

Một số raw failure detail vẫn có thể được giữ trong internal result/state objects để điều khiển retry hoặc diagnostics; Phase 0.5 acceptance chỉ xác nhận critical operational logging paths không emit raw exception.

#### Verification

- Phase 0.5 focused config/DAG/logging: 6 PASS.
- Full regression với explicit test config và `/tmp`: 256 PASS.
- Phase 0 security tests nằm trong full regression: PASS.
- Python compile/static: PASS.
- `.env` read hoặc indirectly loaded: NO; tests xác nhận `find_dotenv/load_dotenv` không được gọi khi import.
- Production MySQL/MinIO, `/data`, Airflow task execution và production state: không được truy cập/thay đổi.
