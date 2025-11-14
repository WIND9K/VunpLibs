# OnusLibs v3 – Tổng quan

OnusLibs là thư viện **REST-first** để làm việc với hệ thống Cyclos/ONUS:

- Gọi API qua **1 facade duy nhất**: `fetch_json`.
- Ẩn toàn bộ phức tạp về:
  - HTTP client (timeout, HTTP/2, proxy, verify_ssl),
  - Token & bảo mật (Keyring hoặc ENV),
  - Rate-limit & max-inflight,
  - Phân trang theo header Cyclos,
  - Cắt nhỏ `datePeriod` theo giờ (segment) khi cần,
  - Dedupe dữ liệu khi phân trang/segment.
- Cung cấp module **DB** dùng chung cơ chế bảo mật (Keyring) với API:
  - Config DB từ Keyring,
  - Healthcheck, query, execute, bulk_insert,
  - Decorator `@transactional` cho giao dịch.

Mục tiêu: **App chỉ lo business**, còn hạ tầng (API/DB) do OnusLibs lo.

---

## Kiến trúc & module chính

### 1. `config.settings.OnusSettings`

Đọc config từ ENV + `.env`:

- `ONUSLIBS_BASE_URL` – bắt buộc (ví dụ: `https://wallet.vndc.io`)
- `ONUSLIBS_PAGE_SIZE`
- `ONUSLIBS_REQ_PER_SEC`
- `ONUSLIBS_MAX_INFLIGHT`
- `ONUSLIBS_TIMEOUT_S`
- `ONUSLIBS_HTTP2`
- `ONUSLIBS_VERIFY_SSL`
- `ONUSLIBS_PROXY`
- `ONUSLIBS_PARALLEL`
- `ONUSLIBS_DATE_SEGMENT_HOURS`
- `ONUSLIBS_SEGMENT_PARALLEL`, `ONUSLIBS_SEGMENT_MAX_WORKERS` (dự phòng cho tương lai)
- `ONUSLIBS_SECRETS_BACKEND` (`keyring`|`env`)
- `ONUSLIBS_KEYRING_SERVICE`, `ONUSLIBS_KEYRING_ITEM`
- `ONUSLIBS_FALLBACK_ENV`
- `ONUSLIBS_TOKEN_HEADER`
- `ONUSLIBS_LOG_LEVEL`, `ONUSLIBS_AUTO_DOTENV`, …

### 2. `security.headers.build_headers`

- Lấy token từ **Keyring** (service `ONUSLIBS_KEYRING_SERVICE`, item `ONUSLIBS_KEYRING_ITEM`),  
  hoặc từ ENV nếu `ONUSLIBS_FALLBACK_ENV=true`.
- Build headers chuẩn:
  - `Access-Client-Token: <token>`
  - `User-Agent: OnusLibs/3 (Python x.y.z)`
  - Merge thêm `extra_headers` nếu caller truyền.

### 3. `http.client.HttpClient`

- Wrapper quanh `httpx`:
  - base_url từ `OnusSettings.base_url`,
  - timeout, verify_ssl, HTTP/2, proxy,
  - (tuỳ config) limiter dựa trên `req_per_sec` & `max_inflight`.
- API cơ bản:
  - `get(path, params=None, headers=None)`
  - (có thể có `post/put/delete`, tuỳ implementation thư viện của bạn).

### 4. `pagination.header_pager.HeaderPager`

- Phân trang theo **header chuẩn Cyclos**:
  - `X-Has-Next-Page`
  - `X-Page-Count`
  - `X-Total-Count`
- Tự điều khiển `page=0..N-1`.
- API:
  - `HeaderPager(client, endpoint, params, headers, page_size)`
  - `fetch_all()` → Iterable các payload (mỗi page).

### 5. `pagination.parallel_pager` (tuỳ chọn, nếu cài)

- `header_fetch_all_parallel`:
  - Dùng `ThreadPoolExecutor` fetch nhiều page song song.
  - Giới hạn bằng `workers` hoặc `ONUSLIBS_MAX_INFLIGHT`.
- Nếu không import được → OnusLibs tự fallback về `HeaderPager` tuần tự.

### 6. `unified.api.fetch_json` – Facade duy nhất

Hàm trung tâm để đọc JSON từ API:

```python
from onuslibs.unified.api import fetch_json
```

- Nhận:
  - `endpoint`, `params`,
  - `fields`, `order_by`, `unique_key`,
  - `page_size`, `paginate`,
  - `strict_fields`, `on_batch`,
  - `parallel` (hoặc đọc từ `ONUSLIBS_PARALLEL`),
  - `settings`, `client`, …
