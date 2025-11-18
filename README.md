# OnusLibs v3 – Tổng quan

OnusLibs là thư viện **REST-first** để làm việc với hệ thống Cyclos/ONUS:

- Gọi API qua **1 facade duy nhất**: `fetch_json`.
- Ẩn toàn bộ phức tạp:
  - HTTP client (timeout, HTTP/2, proxy, verify_ssl),
  - Token & bảo mật (Keyring hoặc ENV),
  - Rate-limit & max-inflight,
  - Phân trang theo header Cyclos,
  - Cắt nhỏ `datePeriod` bằng **hybrid auto-segment** (chia theo ngày + số dòng) khi dữ liệu lớn,
  - Dedupe dữ liệu khi phân trang/segment.
- Cung cấp module **DB** dùng chung cơ chế bảo mật (Keyring) với API:
  - Config DB từ Keyring / ENV,
  - Healthcheck, query, execute, bulk_insert.

Mục tiêu: **App chỉ lo business**, còn hạ tầng (API/DB) do OnusLibs lo.

---

## 1. Kiến trúc & module chính

### 1.1. `config.settings.OnusSettings`

Đọc config từ ENV + `.env`, gom vào 1 object:

- HTTP & runtime:
  - `ONUSLIBS_BASE_URL` – bắt buộc (vd: `https://wallet.vndc.io`)
  - `ONUSLIBS_PAGE_SIZE`
  - `ONUSLIBS_REQ_PER_SEC`
  - `ONUSLIBS_MAX_INFLIGHT`
  - `ONUSLIBS_TIMEOUT_S`
  - `ONUSLIBS_HTTP2`
  - `ONUSLIBS_VERIFY_SSL`
  - `ONUSLIBS_PROXY`
  - `ONUSLIBS_PARALLEL` – phân trang song song theo page.

- **Hybrid auto-segment (v3):**
  - `ONUSLIBS_MAX_WINDOW_DAYS` – chia `datePeriod` lớn thành nhiều “cửa sổ ngày” (vd: 1 ngày / window).
  - `ONUSLIBS_MAX_ROWS_PER_WINDOW` – trần số record ước tính / window (dựa `X-Total-Count`).
  - `ONUSLIBS_AUTO_SEGMENT` – bật/tắt auto-segment (mặc định `true`).
  - `ONUSLIBS_MAX_SEGMENT_SPLIT_DEPTH` – số lần chia đôi tối đa khi fallback 422.
  - `ONUSLIBS_SEGMENT_PARALLEL`, `ONUSLIBS_SEGMENT_MAX_WORKERS` – chạy nhiều segment thời gian song song.

- Legacy:
  - `ONUSLIBS_DATE_SEGMENT_HOURS` – cấu hình segment theo giờ **cũ** (giữ lại cho code legacy, `fetch_json` v3 không dùng).

- Bảo mật & logging:
  - `ONUSLIBS_SECRETS_BACKEND` (`keyring`|`env`)
  - `ONUSLIBS_KEYRING_SERVICE`, `ONUSLIBS_KEYRING_ITEM`
  - `ONUSLIBS_FALLBACK_ENV`
  - `ONUSLIBS_TOKEN_HEADER`
  - `ONUSLIBS_LOG_LEVEL`, `ONUSLIBS_AUTO_DOTENV`, …

---

### 1.2. `security.headers.build_headers`

- Lấy token từ **Keyring**:
  - Service: `ONUSLIBS_KEYRING_SERVICE` (vd: `OnusLibs`)
  - Item: `ONUSLIBS_KEYRING_ITEM` (vd: `ACCESS_CLIENT_TOKEN`)
- Hoặc đọc token từ ENV nếu `ONUSLIBS_FALLBACK_ENV=true`.
- Trả về headers chuẩn:
  - `Access-Client-Token: <token>`
  - `User-Agent: OnusLibs/3 (Python x.y.z)`
  - Các header khác nếu cần.

---

### 1.3. `http.client.HttpClient`

Wrapper trên `httpx`:

- base_url = `OnusSettings.base_url`
- timeout, verify_ssl, HTTP/2, proxy
- Rate-limit theo `req_per_sec`, giới hạn song song theo `max_inflight`.

API cơ bản:

```python
resp = client.get("/api/...", params=params, headers=headers)
```

Tất cả các request trong OnusLibs đi qua HttpClient.

---

### 1.4. `pagination.header_pager.HeaderPager`

