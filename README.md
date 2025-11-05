OnusLibs v2 — Security + Paging v2 (+ Optional DB)

Mục tiêu: OnusLibs là base gateway cho các ứng dụng ETL/Report:

Kết nối API trả JSON (raw) với Paging v2 an toàn, không bỏ sót.

Bảo mật theo framework: Keyring-first, hỗ trợ Fernet, và ENV fallback (chỉ khi bật cho DEV).

(Tùy chọn) Module DB MySQL giữ tương thích tối đa với OnusReport v1.1.

Kiến trúc: Core (HTTP + Paging v2) + Security framework.
Core không chứa token; mọi request phải dùng build_headers().

1) Cài đặt (VS Code, Windows PowerShell)
# 1) Tạo & kích hoạt venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Cài đặt
python -m pip install -U pip
python -m pip install -e .
python -m pip install -r requirements.txt


requirements.txt (tối thiểu):

keyring
pydantic-settings
python-dotenv
cryptography
httpx[http2]
tenacity


Nếu chưa dùng HTTP/2, có thể bỏ [http2] hoặc đặt ONUSLIBS_HTTP2=false. Thư viện có fallback về HTTP/1.1 nếu thiếu h2.

Cài đặt (từ GitHub)

Lưu ý: tên ref phân biệt hoa/thường. Nhánh/tag là v2 (không phải V2).

Cách nhanh (HTTPS)
python -m pip install "git+https://github.com/WIND9K/OnusLibs.git"

2) Bảo mật (Security) — API & DB dùng chung 1 Keyring service

Mô hình tra cứu bí mật (secrets):
auto → keyring → fernet → env (ENV chỉ dùng khi bật explicit cho DEV).

Keyring-first (khuyến nghị)

Service chung cho cả API & DB: ONUSLIBS_KEYRING_SERVICE=OnusLibs

OnusLibs sẽ đọc API token & DB creds từ cùng service này.

Vẫn tương thích ngược: nếu đặt ONUSLIBS_DB_KEYRING_SERVICE, giá trị đó sẽ override cho DB.

Fernet (tuỳ chọn)

Giải mã file secrets mã hoá (vd. .env.enc) nếu bạn triển khai theo chuẩn của dự án.

ENV fallback (không khuyến nghị cho PROD)

Chỉ bật khi DEV: ONUSLIBS_FALLBACK_ENV=true.

Biến môi trường liên quan

Chọn backend:

ONUSLIBS_SECRETS_BACKEND = auto | keyring | fernet | env (mặc định auto)

ONUSLIBS_FALLBACK_ENV = true | false (PROD nên để false)

Service Keyring (dùng chung API & DB)

ONUSLIBS_KEYRING_SERVICE = OnusLibs ← khuyến nghị

(Tuỳ chọn, tương thích ngược) ONUSLIBS_DB_KEYRING_SERVICE
→ nếu đặt, ưu tiên cho DB thay vì dùng ONUSLIBS_KEYRING_SERVICE.

API token ENV (khi fallback)

ACCESS_CLIENT_TOKEN | ONUS_ACCESS_CLIENT_TOKEN | ONUSLIBS_ACCESS_CLIENT_TOKEN

Base URL (bắt buộc khi gọi API)

ONUSLIBS_BASE_URL (hoặc ONUS_BASE_URL), ví dụ: https://wallet.vndc.io

Lưu ý: Core không bao giờ đọc token trực tiếp; mọi request API phải dùng onuslibs.security.build_headers().

Set Keyring (API + DB chung service):

$svc="OnusLibs"
# API token
python -c "import keyring; keyring.set_password('$svc','ACCESS_CLIENT_TOKEN','<TOKEN>')"

# DB creds (nếu muốn cho onuslibs DB module trong tương lai)
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_HOST','<host>')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_USER','<user>')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PASSWORD','<pass>')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_NAME','onusreport')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PORT','3306')"
python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_SSL_CA','')"



Có thể lưu thêm “alias” để tương thích rộng: host/user/password/name/port/ssl_ca.

ENV chạy app (tối thiểu)
ONUSLIBS_SECRETS_BACKEND=keyring
ONUSLIBS_FALLBACK_ENV=false
ONUSLIBS_KEYRING_SERVICE=OnusLibs
ONUSLIBS_BASE_URL=https://wallet.vndc.io          # nếu dùng API


Nếu bạn đã đặt ONUSLIBS_DB_KEYRING_SERVICE, nó sẽ ghi đè service DB; nếu không đặt, DB tự dùng ONUSLIBS_KEYRING_SERVICE.

Kiểm tra nhanh

API header

python -c "from onuslibs.security import build_headers; print(build_headers().keys())"


DB health

python -c "from onuslibs.db import healthcheck; print('DB health:', healthcheck())"