- Tự:
  - Gắn `fields` → `params["fields"]`,
  - Gắn `order_by` → `params["orderBy"]` (nếu có),
  - Xử lý `page`, `pageSize`,
  - Phân trang bằng header,
  - (Nếu bật segment) cắt `datePeriod` thành nhiều khung giờ và gọi nhiều window,
  - Dedupe theo `unique_key` toàn dataset,
  - Gom kết quả thành `List[Dict]`.

### 7. `utils.date_utils.build_date_period`

Helper chung để build `datePeriod`:

```python
from onuslibs.utils.date_utils import build_date_period

date_period = build_date_period("2025-10-11", "2025-10-11")
# -> "2025-10-11T00:00:00.000,2025-10-11T23:59:59.999"
```

- Nhận `start_date`, `end_date` (string `"YYYY-MM-DD"` hoặc `datetime.date`).
- Trả về `datePeriod` full-day, chuẩn dùng cho mọi endpoint có filter thời gian.

---

# Module DB – Kết nối & thao tác CSDL

Module DB của OnusLibs được thiết kế để:

- **Dùng chung cơ chế bảo mật** với API:
  - DB password, host, user… lấy từ **Keyring** (cùng service `OnusLibs`).
- Cung cấp API đơn giản, đủ dùng cho:
  - Healthcheck,
  - Query (SELECT),
  - Execute (INSERT/UPDATE/DELETE),
  - Bulk insert,
  - Transaction với decorator `@transactional`.

> Mục tiêu: ETL mini / báo cáo (như OnusReport) có thể dùng OnusLibs cho cả **API** và **DB** mà không tự xử lý secret.

## 1. Cấu hình secret DB

Khuyến nghị lưu thông tin DB vào **Keyring**:

Ví dụ (PowerShell):

```powershell
$svc="OnusLibs"

python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_HOST','127.0.0.1')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PORT','3306')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_USER','onusreport')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PASSWORD','xxx')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_NAME','onusreport')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_SSL_CA','')"  # nếu không dùng SSL
```

- `ONUSLIBS_KEYRING_SERVICE` và `ONUSLIBS_KEYRING_ITEM` dùng cho token API,  
  còn DB có thể dùng key riêng (`DB_HOST`, `DB_USER`, …) trong cùng service.

## 2. DbSettings.from_secure

Trong module DB (ví dụ `onuslibs.db.settings`):

```python
from onuslibs.db import DbSettings

db_settings = DbSettings.from_secure(
    service="OnusLibs",   # trùng ONUSLIBS_KEYRING_SERVICE
    host_key="DB_HOST",
    port_key="DB_PORT",
    user_key="DB_USER",
    password_key="DB_PASSWORD",
    name_key="DB_NAME",
    ssl_ca_key="DB_SSL_CA",    # optional
)
```

- `DbSettings.from_secure`:
  - Đọc các key tương ứng trong Keyring (theo service).
  - Trả về object DbSettings chứa thông tin kết nối DB.

## 3. API DB: healthcheck, query, execute, bulk_insert

Tùy cách bạn tổ chức module, pattern khuyến nghị:

```python
from onuslibs.db import connect, healthcheck, query, execute, bulk_insert

# 1) Kết nối
conn = connect(db_settings)

# 2) Healthcheck
healthcheck(conn)  # raise hoặc trả True/False tùy implementation

# 3) Query (SELECT)
rows = query(conn, "SELECT * FROM my_table WHERE id = %s", (123,))

# 4) Execute (INSERT/UPDATE/DELETE)
execute(conn, "UPDATE my_table SET status = %s WHERE id = %s", ("OK", 123))

# 5) Bulk insert
rows_to_insert = [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
]
bulk_insert(conn, table="users", rows=rows_to_insert, columns=["id", "name"])
```

- `query` trả về list dict (nếu có mapping), hoặc tuple rows tuỳ cách bạn implement.
- `bulk_insert` nên dùng `executemany` / batch để tối ưu.

## 4. Decorator `@transactional`

Cho phép bạn bọc logic trong 1 transaction:

```python
from onuslibs.db import transactional, connect

conn = connect(db_settings)

@transactional(conn)
def process_user(cur, user_id: int):
    # cur là cursor/connection (tuỳ implement)
    # Thực hiện nhiều câu lệnh SQL
    cur.execute("UPDATE users SET status = %s WHERE id = %s", ("ACTIVE", user_id))
    cur.execute("INSERT INTO logs(user_id, action) VALUES (%s, %s)", (user_id, "activate"))

# Gọi
process_user(123)
```

- Nếu không có exception → commit.
- Nếu có exception → rollback.

> Với pattern này, pipeline kiểu OnusReport (ETL mini) có thể:
> - dùng `fetch_json` để lấy dữ liệu từ API,
> - dùng module DB để insert/update dữ liệu vào MySQL một cách an toàn.

