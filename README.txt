OnusLibs

Thư viện Python dùng chung để truy cập Cyclos (ONUS wallet), với trọng tâm:

Kết nối API an toàn (đọc token từ .env/ENV/Keyring).

Phân trang kiểu datePeriod (Cyclos chỉ cho page=0 khi có datePeriod).

Chia thời gian thông minh + tự tách nhỏ (split) khi một cửa sổ vượt pageSize, đảm bảo không mất dữ liệu.

Cấu hình mềm (không hardcode), truyền từ ứng dụng.

Nội dung

Tính năng chính

Cài đặt

Cấu trúc dự án

Cấu hình bằng ENV

Dùng nhanh (Quickstart)

Chi tiết phân trang Cyclos (datePeriod)

API client & Adapters

CSDL (db_config) & ghi dữ liệu

Quản lý token (Keyring)

UI nhập token

Ví dụ xuất Excel/CSV

Best practices & lưu ý

Khắc phục sự cố

Giấy phép & phiên bản

Tính năng chính

OnusLibsClient: quản lý base_url, headers, token; gọi API trả (status, data, headers).

Phân trang theo thời gian:

1 lần probe rẻ để đọc X-Total-Count cho mỗi khoảng.

Tính số cửa sổ theo ceil(total/page_size), chia đều thời gian theo boundary_mode.

Nếu cửa sổ overflow (header báo Has-Next / Page-Count>1 / Total>pageSize) → đệ quy chia đôi đến khi ≤ pageSize.

Mặc định tự chia theo ngày (split_by_day=True) để ổn định mật độ.

Adapters: tự gộp from/to thành datePeriod=a,b đúng format Cyclos, không làm mất params khác.

DB cấu hình (tuỳ chọn): đọc thông số DB từ .env/ENV (MySQL, …).

Keyring (tuỳ chọn): lưu/lấy token theo profile qua OS Keyring.

UI/CLI (tuỳ chọn): UI streamlit nhập token; CLI lưu token vào Keyring.

Cài đặt
# môi trường ảo khuyến nghị
python -m venv .venv
. .venv/bin/activate  # (Windows: .venv\Scripts\activate)

pip install -r requirements.txt
# yêu cầu tối thiểu cho lib lõi:
#   requests>=2.31
#   python-dotenv>=1.0

# nếu cần DB (ví dụ MySQL):
pip install SQLAlchemy pymysql

# nếu cần keyring / UI:
pip install keyring streamlit


Gợi ý phát hành: cấu hình extras để cài chọn lọc:
pip install onuslibs[db], onuslibs[secrets], onuslibs[ui] (tùy package của bạn).

Cấu trúc dự án
OnusLibs/
├─ onuslibs/
│  ├─ __init__.py
│  ├─ client.py                 # HTTP client + ENV token
│  ├─ compat_env.py             # đọc ENV/.env, fallback hợp lý
│  ├─ api.py                    # helper HTTP đơn lẻ (tuỳ chọn)
│  ├─ token_manager.py          # Keyring (tuỳ chọn)
│  ├─ auth_ui.py                # UI nhập token (tuỳ chọn)
│  ├─ cli.py                    # CLI lưu token (tuỳ chọn)
│  ├─ db_config.py              # nạp cấu hình DB (tuỳ chọn)
│  └─ pagination/
│     ├─ __init__.py
│     ├─ adapters.py
│     ├─ config_pagination_core.py
│     └─ pagination_core.py     # fetch_all: time windows + split overflow
├─ test_commission.py           # ví dụ/ETL (tuỳ nhu cầu)
├─ .env                         # chứa token/DB (không commit)
├─ README.md
├─ requirements.txt
└─ setup.py / pyproject.toml

Cấu hình bằng ENV

Tạo .env ở root dự án:

# API
ONUSLIBS_TOKEN=your-access-client-token
ONUSLIBS_BASE_URL=https://wallet.vndc.io

# Pagination & limits (tùy test)
ONUSLIBS_PAGE_SIZE=20000
ONUSLIBS_RPS=3
ONUSLIBS_PROBE_SIZE=1
ONUSLIBS_EPSILON=1
ONUSLIBS_BOUNDARY=closed-open

# Endpoint & filters (ví dụ)
ONUSLIBS_ENDPOINT=/api/vndc_commission/accounts/vndc_commission_acc/history
ONUSLIBS_CHARGEDBACK=false
ONUSLIBS_TRANSFER_FILTERS=vndc_commission_acc.commission_buysell

# DB (nếu dùng)
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=onus
DB_PASSWORD=secret
DB_NAME=onusdb

# Keyring (tuỳ chọn)
ONUSLIBS_PROFILE=default

Dùng nhanh (Quickstart)
from datetime import datetime
from onuslibs import OnusLibsClient, ConfigLoader, fetch_all, make_client_request, wrap_dateperiod

client = OnusLibsClient(base_url="https://wallet.vndc.io")
request_fn = wrap_dateperiod(make_client_request(client))

cfg = ConfigLoader.load(overrides={
    "endpoint": "/api/vndc_commission/accounts/vndc_commission_acc/history",
    "method": "GET",
    "params": {
        "chargedBack": "false",
        "transferFilters": "vndc_commission_acc.commission_buysell"
    },
    "paging": {
        "page_param": "page",
        "per_page_param": "pageSize",
        "page_size": 20000  # ≤ 20000 (Cyclos)
    },
    "limits": { "req_per_sec": 3 },
    "strategy": {
        "probe_page_size": 1,
        "epsilon_seconds": 1,
        "boundary_mode": "closed-open",  # [start, end)
        "split_by_day": True
    }
})