Phân trang theo chuẩn header Cyclos:

- `X-Has-Next-Page`
- `X-Page-Count`
- `X-Total-Count`

API:

```python
from onuslibs.pagination.header_pager import HeaderPager

pager = HeaderPager(client, endpoint, params, headers, page_size=2000)
for batch in pager.fetch_all():
    ...
```

---

### 1.5. `pagination.parallel_pager` (tuỳ chọn)

Nếu cài thêm module song song:

- `header_fetch_all_parallel`:
  - Dùng `ThreadPoolExecutor` để fetch nhiều page song song.
  - Giới hạn bởi `workers` hoặc `ONUSLIBS_MAX_INFLIGHT`.
- Nếu module này không tồn tại → tự động fallback về `HeaderPager` tuần tự.

---

### 1.6. `unified.api.fetch_json` – Facade duy nhất

Hàm trung tâm để đọc JSON từ API:

```python
from onuslibs.unified.api import fetch_json
```

**Chữ ký tóm tắt:**

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

**Behaviour chính:**

- Đọc `OnusSettings` (ENV-first).
- Chuẩn hoá `params`:
  - `fields` (list → CSV),
  - `order_by` → `params["orderBy"]`,
  - `pageSize` nếu cần.
- Nếu **không có** `datePeriod` hoặc `paginate=False`:
  - Gọi `_fetch_single_window` – không auto-segment.
- Nếu **có** `datePeriod` + `paginate=True`:
  - Áp dụng **hybrid auto-segment v3** (xem phần 2).
- Dedupe theo `unique_key` trên toàn dataset (cross-window / cross-segment).
- Gom kết quả thành `List[Dict]`.
- Nếu có `on_batch`:
  - Gọi `on_batch(batch)` sau mỗi batch (page/segment) đã dedupe.

---

### 1.7. `utils.date_utils.build_date_period`

Helper build `datePeriod` full-day:

```python
from onuslibs.utils.date_utils import build_date_period

date_period = build_date_period("2025-10-11", "2025-10-11")
# -> "2025-10-11T00:00:00.000,2025-10-11T23:59:59.999"
```

Pattern chuẩn trong app:

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

## 2. Hybrid auto-segment v3

Hybrid auto-segment giải quyết bài toán:

- `datePeriod` dài,
- nhiều record,
- API giới hạn ~10k record / window → dễ dính 422 “kinh điển” nếu đi quá nhiều page.

### 2.1. Biến ENV liên quan

- `ONUSLIBS_MAX_WINDOW_DAYS`
  - Chia `datePeriod` lớn thành nhiều **cửa sổ ngày**.
  - Ví dụ: `1` → mỗi window tối đa 1 ngày.

- `ONUSLIBS_MAX_ROWS_PER_WINDOW`
  - Trần số record ước tính mỗi window (dựa `X-Total-Count`).
  - Ví dụ: `8000` (nhỏ hơn 10k để an toàn).

- `ONUSLIBS_AUTO_SEGMENT`
  - Bật/tắt hybrid auto-segment (mặc định `true`).

- `ONUSLIBS_MAX_SEGMENT_SPLIT_DEPTH`
  - Giới hạn số lần chia đôi khi fallback 422 (vd: 4).

- `ONUSLIBS_SEGMENT_PARALLEL`, `ONUSLIBS_SEGMENT_MAX_WORKERS`
  - Cho phép xử lý các segment thời gian song song.

> `ONUSLIBS_DATE_SEGMENT_HOURS` chỉ còn cho legacy, **fetch_json v3 không dùng**.

---

### 2.2. Luồng 3 tầng

**Tầng 1 – chia theo ngày (`MAX_WINDOW_DAYS`)**

- Input: `datePeriod = [start, end]`.
- Nếu `MAX_WINDOW_DAYS > 0`:
  - Cắt thành nhiều `window = [w_start, w_end]` sao cho `w_end - w_start <= MAX_WINDOW_DAYS`.
- Nếu `MAX_WINDOW_DAYS = 0`:
  - Không chia → 1 window = toàn `datePeriod`.

**Tầng 2 – chia theo số dòng (`MAX_ROWS_PER_WINDOW`)**

Cho mỗi `window`:

1. Peek `X-Total-Count` 1 lần:
   - Gửi request với:
     - `datePeriod = window`,
     - `page=0`,
     - `pageSize = eff_page_size` (từ `page_size arg` hoặc `ONUSLIBS_PAGE_SIZE`).
   - Đọc header `X-Total-Count = total_rows`.