---

# Facade `fetch_json` – Cách dùng chi tiết

```python
from onuslibs.unified.api import fetch_json
```

### Chữ ký (tóm tắt)

```python
rows = fetch_json(
    endpoint: str,
    params: dict | None = None,
    *,
    fields: list[str] | str | None = None,
    page_size: int | None = None,
    paginate: bool = True,
    order_by: str | None = None,
    strict_fields: bool = False,
    unique_key: str | None = None,
    settings: OnusSettings | None = None,
    on_batch: callable | None = None,
    client: HttpClient | None = None,
    pager_func: callable | None = None,
    extra_headers: dict | None = None,
    parallel: bool | None = None,
    workers: int | None = None,
) -> list[dict]
```

### Nhóm param **app** cần quan tâm

- `endpoint`: path endpoint (không bao gồm base_url).
- `params`:
  - Mọi query param business (`transferTypes`, `user`, `chargedBack`, …)
  - `datePeriod` (nên dùng `build_date_period` để ghép).
- `fields`: list hoặc CSV, OnusLibs sẽ gắn vào `params["fields"]`.
- `order_by`: optional, gắn vào `params["orderBy"]`.
- `unique_key`: tên field dedupe (ví dụ `"transactionNumber"`).

### Phân trang & parallel

- `page_size`:
  - `None` → `ONUSLIBS_PAGE_SIZE`.
  - Set giá trị → override.
- `paginate`:
  - `True` → phân trang (HeaderPager/parallel_pager).
  - `False` → GET 1 lần.
- `parallel`:
  - `None` → đọc từ `ONUSLIBS_PARALLEL`.
  - `True`/`False` → ép bật/tắt page-parallel cho call hiện tại.

### strict_fields & on_batch

- `strict_fields=True`:
  - Check thiếu field top-level (theo `fields`) → log warning.
- `on_batch(batch)`:
  - Được gọi sau mỗi batch (page/segment) đã dedupe.
  - Các batch vẫn được gom vào kết quả trả về (trừ khi bạn bỏ qua `rows` và chỉ dùng on_batch).

---

# Helper `build_date_period`

```python
from onuslibs.utils.date_utils import build_date_period

date_period = build_date_period(start_date, end_date)
```

- `start_date`, `end_date`:
  - `"YYYY-MM-DD"` hoặc `datetime.date`.
- Output:
  - `"YYYY-MM-DDT00:00:00.000,YYYY-MM-DDT23:59:59.999"`.

App pattern chuẩn:

```python
params = {
    "transferTypes": "...",
    "datePeriod": build_date_period("2025-11-11", "2025-11-11"),
    "user": "",
}
rows = fetch_json(
    endpoint="/api/transfers",
    params=params,
    fields=[...],
    unique_key="transactionNumber",
)
```

---

# CLI — Tham số chi tiết & `-h/--help`

Các script CLI trong `examples/` đều dùng **argparse**, vì vậy luôn có trợ giúp:

```bash
python -m examples.fetch_commission_history -h
python -m examples.get_commission -h
python -m examples.pro_vndc_send -h
```

Dưới đây là tóm tắt những script chính.

---

## `examples.fetch_commission_history`

Kéo lịch sử hoa hồng theo ngày/khoảng ngày.  
App build `params` từ CLI, còn `fetch_json(...)` lo phân trang/lấy dữ liệu.

**Flags chính**

- `--date YYYY-MM-DD`  
  Lấy dữ liệu trong **1 ngày** (00:00:00 → 23:59:59).
- `--start-date YYYY-MM-DD` `--end-date YYYY-MM-DD`  
  Lấy dữ liệu trong **khoảng ngày** (bao gồm cả ngày cuối).
- `--preset {minimal,basic,full}` *(mặc định: `basic`)*  
  Bộ `fields` có sẵn:
  - `minimal`: rất ít field, dùng kiểm nhanh.
  - `basic`: đủ field cho phân tích thường ngày.
  - `full`: đầy đủ hơn (tuỳ script).
- `--fields a,b,c` | `--fields-file path.txt`  
  Ghi đè/thêm `fields` (CSV hoặc file mỗi dòng 1 field).
- `--page-size N`  
  Ghi đè `pageSize` cho lần chạy này. Nếu không đặt, lấy từ `ONUSLIBS_PAGE_SIZE`.
- `--order {dateAsc,dateDesc}`  
  Gửi lên API qua `orderBy`.
- `--filters <transferFilters>`  
  Gửi lên API `transferFilters`, ví dụ: `vndc_commission_acc.commission_buysell`.