items = []
for it in fetch_all(
    cfg,
    start_date=datetime.fromisoformat("2025-10-10T00:00:00"),
    end_date=datetime.fromisoformat("2025-10-11T23:59:59"),
    client_request=request_fn
):
    items.append(it)

print("Tổng items:", len(items))

Chi tiết phân trang Cyclos (datePeriod)

Quan trọng: Khi truyền datePeriod=a,b, Cyclos chỉ chấp nhận page=0.
Do đó OnusLibs không dùng offset/page; thay vào đó dùng time windows:

Probe (rẻ) để đọc X-Total-Count cho khoảng thời gian.

Tính num_windows = ceil(total/page_size).

Chia đều thời gian thành num_windows cửa sổ:

boundary_mode='closed-open' ⇒ [start, end) không trùng/khuyết ở ranh.

closed-closed ⇒ dùng epsilon_seconds dịch ranh kế tiếp.

Gọi API cho mỗi cửa sổ với page=0,pageSize=page_size.

Nếu overflow (Has-Next/Page-Count>1/Total>pageSize) ⇒ đệ quy chia đôi cửa sổ đến khi ≤ page_size.

Mặc định bật split_by_day=True: auto chia [start,end) thành các ngày [00:00,24:00) trước khi làm các bước trên (ổn định hơn khi mật độ dữ liệu không đều).

API client & Adapters
from onuslibs import OnusLibsClient, make_client_request, wrap_dateperiod

client = OnusLibsClient(base_url="https://wallet.vndc.io")
request_fn = wrap_dateperiod(make_client_request(client))

# request_fn(method, endpoint, params) -> (status, data, headers)
status, data, headers = request_fn("GET", "/path", {"datePeriod":"2025-10-11T00:00:00,2025-10-11T23:59:59", "page":0, "pageSize":20000})


wrap_dateperiod tự gộp from/to → datePeriod=a,b nếu bạn truyền from/to vào params.

CSDL (db_config) & ghi dữ liệu

Đọc cấu hình DB:

from onuslibs import DB_CONFIG
print(DB_CONFIG)  # {'host':..., 'user':..., 'password':..., 'database':..., 'port':...}


Ghi vào MySQL (ví dụ):

from sqlalchemy import create_engine, text

dsn = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG.get('port',3306)}/{DB_CONFIG['database']}?charset=utf8mb4"
engine = create_engine(dsn, pool_pre_ping=True)

with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO commission_raw (date, user_id, user_display, amount, payload_json)
        VALUES (:date, :uid, :name, :amount, :payload)
    """), [
        {
            "date":  (it.get("date","")[:10]),
            "uid":   (it.get("relatedAccount",{}).get("user",{}).get("id")),
            "name":  (it.get("relatedAccount",{}).get("user",{}).get("display")),
            "amount": it.get("amount"),
            "payload": str(it),
        } for it in items
    ])


Mẹo: tạo UNIQUE KEY theo business key (VD: transferId) và dùng UPSERT để tránh trùng.

Quản lý token (Keyring)

CLI (lưu token vào Keyring):

python -m onuslibs.cli --profile default --base https://wallet.vndc.io --token XXXXX


Trong code:

from onuslibs import set_wallet_credentials, get_wallet_credentials
set_wallet_credentials("default", "https://wallet.vndc.io", "XXXXX")
print(get_wallet_credentials("default"))  # {'base':..., 'token':...}


Hồ sơ mặc định đọc từ ONUSLIBS_PROFILE.

UI nhập token

Chạy UI (Streamlit):

streamlit run -m onuslibs.auth_ui


Nhập WALLET_BASE & ACCESS_CLIENT_TOKEN, lưu vào Keyring để app dùng lại sau.

Ví dụ xuất Excel/CSV

Mỗi giao dịch 1 dòng (không tính tổng), mapping theo API:

date = item["date"] của API (không convert TZ), cắt [:10] nếu có giờ.

user.id = relatedAccount.user.id

user.display = relatedAccount.user.display

amount = item["amount"]

import pandas as pd

rows = []
for it in items:
    rows.append({
        "date": (it.get("date","")[:10]),
        "user.id": it.get("relatedAccount",{}).get("user",{}).get("id"),
        "user.display": it.get("relatedAccount",{}).get("user",{}).get("display",""),
        "amount": it.get("amount"),
    })

df = pd.DataFrame(rows, columns=["date", "user.id", "user.display", "amount"])
df.to_excel("commission_raw.xlsx", index=False)  # hoặc to_csv(...)

Best practices & lưu ý

page_size: đặt tối đa (thường 20,000) để giảm request.

req_per_sec: giữ ở 2–3 rps (tùy rate-limit).

boundary_mode='closed-open': [start, end) nối cửa sổ không trùng/khuyết.

split_by_day=True: ổn định mật độ, giảm overflow.

Không convert timezone nếu muốn ngày đúng như API → dùng item["date"][:10].

Đừng hardcode filter trong lib; truyền qua cfg.params từ ứng dụng (VD: chargedBack, transferFilters, ...).

Song song: nếu dữ liệu rất lớn, có thể chạy song song theo ngày ở phía ứng dụng (quản rps tổng).

Khắc phục sự cố

422 khi page>0 với datePeriod: là hành vi Cyclos. Dùng time windows (lib đã xử lý).

Batch đầu không đủ 20k: vì chia theo thời gian, không phải offset; cửa sổ ít dữ liệu sẽ trả đúng số ít đó.

Sai ngày (ví dụ ra 09 thay vì 10): không parse đổi TZ; lấy đúng item["date"].

Thiếu/đúp ở ranh: dùng boundary_mode='closed-open'; để lib tự chia cửa sổ/auto-split.

Giấy phép & phiên bản

__version__ = "1.0.0" (điền theo thực tế của bạn).

License: MIT / Apache-2.0 / … (chọn và cập nhật vào repo).