Gợi ý .env (an toàn cho PROD)
# ==== Secrets backend ====
ONUSLIBS_SECRETS_BACKEND=keyring
ONUSLIBS_FALLBACK_ENV=false

# Dùng chung 1 service cho API & DB
ONUSLIBS_KEYRING_SERVICE=OnusLibs

# Base URL cho API
ONUSLIBS_BASE_URL=https://wallet.vndc.io

# (Không đặt DB_* ở đây cho PROD; DB_* chỉ dùng tạm khi DEV + bootstrap)

3) Runtime Settings (Core — KHÔNG chứa token)

OnusSettings đọc các biến:

ONUSLIBS_BASE_URL hoặc ONUS_BASE_URL (bắt buộc)

ONUSLIBS_PAGE_SIZE (mặc định 10000)

ONUSLIBS_REQ_PER_SEC (mặc định 3.0)

ONUSLIBS_HTTP2 (mặc định true) → nếu thiếu h2, tự fallback HTTP/1.1

ONUSLIBS_TIMEOUT_S (mặc định 30)

Ví dụ đặt nhanh (cho phiên hiện tại):

$env:ONUS_BASE_URL="https://wallet.vndc.io"
$env:ONUSLIBS_HTTP2="false"   # nếu chưa cài httpx[http2]

4) Phân trang v2
Mục tiêu

Không bỏ sót (nhiều bản ghi cùng giây).

Ổn định với API chỉ cho phép page=0.

Hiệu năng an toàn: req_per_sec, timeout_s, day_workers.

Cấu trúc chạy

Outer (cấp ngày): chia theo ngày [day, next_day), có thể chạy song song theo day_workers.

Inner (nội ngày):

Mặc định: segmented-by-total

Gọi page=0 để đọc header: X-Total-Count, X-Page-Size, X-Page-Count, X-Has-Next-Page.

Ước lượng số segments ≈ ceil(Total / page_size).

Mỗi segment luôn khởi đầu bằng page=0 (tránh lỗi 422 ở page>0 trên các API nhạy cảm).

Trong mỗi segment, nếu batch trả về “đầy” ≈ page_size * safety_ratio, thực hiện bisect theo thời gian (tăng cursor lên max(timestamp) + ε) để không bỏ sót các bản ghi trùng timestamp.

Header paging fallback
Đặt force_segmented_paging=False để dùng phân trang server: page=0,1,2,… (tương thích cách cũ).

Chỉ dùng khi API của bạn bảo đảm phân trang ổn định với page>0.

Nếu server không cung cấp header tổng hoặc header không đáng tin, thư viện tự rơi về segmented-by-last-timestamp (vẫn bắt đầu page=0, đi tiếp bằng mốc thời gian cuối + ε).

Limiter & Timeout

req_per_sec: giới hạn tốc độ gọi (khuyến nghị 2–3 RPS).

timeout_s: timeout mỗi request (mặc định 30s).

http2: bật/tắt HTTP/2; nếu chưa cài h2, thư viện sẽ fallback về HTTP/1.1.

Tham số chính

endpoint: API endpoint (vd. "/api/commissions/history").

start, end: khoảng thời gian tổng (UTC).

Khuyến nghị datetime có tzinfo=UTC. Thư viện không tự chuyển timezone.

date_field: tên trường thời gian trong payload (vd. "date").

page_size: kích thước lô (mặc định 10.000; có thể 20.000).

split_by_day: True để cắt theo ngày [day, next_day).

day_workers: số “luồng ngày” chạy song song (khuyến nghị 2–5).

segment_safety_ratio: ngưỡng xem là “đầy” (khuyến nghị 0.95).

epsilon_seconds: bước nhảy khi bisect (mặc định 1 giây).

force_segmented_paging:

True (mặc định): segmented-by-total / last-timestamp (không dùng page>0).

False: dùng header paging của server (page=0,1,2,…).

Pseudo-code (giản lược)
for day in days(start, end):             # [day, next_day)
  cursor = day.start
  # ước lượng segments từ header tổng (nếu có), else = +∞
  while cursor < day.end:
    resp = GET page=0, filter date ∈ [cursor, day.end)
    items = resp.items
    append(items)

    if len(items) >= page_size * segment_safety_ratio:
        t_max = max(items[date_field])
        cursor = t_max + epsilon_seconds   # tránh trùng timestamp
    else:
        break

Ví dụ gọi
from datetime import date
from onuslibs import fetch_all

rows = fetch_all(
    endpoint="/api/commissions/history",
    start=date(2025, 10, 1),
    end=date(2025, 10, 1),
    date_field="date",
    page_size=20000,
    split_by_day=True,
    day_workers=2,                 # 2–5 tuỳ tài nguyên
    req_per_sec=3.0,
    http2=True,
    timeout_s=30.0,
    segment_safety_ratio=0.95,
    epsilon_seconds=1,
    # Fallback dùng page 0..n của server (không khuyến nghị nếu API hay lỗi page>0):
    # force_segmented_paging=False,
)
print(len(rows))

