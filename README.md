# OnusLibs v3 — REST‑first, Facade duy nhất

OnusLibs v3 là thư viện **API Client** tối giản cho hệ thống Cyclos/Wallet với các nguyên tắc cốt lõi:

- **REST‑first**: tập trung GET JSON, ghép URL và params rõ ràng.
- **Facade duy nhất**: 1 API hợp nhất `fetch_json(...)` bao phủ phần lớn use‑case.
- **ENV‑first + Keyring cho secrets**: cấu hình qua ENV/.env; token/DB qua keyring.
- **An toàn & hiệu năng**: HTTP/2, retry/backoff/jitter, rate‑limit theo RPS, phân trang theo header Cyclos, **tuỳ chọn chạy song song** (parallel) có ràng buộc.

---

## Kiến trúc (6 module)

1) **config / OnusSettings**  
   - Tự nạp ENV và `.env` (nếu có `python-dotenv`).  
   - Chuẩn hoá giá trị & validate bắt buộc (`ONUSLIBS_BASE_URL`).  
   - Tham số runtime: `page_size`, `req_per_sec`, `max_inflight`, `timeout_s`, `http2`, `proxy`, `verify_ssl`, ...

2) **security / build_headers**  
   - Tạo header chuẩn cho mọi request (ví dụ: `Authorization`).  
   - **ENV‑first** + **keyring** cho secrets (token, DB).

3) **http / HttpClient**  
   - Dùng `httpx.Client` đồng bộ, tái sử dụng kết nối.  
   - **RateLimiter** (RPS), **retry/backoff/jitter**, HTTP/2 (nếu sẵn).  
   - Gọi chính: `get(path, params, headers)`.

4) **pagination / HeaderPager**  
   - Phân trang theo header Cyclos: `X-Has-Next-Page`, `X-Page-Count`, `X-Total-Count`.  
   - Dừng êm khi `400/404/422` (hết trang/không hợp lệ).  
   - **Parallel pager (tuỳ chọn)**: chạy song song theo trang, **giữ thứ tự** 0→N−1, **tôn trọng RPS** và `max_inflight`.

5) **unified / fetch_json (Facade)**  
   - Gộp headers + params + phân trang + **dedupe** + `on_batch` + `strict_fields`.  
   - Dễ test: DI `client`, `pager_func`, `extra_headers`.  
   - Bật **parallel** bằng cờ `parallel=True` (opt‑in).

6) **db** *(tuỳ chọn)*  
   - `DbSettings.from_secure()` (keyring).  
   - `query / execute / bulk_insert` + `@transactional` (phục vụ ETL).

---

## Cài đặt & Chuẩn bị

### 1) Cài ở chế độ phát triển (editable)

```bash
pip uninstall -y onuslibs
pip install -e .
```

### 2) ENV/.env (ENV‑first)

**Bắt buộc**
```
ONUSLIBS_BASE_URL=https://wallet.vndc.io
```

**Điều khiển runtime**
```
ONUSLIBS_PAGE_SIZE=10000
ONUSLIBS_REQ_PER_SEC=2
ONUSLIBS_MAX_INFLIGHT=4
ONUSLIBS_TIMEOUT_S=60
ONUSLIBS_HTTP2=true
ONUSLIBS_VERIFY_SSL=true
# ONUSLIBS_PROXY=https://user:pass@host:port  (nếu cần)
```

**Secrets backend**
```
ONUSLIBS_SECRETS_BACKEND=keyring
ONUSLIBS_KEYRING_SERVICE=OnusLibs
ONUSLIBS_KEYRING_ITEM=ACCESS_CLIENT_TOKEN
ONUSLIBS_FALLBACK_ENV=true   # cho phép đọc token từ ENV nếu thiếu keyring (khuyến nghị chỉ dùng dev)
```

> `.env` cần mã hoá **UTF‑8 không BOM** và đặt tại **root** dự án. `OnusSettings` sẽ tự `load_dotenv()` nếu có.

### 3) Keyring (token & DB)

PowerShell (Windows):
```powershell
$svc="OnusLibs"
python -c "import keyring; s='$svc'; keyring.set_password(s,'ACCESS_CLIENT_TOKEN','<your_api_token_here>')"

# (Tuỳ chọn) DB secrets:
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_HOST','<host>')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_USER','onusreport')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PASSWORD','<pass>')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_NAME','onusreport')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PORT','3306')"
```

