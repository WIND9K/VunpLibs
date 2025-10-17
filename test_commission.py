# test_commission.py — Xuất Excel: date, user.id, user.display, amount (mỗi giao dịch 1 dòng, không tổng)
from __future__ import annotations

import os
from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import pandas as pd

from onuslibs.client import OnusLibsClient
from onuslibs.pagination import fetch_all, ConfigLoader, make_client_request, wrap_dateperiod

# ========== 1) ENV & CẤU HÌNH CƠ BẢN ==========
load_dotenv()

BASE_URL = os.getenv("ONUSLIBS_BASE_URL", "https://wallet.vndc.io").strip().replace("…", "").replace("...", "").rstrip("/")
START    = os.getenv("ONUSLIBS_START", "2025-10-10T00:00:00")
END      = os.getenv("ONUSLIBS_END",   "2025-10-11T23:59:59")

PAGE_SIZE        = int(os.getenv("ONUSLIBS_PAGE_SIZE", "20000"))  # ≤ 20000 theo Cyclos
RPS              = float(os.getenv("ONUSLIBS_RPS", "3"))
PROBE_PAGE_SIZE  = int(os.getenv("ONUSLIBS_PROBE_SIZE", "1"))
EPSILON_SECONDS  = int(os.getenv("ONUSLIBS_EPSILON", "1"))
BOUNDARY_MODE    = os.getenv("ONUSLIBS_BOUNDARY", "closed-open").lower()  # 'closed-open' khuyến nghị

ENDPOINT = os.getenv("ONUSLIBS_ENDPOINT", "/api/vndc_commission/accounts/vndc_commission_acc/history")
DEFAULT_PARAMS = {
    "chargedBack": os.getenv("ONUSLIBS_CHARGEDBACK", "false"),
    "transferFilters": os.getenv("ONUSLIBS_TRANSFER_FILTERS", "vndc_commission_acc.commission_buysell"),
}

OUTPUT_XLSX = os.getenv("ONUSLIBS_OUTPUT", "commission_raw.xlsx")

# ========== 2) VALIDATE BASE_URL ==========
u = urlparse(BASE_URL)
assert u.scheme in ("http", "https") and u.hostname, f"BASE_URL invalid: {repr(BASE_URL)}"

print("🔎 BASE_URL =", repr(BASE_URL))
print(f"🔧 pageSize={PAGE_SIZE} | rps={RPS} | probe={PROBE_PAGE_SIZE} | epsilon={EPSILON_SECONDS} | boundary={BOUNDARY_MODE}")
print(f"▶️ Range: {START} → {END}")
print(f"📤 Excel out: {OUTPUT_XLSX}")

# ========== 3) CLIENT + ADAPTER ==========
client = OnusLibsClient(base_url=BASE_URL)
_request_fn = wrap_dateperiod(make_client_request(client))

def debug_request(method, endpoint, params):
    status, data, headers = _request_fn(method, endpoint, params)
    show = {k: v for k, v in headers.items() if k.lower().startswith("x-")}
    print(f"[{params.get('page', 0)}] HEADERS:", show)
    return status, data, headers

# ========== 4) CẤU HÌNH LIB (lib tự chia theo ngày + split overflow) ==========
cfg = ConfigLoader.load(overrides={
    "endpoint": ENDPOINT,
    "method": "GET",
    "params": DEFAULT_PARAMS,
    "paging": {
        "page_param": "page",
        "per_page_param": "pageSize",
        "page_size": PAGE_SIZE
    },
    "limits": {
        "req_per_sec": RPS
    },
    "strategy": {
        "probe_page_size": PROBE_PAGE_SIZE,
        "epsilon_seconds": EPSILON_SECONDS,
        "boundary_mode": BOUNDARY_MODE,
        "split_by_day": True,  # 🌟 lib tự cắt [day, nextDay)
        # (lib sẽ tự split khung nếu overflow dựa vào X- headers)
    }
})