Checklist an toàn

 start/end là UTC, tránh lẫn naive/aware.

 page_size 10k–20k; segment_safety_ratio≈0.95.

 req_per_sec 2–3; timeout_s≥30.

 split_by_day=True để giảm cửa sổ.

 Header tổng có thì tận dụng; không có → auto last-timestamp.

 Chỉ bật force_segmented_paging=False khi API phân trang ổn định ở page>0.

5) Ví dụ API phổ biến
5.1 Commission History (Paging v2)
from datetime import date
from onuslibs import fetch_all

rows = fetch_all(
    endpoint="/api/commissions/history",
    start=date(2025, 10, 1),
    end=date(2025, 10, 1),
    date_field="date",
    page_size=20000,
    split_by_day=True,
    req_per_sec=3.0,
)
print(len(rows), rows[:1])

5.2 Users theo danh sách ID (simple)
from onuslibs.simple import users_by_ids

rows = users_by_ids(
    ids=["6277729705...", "6277729706..."],
    endpoint="/api/users",
    fields="id,username,name,email",
    page_size=10000,
    http2=True,
)
print(len(rows), rows[:1])


simple.py không cache header ở cấp module; mỗi request luôn gọi build_headers() để lấy token mới nhất (an toàn khi rotate).

6) (Tùy chọn) Module DB MySQL

Sẽ được cập nhật ở bước 2 (mã nguồn). README ghi chú trước để đồng bộ cách dùng.

ENV dự kiến: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (tuỳ chọn DB_PORT, DB_SSL_CA)

API dự kiến:

healthcheck() -> bool

query(sql, params=None) -> List[Dict]

execute(sql, params=None) -> int

bulk_insert(table, rows, columns=None, on_duplicate_update=None, chunk_size=1000) -> int

Mục tiêu: tương thích với cách dùng của OnusReport v1.1 để giảm đổi code khi nâng cấp.

7) Cấu trúc repo (rút gọn)
OnusLibs/
└─ onuslibs/
   ├─ __init__.py                 # export: build_headers, get_access_client_token, fetch_all
   ├─ settings.py                 # OnusSettings (runtime, KHÔNG chứa token)
   ├─ http_client.py              # make_sync_client/make_async_client + fallback HTTP/1.1
   ├─ security/
   │  ├─ __init__.py              # export SecuritySettings, get_access_client_token, build_headers
   │  ├─ settings.py              # SecuritySettings (Keyring/Fernet/ENV)
   │  ├─ token_provider.py        # get_access_client_token()/build_headers()
   │  └─ fernet_loader.py         # giải mã .env.enc
   ├─ pagination/
   │  ├─ segmented.py             # fetch_all (core v2)
   │  └─ pagination_core.py       # compat: from .segmented import fetch_all
   └─ simple.py                   # users_by_ids, list_users (không cache header)

8) Smoke test nhanh
# Kiểm tra header
python -c "from onuslibs.security import build_headers; print(build_headers().keys())"

# Test HTTP (cần token hợp lệ)
python - << 'PY'
import os, httpx
from onuslibs.security import build_headers
base = os.getenv("ONUS_BASE_URL","https://wallet.vndc.io").rstrip("/")
url  = f"{base}/api/users"
with httpx.Client(http2=True, timeout=10) as c:
    r = c.get(url, headers=build_headers(), params={"page":0,"pageSize":1,"fields":"id"})
    print("status:", r.status_code)
PY

9) Migration 1.1 → v2 (nhanh)

Thay mọi chỗ tự dựng header/token → from onuslibs.security import build_headers.

Nếu code cũ import pagination_core.fetch_all → không cần sửa, đã có file tương thích.

Nếu app đang dùng ENV token trực tiếp → bật ONUSLIBS_FALLBACK_ENV=true (DEV) hoặc chuyển sang Keyring/Fernet (khuyến nghị cho PROD).

Nếu dùng HTTP/2, cài httpx[http2] (gói h2). Không có thì thư viện tự fallback HTTP/1.1.

10) Troubleshooting

ImportError: Using http2=True, but the 'h2' package is not installed
→ python -m pip install "httpx[http2]" hoặc đặt ONUSLIBS_HTTP2=false.

Thiếu base URL
→ đặt ONUSLIBS_BASE_URL hoặc ONUS_BASE_URL.

Missing API token
→ Lưu vào Keyring onuslibs/ACCESS_CLIENT_TOKEN, hoặc cấu hình Fernet, hoặc bật ONUSLIBS_FALLBACK_ENV=true (DEV).