Bash (Linux/macOS):
```bash
python - <<'PY'
import keyring
svc="OnusLibs"
keyring.set_password(svc,"ACCESS_CLIENT_TOKEN","<your_api_token_here>")
PY
```

---

## Facade duy nhất: `fetch_json(...)`

```python
from onuslibs.config.settings import OnusSettings
from onuslibs.unified.api import fetch_json

s = OnusSettings()  # tự nạp ENV/.env
rows = fetch_json(
    endpoint="/api/users",
    params={"statuses": "active"},
    fields=["id","name","email"],      # hoặc "id,name,email"
    paginate=True,                     # bật phân trang
    page_size=None,                    # None -> lấy từ ENV; nếu không có -> mặc định 10000
    order_by="name asc",
    settings=s,
    unique_key="id",                   # dedupe theo khoá
    strict_fields=True,                # cảnh báo nếu field top-level thiếu
    # parallel=True,                   # (tuỳ chọn) bật chạy song song theo trang
    # workers=None,                    # None -> dùng ONUSLIBS_MAX_INFLIGHT; clamp ≤ 16
)
```

### Tham số chi tiết

- `endpoint: str` — ví dụ `"/api/users"`  
- `params: dict | None` — tham số gốc **không** gồm `fields`, `orderBy`, `pageSize` (Facade sẽ chèn).  
- `fields: Sequence[str] | str | None` — list hoặc CSV; Facade chuẩn hoá thành CSV.  
- `paginate: bool` — bật phân trang.  
- `page_size: int | None` — **ưu tiên cao nhất**; nếu None → dùng `OnusSettings.page_size`; nếu vẫn trống → **mặc định 10000**.  
- `order_by: str | None` — gửi vào `orderBy`.  
- `unique_key: str | None` — dedupe giữa các trang.  
- `strict_fields: bool` — cảnh báo nếu field top-level không thấy trong payload.  
- `settings: OnusSettings` — ENV‑first.  
- `on_batch: Callable[[list[dict]], None] | None` — callback theo batch.  
- `client: HttpClient | None` — DI HttpClient.  
- `pager_func: Callable | None` — DI chiến lược phân trang (override mặc định).  
- `extra_headers: dict | None` — chèn/ghi đè header.  
- `parallel: bool` — **opt‑in** chạy song song theo trang (cần `parallel_pager.py`).  
- `workers: int | None` — số luồng; `None` → dùng `ONUSLIBS_MAX_INFLIGHT` (và clamp ≤ 16).

**Thứ tự ưu tiên `page_size` (khi `paginate=True`)**  
1) `page_size` truyền trực tiếp vào `fetch_json(...)` (cho lần gọi đó).  
2) `OnusSettings.page_size` (đọc từ `ONUSLIBS_PAGE_SIZE`).  
3) Mặc định 10000.

> Khi `paginate=True`, lớp phân trang sẽ tự chèn `pageSize` vào request → **không nên** tự đặt `pageSize` trong `params`.

---

## HTTP Client (Module 3)

- **Rate limit** theo `ONUSLIBS_REQ_PER_SEC` (RPS) — an toàn cho server.  
- **Retry/backoff/jitter** cho lỗi 429/5xx.  
- **HTTP/2**, `timeout_s`, `verify_ssl`, `proxy`.  
- Reuse 1 `httpx.Client` → hiệu năng & thread‑safety tốt cho GET/JSON.

> Khi **parallel**: nhiều luồng cùng chia sẻ `HttpClient` ⇒ limiter vẫn **khống chế RPS tổng**, tránh “flood”.

---

## Pagination (Module 4)

- **HeaderPager** tuần tự (mặc định), dừng êm khi `400/404/422`.  
- **Parallel pager (tuỳ chọn)**  
  - Lấy page 0 để suy ra tổng trang (`X-Page-Count`/`X-Total-Count`); nếu không có → fallback tuần tự.  
  - Chạy song song 1..N, **giữ thứ tự** yield 0→N−1.  
  - Tôn trọng `ONUSLIBS_REQ_PER_SEC` và `ONUSLIBS_MAX_INFLIGHT` (clamp ≤ 16).

