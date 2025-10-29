OnusLibs v2 — ETL mini cho Cyclos/ONUS API

OnusLibs v2 là thư viện Python phục vụ ETL/report với Cyclos/ONUS API, ưu tiên an toàn, ổn định, hiệu năng. Thư viện có thể dùng DLT như “core” (tuỳ chọn), đồng thời bổ sung thuật toán phân trang v2 đã được kiểm thử độc lập.

Tính năng

Bảo mật token (Secret Manager):

Keyring (khuyên dùng Production): lưu trong Credential Manager/Keychain/Secret Service.

Fernet file mã hoá: .env.enc + config/security/secret.key tách biệt.

ENV: chỉ dùng DEV/local.

Phân trang v2:

Đa luồng cấp ngày (day_workers).

Nội ngày: segmented-by-total theo header X-Total-Count, X-Page-Size + bisect khi đoạn “đầy” (tránh miss record trùng timestamp).

Limiter req_per_sec, timeout_s mỗi request.

Fallback header paging (tuỳ chọn) để tương thích API cũ.

Tách bạch: Thư viện không tự đọc TOML; các test/app ngoài có thể đọc TOML rồi truyền tham số vào thư viện.

DLT integration (tuỳ chọn): dlt_source.py để dùng pipeline DLT; các phần DLT không xử lý được sẽ do module phụ của OnusLibs đảm trách.

Cấu trúc dự án
OnusLibs/
├─ onuslibs/
│  ├─ __init__.py                 # public API (vd: fetch_all, …)
│  ├─ config.py
│  ├─ dlt_source.py               # nguồn DLT (tuỳ chọn dùng)
│  ├─ http_client.py              # httpx client + headers (đọc token qua secrets.manager)
│  ├─ settings.py                 # OnusSettings (đọc ENV, defaults runtime)
│  ├─ simple.py                   # no-datePeriod helpers (vd: users_by_ids)
│  ├─ utils.py                    # parse_filters, helpers
│  ├─ config/
│  │  └─ onuslibs.toml            # chỉ cho test/runner, thư viện không tự đọc
│  ├─ pagination/
│  │  ├─ segmented.py             # segmented-by-total + bisect (v2)
│  │  ├─ header_paging.py         # paging tuần tự theo header (fallback/compat)
│  │  ├─ time_windows.py          # cắt ngày [day, next_day)
│  │  └─ limiter.py               # limiter/điều phối RPS (nếu dùng)
│  └─ secrets/
│     ├─ __init__.py
│     ├─ manager.py               # chọn backend keyring/fernet/env
│     ├─ keyring_backend.py       # đọc/ghi/xoá token trong Keyring
│     ├─ fernet_backend.py        # đọc .env.enc bằng secret.key
│     └─ env_backend.py           # DEV: lấy token từ ENV
│
├─ app_commission.py              # ví dụ app ngoài (datePeriod)
├─ app_config.py                  # cấu hình chuẩn hoá cho app_commission
├─ app_users.py                   # ví dụ app ngoài (no-datePeriod)
├─ app_users_config.py            # cấu hình chuẩn hoá cho app_users
├─ app_dateperiod_min.py          # mẫu tối giản: ghi đè cấu hình khi gọi thư viện
├─ run_pipeline.py                # test DLT + thuật toán v2 đã kiểm thử
├─ test_dateperiod_simple.py      # test đọc TOML (datePeriod)
├─ test_users_no_dateperiod_simple.py   # test đọc TOML (no-datePeriod)
├─ test_users_no_dateperiod.py.py # test legacy (giữ để tham chiếu)
├─ files/                         # nơi ghi CSV (nếu dùng)
├─ pyproject.toml
├─ .env                           # DEV only (không dùng PROD)
├─ venv/                          # môi trường ảo (khuyên .gitignore)
└─ .git/                          # repo (nếu có)