2. Quyết định:

- Nếu:
  - `auto_segment=False`, hoặc
  - `MAX_ROWS_PER_WINDOW <= 0`, hoặc
  - không đọc được `X-Total-Count`,
  → giữ nguyên window (không chia).

- Nếu `total_rows <= MAX_ROWS_PER_WINDOW`:
  → window trở thành 1 segment.

- Nếu `total_rows > MAX_ROWS_PER_WINDOW`:
  - Tính: `n_segments = ceil(total_rows / MAX_ROWS_PER_WINDOW)`.
  - Chia `window` thành `n_segments` đoạn bằng nhau theo **thời gian**.

Ví dụ:

- `MAX_ROWS_PER_WINDOW = 8000`
- `total_rows = 21594`
- `n_segments = ceil(21594 / 8000) = 3`
  → Mỗi segment ~ 7k–8k record.

Kết quả:

- Với `pageSize = 2000`, mỗi segment cần tối đa ~4 page.
- Không chạm page quá cao → giảm nguy cơ 422 do giới hạn 10k record.

**Tầng 3 – fallback 422 (`MAX_SEGMENT_SPLIT_DEPTH`)**

Nếu khi fetch segment vẫn gặp lỗi **pagination 422**:

- Hàm `_run_with_split(seg_start, seg_end, depth)`:

  1. Thử `_run_window(seg_start, seg_end)`:
     - Nếu OK → dùng kết quả.

  2. Nếu lỗi:
     - Chỉ xử lý tiếp nếu:
       - `auto_segment=True`,
       - `MAX_SEGMENT_SPLIT_DEPTH > 0`,
       - lỗi đúng pattern “Pagination error … 422”.
     - Nếu không thoả → raise lại lỗi.

  3. Nếu 422 và `depth >= MAX_SEGMENT_SPLIT_DEPTH`:
     - Log error: “reached max split depth … nhưng API vẫn trả 422”.
     - Raise → **không âm thầm bỏ qua data**.

  4. Nếu 422 và còn quota depth:
     - Chia đôi thời gian: `mid = (seg_start + seg_end)/2`.
     - Gọi `_run_with_split(seg_start, mid, depth+1)` và `_run_with_split(mid, seg_end, depth+1)`.
     - Gộp kết quả 2 bên.

---

## 3. Dedupe & song song

### 3.1. Dedupe theo `unique_key`

- `fetch_json` nhận tham số `unique_key` (vd: `"transactionNumber"`).
- Khi gom data từ nhiều segment:
  - Dùng `set` lưu các key đã gặp.
  - Bỏ qua record có key trùng.
- Đảm bảo không bị duplicate khi segment/time bị overlap.

### 3.2. `on_batch`

- Nếu truyền `on_batch(batch)`:
  - Sau mỗi batch (đã dedupe), `fetch_json` sẽ gọi `on_batch`.
- Hữu ích khi:
  - Stream dữ liệu ra file,
  - Xử lý dần từng phần, tránh giữ toàn bộ trong RAM.

### 3.3. Song song

2 lớp:

1. **Page-level parallel**:
   - `ONUSLIBS_PARALLEL=true`.
   - Nhiều page trong cùng 1 window/segment được fetch song song.

2. **Segment-level parallel**:
   - `ONUSLIBS_SEGMENT_PARALLEL=true`.
   - `ONUSLIBS_SEGMENT_MAX_WORKERS` = số worker cho segment.
   - Nhiều segment (nhiều đoạn thời gian) chạy song song.

Cả 2 đều chịu giới hạn bởi `ONUSLIBS_MAX_INFLIGHT` và `ONUSLIBS_REQ_PER_SEC`.

---

## 4. Module DB – Kết nối & thao tác CSDL

### 4.1. Cấu hình secret DB

Khuyến nghị lưu thông tin DB trong **Keyring** (cùng service với token):

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

Hoặc qua ENV:

```env
ONUSLIBS_DB_HOST=127.0.0.1
ONUSLIBS_DB_PORT=3306
ONUSLIBS_DB_USER=onusreport
ONUSLIBS_DB_PASSWORD=xxx
ONUSLIBS_DB_NAME=onusreport
ONUSLIBS_DB_SSL_CA=
ONUSLIBS_DB_CONNECT_TIMEOUT=10
```

