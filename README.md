# Tổng hợp OnusLibs v3 (chuẩn kiến trúc 6 module)﻿

# Mục tiêu & Triết lý﻿

REST-first, Facade duy nhất cho API ONUS/Cyclos.

Ẩn phức tạp: token/keyring, HTTP/2, rate-limit, retry/backoff, phân trang header.

Cấu hình runtime qua ENV, validate chặt, dễ “bật/tắt” fallback ENV khi cần.

An toàn log: luôn “scrub” token khi in/log.

# Kiến trúc 6 module﻿

config/OnusSettings﻿

Đọc ENV tại runtime, không “đóng băng” khi import.

Validate:

ONUSLIBS_BASE_URL bắt buộc, bắt đầu bằng http(s)://.

ONUSLIBS_PAGE_SIZE ≥ 1, ONUSLIBS_REQ_PER_SEC > 0, ONUSLIBS_TIMEOUT_S > 0, ONUSLIBS_MAX_INFLIGHT ≥ 1.

ONUSLIBS_TOKEN_HEADER không rỗng.

ONUSLIBS_SECRETS_BACKEND ∈ {keyring, env} (khác → normalize về keyring).

to_dict() trả ảnh chụp cấu hình hiện hành.

security/﻿

keyring_helper (get/set bí mật theo ONUSLIBS_KEYRING_SERVICE + ONUSLIBS_KEYRING_ITEM).

build_headers(settings, extra=None): trả headers chuẩn (mặc định chứa Access-Client-Token: <token>).

Ưu tiên keyring; nếu ONUSLIBS_FALLBACK_ENV=true, cho phép lấy từ ENV (ACCESS_CLIENT_TOKEN).

preview_headers(headers): ẩn token kiểu abcd...wxyz để log/debug an toàn.

http/﻿

HttpClient(settings) bọc httpx.Client:

HTTP/2 (nếu khả dụng), timeout theo ENV.

Rate-limit theo ONUSLIBS_REQ_PER_SEC.

Retry/backoff cho 429/5xx (mũ 1–2–4–8s, giới hạn).

Tự nối base_url + path (nếu path không phải URL tuyệt đối).

API chính: get(path, *, params, headers).

pagination/﻿

HeaderPager(client, endpoint, params, headers, page_size):

Gọi GET theo trang; dừng khi X-Has-Next-Page=false hoặc batch rỗng.

Hỗ trợ payload dạng list hoặc dict có items/pageItems.

Luôn gắn page (bắt đầu 0) và pageSize vào params.

unified/﻿

fetch_json(endpoint, params, *, fields, order_by, paginate, page_size, strict_fields, unique_key, on_batch, settings):

Facade duy nhất để GET JSON.

Thêm fields (CSV) & orderBy đúng chuẩn server.

paginate=True → dùng HeaderPager; paginate=False → gọi 1 lần.

Dedupe theo unique_key (nếu cung cấp).

on_batch nhận từng batch ngay khi fetch (stream kiểu ETL).

strict_fields=True (khuyến nghị khi dev) giúp “fail-fast” từ phía server nếu fields sai.

db/ (tuỳ chọn)﻿

Đọc kết nối MySQL từ keyring (DB_HOST, DB_USER, …).

Helper: query/execute/bulk_insert, @transactional.

Mục tiêu: dùng chung chuẩn bảo mật (cùng Keyring Service).

# Mục tiêu: dùng chung chuẩn bảo mật (cùng Keyring Service)﻿

# ENV khuyến nghị﻿

bash
# ===== BẮT BUỘC =====
ONUSLIBS_BASE_URL=https://wallet.vndc.io

# ===== Runtime =====
ONUSLIBS_PAGE_SIZE=10000
ONUSLIBS_REQ_PER_SEC=2
ONUSLIBS_MAX_INFLIGHT=4
ONUSLIBS_TIMEOUT_S=60
ONUSLIBS_HTTP2=true

# ===== Secrets backend =====
ONUSLIBS_SECRETS_BACKEND=keyring
ONUSLIBS_KEYRING_SERVICE=OnusLibs
ONUSLIBS_KEYRING_ITEM=ACCESS_CLIENT_TOKEN
ONUSLIBS_FALLBACK_ENV=false         # Production nên để false
ONUSLIBS_TOKEN_HEADER=Access-Client-Token
# Thiết lập Keyring (PowerShell – Windows)﻿

powershell
$svc = "OnusLibs"
python -c "import keyring; keyring.set_password('$svc','ACCESS_CLIENT_TOKEN','<token>')"
(Nếu cần test tạm mà chưa set keyring: đặt ONUSLIBS_FALLBACK_ENV=true + ACCESS_CLIENT_TOKEN=<token> — KHÔNG khuyến nghị cho production.)﻿

# Cách dùng tối thiểu﻿

A) Dùng Facade fetch_json (khuyến nghị)

python
from onuslibs.unified.api import fetch_json

rows = fetch_json(
    endpoint="/api/users",
    params={
        "includeGroup":"true",
        "usersToInclude": "6277729706994698142",
        "statuses": "active,blocked,disabled",
    },
    fields="id,name,email,customValues,group.name",
    paginate=True,           # bật phân trang theo HeaderPager
    page_size=1000,          # hoặc để mặc định theo settings
    unique_key="id",         # dedupe
    strict_fields=False,     # dev có thể bật True để fail-fast
)
print("Total:", len(rows))
B) Gọi trực tiếp (httpx + headers)

python
import httpx
from onuslibs.config.settings import OnusSettings
from onuslibs.security.headers import build_headers

s = OnusSettings()
hdrs = build_headers(s)
url = s.base_url.rstrip("/") + "/api/users"
params = {
    "includeGroup": "true",
    "page": 0, "pageSize": 1000,
    "usersToInclude": "6277729706994698142",
    "statuses": "active,blocked,disabled",
    "fields": "id,name,email,customValues.date_of_birth,customValues.gender,group.name,customValues.vip_level,customValues.listed,address.city,customValues.document_type",
}
with httpx.Client(timeout=s.timeout_s, http2=s.http2) as cli:
    r = cli.get(url, headers=hdrs, params=params)
    r.raise_for_status()
    data = r.json()
# Quy ước an toàn & chất lượng﻿

Không in token: luôn dùng preview_headers(headers) khi cần log.

Giới hạn tốc độ theo REQ_PER_SEC để tránh 429.

Truy vấn lớn: ưu tiên paginate=True để chia trang; nếu chỉ one-shot với page=0&pageSize=... → đặt paginate=False.

Dữ liệu customValues: nếu nghi ngờ thiếu field, hãy gọi fields=customValues để xem đủ tất cả keys server trả về trước khi tối ưu hoá.

# Checklist vận hành nhanh﻿

Set keyring: ACCESS_CLIENT_TOKEN với service OnusLibs.

Set ENV như mục “ENV khuyến nghị”.

pip install -e .

Gọi thử A) hoặc B) để kiểm tra live.

Bật/tắt strict_fields và điều chỉnh fields theo schema thực tế của API.