- `--charged-back {true,false}`  
  Gửi lên API `chargedBack`.
- `--out-json file.json` / `--out-csv file.csv`  
  Xuất dữ liệu ra file (CSV dùng helper flatten dot-path).

**Flags phân trang/hiệu năng**

- `--parallel`  
  Bật **đọc song song** các trang (song song theo page).  
- `--workers N`  
  Số luồng khi `--parallel` (mặc định lấy từ `ONUSLIBS_MAX_INFLIGHT`).
- `--page-size N`  
  (nhắc lại) Kích thước trang – ảnh hưởng trực tiếp đến số trang và lỗi 422.

**Flags debug (test)**

- `--debug-flow`  
  In log từng trang để quan sát.
- `--delay-ms N`  
  Ngủ N ms trước mỗi request (dễ xem log).
- `--max-pages N`  
  Giới hạn số trang để demo/kiểm thử.
- `--print-total`  
  In tổng record sau khi gom.

**Ví dụ**

```bash
# 1 ngày, preset basic, tuần tự
python -m examples.fetch_commission_history   --date 2025-10-11 --preset basic --page-size 2000

# Quan sát tuần tự: log + delay + limit 5 page
python -m examples.fetch_commission_history   --date 2025-10-11 --preset basic   --page-size 400 --debug-flow --delay-ms 300 --max-pages 5

# Đa luồng (nếu endpoint an toàn, orderBy ổn định)
python -m examples.fetch_commission_history   --date 2025-10-11 --preset basic   --page-size 2000 --parallel --workers 4
```

---

## `examples.get_commission`

Phiên bản gọn, tập trung **xuất JSON nhanh**.

**Flags chính**

- `--date` **hoặc** `--start-date/--end-date`
- `--preset {minimal,basic,full}`
- `--fields a,b,c` | `--fields-file path.txt`
- `--page-size N`
- `--order {dateAsc,dateDesc}`
- `--filters <transferFilters>`
- `--charged-back {true,false}`
- `--out-json file.json`

**Ví dụ**

```bash
python -m examples.get_commission   --date 2025-10-11   --preset full   --page-size 2000   --out-json commission_2025-10-11.json
```

---

## `examples.pro_vndc_send`

Test API:

```text
GET /api/transfers
  ?transferTypes=vndcacc.vndc_offchain_send_onuspro
  &amountRange=
  &datePeriod=...T00:00:00.000,...T23:59:59.999
  &user=
  &pageSize=...
  &fields=transactionNumber,date,amount,from.user.id,from.user.display,to.user.id,to.user.display,type.internalName
```

**Flags chính**

- `--date YYYY-MM-DD`  
  Ngày cần lấy giao dịch `vndc_offchain_send_onuspro`.
- `--limit-print N`  
  Số dòng in demo ra màn hình (mặc định 5).
- `--json`  
  In toàn bộ kết quả ra stdout dạng JSON 1 dòng.

Script dùng:

- `build_date_period(day, day)` để build `datePeriod`,
- `fetch_json` với:
  - `endpoint="/api/transfers"`,
  - `params = {transferTypes, amountRange, datePeriod, user}`,
  - `fields` chuẩn như trên,
  - `unique_key="transactionNumber"`.

**Ví dụ**

```bash
python -m examples.pro_vndc_send --date 2025-11-11 --limit-print 10
python -m examples.pro_vndc_send --date 2025-11-11 --json > pro_vndc_send_2025-11-11.json
```

---

## Biến ENV (tóm tắt)

- Bắt buộc:
  - `ONUSLIBS_BASE_URL`

- Hiệu năng & HTTP:
  - `ONUSLIBS_PAGE_SIZE`
  - `ONUSLIBS_REQ_PER_SEC`
  - `ONUSLIBS_MAX_INFLIGHT`
  - `ONUSLIBS_TIMEOUT_S`
  - `ONUSLIBS_HTTP2`
  - `ONUSLIBS_VERIFY_SSL`
  - `ONUSLIBS_PROXY`

- Parallel & segment:
  - `ONUSLIBS_PARALLEL`
  - `ONUSLIBS_DATE_SEGMENT_HOURS`
  - `ONUSLIBS_SEGMENT_PARALLEL` (tương lai)
  - `ONUSLIBS_SEGMENT_MAX_WORKERS` (tương lai)

- Bảo mật:
  - `ONUSLIBS_SECRETS_BACKEND=keyring|env`
  - `ONUSLIBS_KEYRING_SERVICE=OnusLibs`
  - `ONUSLIBS_KEYRING_ITEM=ACCESS_CLIENT_TOKEN`
  - `ONUSLIBS_FALLBACK_ENV=true|false`
  - Các key DB trong Keyring: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL_CA`…