> Khuyến nghị: chỉ bật parallel khi endpoint **ổn định** `orderBy` (ví dụ `date asc/desc`).

---

## Security (Module 2)

- `build_headers(settings)` sinh header (Authorization, User‑Agent, ...).  
- Token ưu tiên từ keyring (`ACCESS_CLIENT_TOKEN`). Khi `ONUSLIBS_FALLBACK_ENV=true`, cho phép lấy token từ ENV (khuyến nghị dev).

---

## DB (Module 6 — tuỳ chọn)

- `DbSettings.from_secure()` lấy cấu hình DB từ keyring.  
- `db.core`: `query() / execute() / bulk_insert()` + `@transactional`.

---

## Ví dụ thực tế

### 1) Commission history (CLI tách cấu hình)

```bash
# 1 ngày, preset basic (date, amount, description)
python -m apps.commission.cli --date 2025-10-11

# Khoảng ngày + preset full + ghi CSV
python -m apps.commission.cli --start-date 2025-10-01 --end-date 2025-10-11 --preset full --out-csv out.csv

# Bổ sung fields qua CSV
python -m apps.commission.cli --date 2025-10-11 --preset minimal --fields amount,description
```

**Flags phổ biến**
- `--date` hoặc `--start-date/--end-date`  
- `--preset {minimal,basic,full}`  
- `--fields <csv>` / `--fields-file <path>`  
- `--page-size <int>` / `--order {dateAsc,dateDesc}` / `--filters <transferFilters>`  
- `--charged-back {true,false}`  
- `--out-json <file>` / `--out-csv <file>`  
- *(tuỳ chọn)* `--parallel` / `--workers <int>`

### 2) Lấy users theo danh sách userid

```python
from onuslibs.config.settings import OnusSettings
from onuslibs.unified.api import fetch_json

user_ids = ["6277729722014433182"]
fields = [
    "id","name","email",
    "group.name",
    "customValues.gender","customValues.date_of_birth",
    "customValues.vip_level","customValues.listed",
    "address.city","customValues.document_type",
]
rows = fetch_json(
    endpoint="/api/users",
    params={
        "includeGroup": "true",
        "usersToInclude": ",".join(user_ids),
        "statuses": "active,blocked,disabled",
        "page": 0,
    },
    fields=fields,
    paginate=True,
    page_size=1000,
    settings=OnusSettings(),
    unique_key="id",
    strict_fields=True,
    # parallel=True,
)
```

---

## Utilities (khuyên dùng)

- `tools/print_json.py` — in JSON đẹp (UTF‑8, indent).  
- `tools/write_csv.py` — **flatten** nested dict theo dot‑path, ghi CSV `utf-8-sig` (Excel‑friendly).

```python
from tools.write_csv import write_csv
n = write_csv(rows, "out.csv")                          # auto dò cột & flatten
n = write_csv(rows, "selected.csv", fields=["id","date","from.name"])
```

---

## Best practices

- **ENV‑first**: cấu hình qua ENV/.env; secrets qua keyring.  
- **Token permission**: thiếu quyền ⇒ API trả thiếu field (không phải lỗi thư viện).  
- **RPS & inflight**: điều chỉnh `ONUSLIBS_REQ_PER_SEC` + `ONUSLIBS_MAX_INFLIGHT` phù hợp server.  
- **Parallel**: chỉ bật khi cần; đảm bảo `orderBy` ổn định; theo dõi log 429/5xx.  
- **Dedupe**: luôn set `unique_key` (nếu endpoint có id) để tránh trùng khi phân trang.  
- **on_batch**: xử lý/ghi DB theo mẻ để tiết kiệm RAM.  

---

## Troubleshooting

- `base_url is empty` → thiếu `ONUSLIBS_BASE_URL` hoặc `.env` chưa nạp (encoding/đường dẫn).  
- `.env parse error` → lưu file UTF‑8 không BOM, dạng `KEY=VALUE` (mỗi dòng một biến).  
- `422 unknown` ở trang lớn → page vượt phạm vi; HeaderPager sẽ dừng êm.  
- Thiếu field dù đã khai báo `fields` → **token không đủ quyền**.  

---

## Giấy phép

Nội bộ dự án Vũ — sử dụng theo chính sách nội bộ.