Khuyến nghị .gitignore:
venv/, .env, config/security/secret.key, *.db, files/*.csv

Cài đặt
python -m pip install -U httpx tenacity python-dotenv dlt cryptography keyring
# hoặc: pip install -e .  (nếu dùng pyproject.toml của dự án)

Biến môi trường bắt buộc

ONUSLIBS_BASE_URL — ví dụ: https://wallet.vndc.io

Token lấy qua Secret Manager (Keyring/Fernet/ENV).
Khuyến nghị Production:

ONUSLIBS_FALLBACK_ENV=false

Bảo mật token (Secret Manager)
A) Keyring (khuyên dùng Production)

Đặt token vào Keyring (một lần):

python -c "from onuslibs.secrets.keyring_backend import set_access_client_token_to_keyring as setk; setk('OnusLibs','ACCESS_CLIENT_TOKEN','<TOKEN>')"


Chạy app:

$env:ONUSLIBS_SECRETS_BACKEND = "keyring"
$env:ONUSLIBS_KEYRING_SERVICE = "OnusLibs"          # hoặc 'App1' nếu bạn set service App1
$env:ONUSLIBS_KEYRING_ITEM    = "ACCESS_CLIENT_TOKEN"
$env:ONUSLIBS_BASE_URL        = "https://wallet.vndc.io"
$env:ONUSLIBS_FALLBACK_ENV    = "false"             # khuyến nghị
python app_commission.py


Ví dụ dùng service riêng:

Đặt token: setk('App1','ACCESS_CLIENT_TOKEN','<TOKEN>')

ENV khi chạy: ONUSLIBS_SECRETS_BACKEND=keyring, ONUSLIBS_KEYRING_SERVICE=App1.

B) Fernet file mã hoá

Tạo key + file mã hoá (một lần):

from cryptography.fernet import Fernet
from pathlib import Path
import json
key = Fernet.generate_key()
Path("config/security").mkdir(parents=True, exist_ok=True)
Path("config/security/secret.key").write_bytes(key)
payload = json.dumps({"ONUSLIBS_ACCESS_CLIENT_TOKEN":"<TOKEN>"}).encode("utf-8")
enc = Fernet(key).encrypt(payload)
Path(".env.enc").write_bytes(enc)
print("OK: wrote secret.key & .env.enc")


Chạy app:

$env:ONUSLIBS_SECRETS_BACKEND = "fernet"
$env:ONUSLIBS_ENC_FILE        = ".env.enc"
$env:ONUSLIBS_FERNET_KEY_FILE = "config/security/secret.key"
$env:ONUSLIBS_BASE_URL        = "https://wallet.vndc.io"
$env:ONUSLIBS_FALLBACK_ENV    = "false"
python app_commission.py


Không commit config/security/secret.key. .env.enc có thể commit (đã mã hoá).

C) ENV (DEV only)
$env:ONUSLIBS_SECRETS_BACKEND = "env"
$env:ONUSLIBS_BASE_URL        = "https://wallet.vndc.io"
$env:ONUSLIBS_ACCESS_CLIENT_TOKEN = "<TOKEN>"
python app_commission.py

Sử dụng thư viện
1) API có datePeriod (ví dụ: commission history)
from datetime import datetime, timezone
from onuslibs import fetch_all
from onuslibs.utils import parse_filters
from onuslibs.settings import OnusSettings

_ = OnusSettings()  # xác thực ENV & defaults

rows = fetch_all(
    endpoint="/api/vndc_commission/accounts/vndc_commission_acc/history",
    start=datetime(2025,10,10,0,0,0,tzinfo=timezone.utc),
    end  =datetime(2025,10,11,23,59,59,tzinfo=timezone.utc),
    filters=parse_filters("chargedBack=false&transferFilters=vndc_commission_acc.commission_buysell"),
    fields=["date","transactionNumber","relatedAccount.user.id","relatedAccount.user.display","amount"],
    split_by_day=True,
    page_size=10000,
    day_workers=2,
    req_per_sec=3.0,
    http2=True,
    timeout_s=30.0,
    # thuật toán v2
    force_segmented_paging=True,
    segment_safety_ratio=0.95,
    segment_min_seconds=1.0,
)
print(len(rows))

2) API không có datePeriod (theo danh sách ids)
from onuslibs.settings import OnusSettings
from onuslibs.simple import users_by_ids

_ = OnusSettings()

rows = users_by_ids(
    ids=[
        "6277729705839478686","6277729705841389470","6277729705866067870",
        "6277729705874792350","6277729705876799390","6277729705899581342",
        "6277729705903484830","6277729705904418718","6277729705925767070",
    ],
    endpoint="/api/users",
    id_param="usersToInclude",
    fields=["id","username","name","email"],
    page_size=10000,
    timeout_s=30.0,
    http2=True,
)
print(len(rows))

Mẫu ứng dụng ngoài (đã tách cấu hình)

app_commission.py + app_config.py: ví dụ datePeriod, cấu hình chuẩn hoá bằng dataclass; xuất CSV.

app_users.py + app_users_config.py: ví dụ no-datePeriod; lấy theo danh sách ids; xuất CSV.

app_dateperiod_min.py: mẫu tối giản không đọc TOML, ghi đè cấu hình trực tiếp khi gọi fetch_all.

Mặc định CSV ghi vào files/*.csv. Có thể đổi đường dẫn trong file config app.

Test/Runner (đọc TOML → truyền tham số vào thư viện)

test_dateperiod_simple.py: đọc onuslibs/config/onuslibs.toml rồi gọi fetch_all(...).

test_users_no_dateperiod_simple.py: đọc TOML → users_by_ids(...).

run_pipeline.py: kịch bản DLT + thuật toán v2 (segmented-by-total + bisect + limiter + day_workers).

Thư viện không tự đọc TOML; test/app đọc TOML và truyền vào OnusLibs.

Thuật toán phân trang v2

Outer (cấp ngày): chạy song song theo day_workers.

Inner (nội ngày):

segmented-by-total (mặc định):

Gọi page=0 để lấy header: X-Total-Count, X-Page-Size, X-Page-Count, X-Has-Next-Page.

Tính segments ≈ ceil(Total / page_size).

Mỗi segment luôn khởi đầu page=0 để tránh 422 với page>0 (tuỳ API).

Bisect khi segment “đầy” (~= page_size * safety_ratio) để không bỏ sót record trùng timestamp (≤1s có thể nhiều record).

Header paging fallback: đặt force_segmented_paging=False để lướt page=0,1,2,… theo server (giữ tương thích cũ).

Limiter: req_per_sec; timeout: timeout_s mỗi request.

Headers API quan trọng

X-Total-Count, X-Page-Size, X-Current-Page, X-Page-Count, X-Has-Next-Page

Access-Control-Expose-Headers phải expose các header trên (API hiện có).

Troubleshooting

RuntimeError: Thiếu ENV ONUSLIBS_BASE_URL → export ENV này.

Thiếu token:

Keyring: chưa set vào Keyring hoặc sai ONUSLIBS_KEYRING_SERVICE.

Fernet: secret.key không khớp .env.enc hoặc tắt/thiếu fallback ENV.

422 Unprocessable Entity → sai tham số/datePeriod; ưu tiên segmented-by-total thay vì page>0.

ReadTimeout/ConnectError → tăng timeout_s, giảm req_per_sec, kiểm tra mạng/TLS/Proxy.

can't compare offset-naive and offset-aware datetimes → luôn truyền datetime có tzinfo=UTC.

Bảo mật & Hardening

Không log token; không bật HTTP raw trace ở PROD.

HTTPS + verify TLS.

Quyền file: hạn chế đọc config/security/secret.key.

Rotate token định kỳ (Keyring/.env.enc).

Không commit secrets (.env, secret.key).

Gợi ý hiệu năng

page_size: 10.000 (khớp header API).

req_per_sec: 2–3 RPS an toàn.

day_workers: 2–5 tuỳ tài nguyên/mạng.

Bật force_segmented_paging=True để đảm bảo đầy đủ dữ liệu khi nội ngày có nhiều record trùng giây.