### 4.2. `DbSettings.from_secure`

```python
from onuslibs.db.settings import DbSettings

db_settings = DbSettings.from_secure()               # đọc từ keyring + ENV
db_settings = DbSettings.from_secure(fallback_env=True)  # ưu tiên ENV trước
```

- Đọc lần lượt các key DB từ ENV / Keyring.
- Có `safe_dict()` để log cấu hình không chứa password.

### 4.3. Facade `onuslibs.db` (dùng nhanh)

```python
from onuslibs.db import healthcheck, query, execute, bulk_insert

print("DB OK?", healthcheck())

rows = query("SELECT * FROM onchain_diary LIMIT %s", (5,))
execute("INSERT INTO tmp_onuslibs_smoke(id, name, score) VALUES (%s,%s,%s)", (123, "smoke", 100))

bulk_insert(
    "INSERT INTO tmp_onuslibs_smoke(id, name, score) VALUES (%s,%s,%s)",
    [(2001, "bulk-1", 10), (2002, "bulk-2", 20)],
    batch_size=1000,
)
```

- Lần đầu gọi sẽ tự `DbSettings.from_secure()` + tạo `DB` nội bộ.
- Các lần sau reuse lại instance đó.

### 4.4. Class `DB` (nâng cao)

```python
from onuslibs.db.settings import DbSettings
from onuslibs.db.core import DB

db = DB(DbSettings.from_secure())

ok = db.healthcheck()
rows = db.query("SELECT * FROM onchain_diary WHERE userid=%s LIMIT 10", (123,))
affected = db.execute("UPDATE tmp_onuslibs_smoke SET score=%s WHERE id=%s", (100, 1))
```

---

## 5. Ví dụ sử dụng trong `examples/`

### 5.1. `examples/get_commission.py`

- Endpoint:
  - `/api/vndc_commission/accounts/vndc_commission_acc/history`
- Params:
  - `chargedBack=false`
  - `transferFilters=vndc_commission_acc.commission_buysell`
  - `datePeriod = build_date_period(start_date, end_date)`
- Fields (ví dụ):
  - `date, transactionNumber, relatedAccount.user.id, relatedAccount.user.display, amount, description`
- Gọi:

```python
rows = fetch_json(
    endpoint=ENDPOINT,
    params=params,
    fields=FIELDS,
    page_size=args.page_size,
    paginate=True,
    order_by=args.order,
    settings=OnusSettings(),
    unique_key="transactionNumber",
)
```

### 5.2. `examples/onchain_usdt_receive.py`

- Endpoint: `/api/transfers`
- Params:
  - `transferFilters=usdtacc.onchain_receive`
  - `datePeriod=build_date_period(start_date, end_date)`
- Fields:
  - `transactionNumber,date,amount,from.user.id,from.user.display,to.user.id,to.user.display,type.internalName`
- Dùng để test hybrid auto-segment trên range dài (vd: 2025-11-01 → 2025-11-16).

### 5.3. `examples/pro_vndc_send.py`

- Endpoint: `/api/transfers`
- Params:
  - `transferTypes=vndcacc.vndc_offchain_send_onuspro`
  - `amountRange=""`
  - `datePeriod=build_date_period(start_date, end_date)`
- Fields giống `onchain_usdt_receive`.
- Hỗ trợ:
  - `--date` hoặc `--start-date/--end-date`
  - `--out-csv` (mặc định `files/pro_vndc_send.csv`)

---

## 6. Tóm tắt ENV quan trọng

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
  - `ONUSLIBS_MAX_WINDOW_DAYS`
  - `ONUSLIBS_MAX_ROWS_PER_WINDOW`
  - `ONUSLIBS_AUTO_SEGMENT`
  - `ONUSLIBS_MAX_SEGMENT_SPLIT_DEPTH`
  - `ONUSLIBS_SEGMENT_PARALLEL`
  - `ONUSLIBS_SEGMENT_MAX_WORKERS`
  - `ONUSLIBS_DATE_SEGMENT_HOURS` (legacy)

- Bảo mật:
  - `ONUSLIBS_SECRETS_BACKEND`
  - `ONUSLIBS_KEYRING_SERVICE`
  - `ONUSLIBS_KEYRING_ITEM`
  - `ONUSLIBS_FALLBACK_ENV`
  - Các key DB (ENV hoặc Keyring): `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL_CA`, ...