# ========== 5) HÀM TRÍCH TRƯỜNG THEO MAPPING BẠN YÊU CẦU ==========
def _get(obj: Dict[str, Any], path: str) -> Optional[Any]:
    cur = obj
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

def _pick_date_as_api(item: Dict[str, Any]) -> str:
    """
    Lấy đúng trường 'date' do API trả về, KHÔNG convert timezone.
    - Nếu có dạng 'YYYY-MM-DDTHH:mm:ss...' hoặc có khoảng trắng, cắt 10 ký tự đầu.
    - Nếu đã là 'YYYY-MM-DD' thì giữ nguyên.
    - Nếu định dạng khác, trả nguyên chuỗi (để bạn dễ đối soát).
    """
    v = item.get("date")
    if v is None:
        # Không fallback sang executedAt/createdAt để tránh lệch ngày do TZ
        return ""
    if not isinstance(v, str):
        # nếu API trả epoch/number, vẫn không convert TZ: chỉ cố gắng format yyyy-MM-dd UTC-naive
        try:
            # nếu bạn không muốn giả định epoch → để nguyên chuỗi str(v)
            from datetime import datetime
            return datetime.utcfromtimestamp(int(v)).strftime("%Y-%m-%d")
        except Exception:
            return str(v)
    s = v.strip()
    if len(s) >= 10 and ("T" in s or " " in s):
        return s[:10]
    # 'YYYY-MM-DD' → giữ nguyên
    return s

def _pick_user_id(item: Dict[str, Any]) -> str:
    v = _get(item, "relatedAccount.user.id")
    return str(v) if v is not None else "unknown"

def _pick_user_display(item: Dict[str, Any]) -> str:
    v = _get(item, "relatedAccount.user.display")
    return str(v) if v is not None else ""

def _pick_amount(item: Dict[str, Any]):
    # amount theo API (không tổng, không ép abs)
    v = item.get("amount")
    # Ghi ra Excel: nếu là số -> float; nếu string số -> float; còn lại -> str
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        ss = v.replace(",", "").strip()
        try:
            return float(ss)
        except Exception:
            return v  # để nguyên chuỗi nếu không parse được
    if isinstance(v, dict) and "value" in v:
        try:
            return float(str(v["value"]).replace(",", ""))
        except Exception:
            return str(v["value"])
    return v if v is not None else 0

# ========== 6) LẤY DỮ LIỆU → MỖI GIAO DỊCH 1 DÒNG ==========
rows = []

def on_batch(items):
    for it in items:
        rows.append({
            "date": _pick_date_as_api(it),             # đúng 'date' của API, chỉ cắt HH:mm:ss
            "user.id": _pick_user_id(it),              # relatedAccount.user.id
            "user.display": _pick_user_display(it),    # relatedAccount.user.display
            "amount": _pick_amount(it),                # amount (raw)
        })

start_date = datetime.fromisoformat(START)
end_date   = datetime.fromisoformat(END)

for _ in fetch_all(
    cfg,
    start_date=start_date,
    end_date=end_date,
    client_request=debug_request,
    on_batch=on_batch
):
    pass

# ========== 7) XUẤT EXCEL (.xlsx) ==========
df = pd.DataFrame(rows, columns=["date", "user.id", "user.display", "amount"])
if not df.empty:
    df.sort_values(by=["date", "user.id"], inplace=True)

engine = None
try:
    import openpyxl  # noqa
    engine = "openpyxl"
except Exception:
    try:
        import xlsxwriter  # noqa
        engine = "xlsxwriter"
    except Exception:
        engine = None

if engine:
    with pd.ExcelWriter(OUTPUT_XLSX, engine=engine) as writer:
        df.to_excel(writer, index=False, sheet_name="Raw")
else:
    # fallback CSV nếu chưa cài engine excel
    OUTPUT_XLSX = os.path.splitext(OUTPUT_XLSX)[0] + ".csv"
    df.to_csv(OUTPUT_XLSX, index=False, encoding="utf-8")

print("\n====== DONE ======")
print(f"🧾 Rows (raw): {len(df)}")
print(f"💾 Saved: {OUTPUT_XLSX}")
