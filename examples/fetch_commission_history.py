# -*- coding: utf-8 -*-
"""
Fetch commission history (VNDC) qua OnusLibs Facade – cấu hình tách ở đầu trang.

Chạy mẫu:
  python -m examples.fetch_commission_history --date 2025-10-11
  python -m examples.fetch_commission_history --start-date 2025-10-01 --end-date 2025-10-11 --preset full
  python -m examples.fetch_commission_history --date 2025-10-11 --fields date,amount,description
"""

from __future__ import annotations
import os
import sys
import argparse
from typing import List, Dict, Any, Optional

# =========================
# CONFIG (tách biệt)
# =========================
ENDPOINT = "/api/vndc_commission/accounts/vndc_commission_acc/history"

# Presets fields – đổi ở đây
PRESETS: Dict[str, List[str]] = {
    "minimal": ["date"],
    "basic":   ["date","transactionNumber","relatedAccount.user.id","relatedAccount.user.display", "amount", "description"],
    "full":    ["date", "amount", "description", "from.name", "to.name", "currency", "txId"],
}

# Mặc định params
DEFAULT_PAGE_SIZE     = 1000
DEFAULT_ORDER         = "dateAsc"  # hoặc "dateDesc"
DEFAULT_FILTER        = "vndc_commission_acc.commission_buysell"
DEFAULT_CHARGED_BACK  = "false"    # "true"/"false"

# =========================
# HELPERS (liên quan cấu hình)
# =========================
def _dedupe(seq) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in seq or []:
        x = str(x).strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

def resolve_fields(
    *,
    preset: Optional[str] = None,
    fields_csv: Optional[str] = None,
    fields_file: Optional[str] = None,
) -> List[str]:
    """
    Hợp nhất fields từ preset + CSV + file (mỗi dòng 1 field). Ưu tiên: preset -> CSV -> file.
    """
    parts: List[str] = []
    if preset:
        ps = PRESETS.get(preset)
        if ps is None:
            raise SystemExit(f"Preset '{preset}' không tồn tại. Chọn: {', '.join(PRESETS)}")
        parts.extend(ps)
    if fields_csv:
        parts.extend([p.strip() for p in fields_csv.split(",") if p.strip()])
    if fields_file:
        with open(fields_file, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    parts.append(s)
    parts = _dedupe(parts)
    return parts or PRESETS["minimal"][:]  # fallback

def _date_period_for_day(d: str) -> str:
    return f"{d}T00:00:00.000,{d}T23:59:59.999"

def _date_period_range(start_date: str, end_date: str) -> str:
    return f"{start_date}T00:00:00.000,{end_date}T23:59:59.999"

def build_params(
    *,
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    charged_back: str = DEFAULT_CHARGED_BACK,
    transfer_filters: str = DEFAULT_FILTER,
    order: str = DEFAULT_ORDER,
    page: int = 0,
) -> Dict[str, str]:
    """
    Trả dict params gọn để đưa thẳng vào fetch_json.
    """
    if date and (start_date or end_date):
        raise SystemExit("Chỉ chọn 1 trong --date hoặc --start-date/--end-date")
    if date:
        dp = _date_period_for_day(date)
    else:
        if not (start_date and end_date):
            raise SystemExit("Thiếu --end-date khi dùng --start-date")
        dp = _date_period_range(start_date, end_date)

    return {
        "chargedBack":     charged_back,
        "transferFilters": transfer_filters,
        "datePeriod":      dp,
        "orderBy":         order,
        "page":            str(page),  # an toàn
    }

def _parse_int(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except Exception:
        return None

# =========================
# RUNTIME (app chạy)
# =========================
# Thử import print_json (tools/print_json.py); nếu chạy trực tiếp file, thêm sys.path
try:
    from tools.print_json import print_json
except ModuleNotFoundError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    try:
        from tools.print_json import print_json
    except Exception:
        import json
        def print_json(data: Any, **kwargs):
            print(json.dumps(data, ensure_ascii=False, indent=2))

from onuslibs.config.settings import OnusSettings
from onuslibs.unified.api import fetch_json
from onuslibs.http.client import HttpClient
from onuslibs.security.headers import build_headers

def try_get_api_total_count(settings: OnusSettings, endpoint: str, params: Dict[str, Any]) -> Optional[int]:
    """
    Gọi 1 request nhỏ (page=0,pageSize=1) để đọc header X-Total-Count nếu có. Không ném lỗi.
    """
    cli = HttpClient(settings)
    hdrs = build_headers(settings)
    p = dict(params); p["page"] = 0; p["pageSize"] = 1
    try:
        resp = cli.get(endpoint, params=p, headers=hdrs)
        resp.raise_for_status()
        headers_l = {k.lower(): v for k, v in resp.headers.items()}
        return _parse_int(headers_l.get("x-total-count"))
    except Exception:
        return None
    finally:
        try: cli.close()
        except Exception: pass

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch VNDC commission history via OnusLibs (config tách ở đầu file).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="Ngày (YYYY-MM-DD).", default=None)
    g.add_argument("--start-date", help="Ngày bắt đầu (YYYY-MM-DD).", default=None)
    p.add_argument("--end-date", help="Ngày kết thúc (YYYY-MM-DD) – bắt buộc nếu dùng --start-date.", default=None)

    # Fields (đã gom sẵn ở cấu hình)
    p.add_argument("--preset", choices=list(PRESETS.keys()), default="basic",
                   help=f"Chọn sẵn bộ fields: {', '.join(PRESETS.keys())} (mặc định basic).")
    p.add_argument("--fields", help="CSV fields bổ sung/ghi đè.", default=None)
    p.add_argument("--fields-file", help="File chứa danh sách fields (mỗi dòng 1 field).", default=None)

    # Params khác dùng mặc định từ cấu hình
    p.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help=f"pageSize mỗi trang (mặc định {DEFAULT_PAGE_SIZE}).")
    p.add_argument("--order", choices=["dateAsc", "dateDesc"], default=DEFAULT_ORDER, help=f"Thứ tự theo API (mặc định {DEFAULT_ORDER}).")
    p.add_argument("--filters", default=DEFAULT_FILTER, help=f"transferFilters (mặc định {DEFAULT_FILTER}).")
    p.add_argument("--charged-back", choices=["true","false"], default=DEFAULT_CHARGED_BACK, help=f"chargedBack (mặc định {DEFAULT_CHARGED_BACK}).")

    p.add_argument("--out-json", help="Ghi ra file JSON.", default=None)
    # Bạn có thể thêm --out-csv nếu muốn, dùng tools.write_csv
    return p

def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)

    # 1) Fields (preset/CSV/file)
    fields = resolve_fields(
        preset=args.preset,
        fields_csv=args.fields,
        fields_file=args.fields_file,
    )

    # 2) Params (tách ở đầu trang)
    params = build_params(
        date=args.date,
        start_date=args.start_date,
        end_date=args.end_date,
        charged_back=args.charged_back,
        transfer_filters=args.filters,
        order=args.order,
        page=0,
    )

    # 3) Fetch
    s = OnusSettings()  # tự nạp ENV/.env
    rows: List[Dict[str, Any]] = fetch_json(
        endpoint=ENDPOINT,
        params=params,
        fields=fields,          # list[str]
        paginate=True,          # lịch sử → nên phân trang
        page_size=args.page_size,
        order_by=None,          # đã set orderBy trong params
        settings=s,
        unique_key=None,
        parallel=True,
    )

    # 4) Xuất & thống kê
    if args.out_json:
        # print_json(rows, to_file=args.out_json)
        print(f"Đã ghi JSON: {len(rows)} dòng -> {args.out_json}")
    else:
        print_json(rows)
        print(f"\nTotal fetched rows: {len(rows)}")

    api_total = try_get_api_total_count(s, ENDPOINT, params)
    if api_total is not None:
        print(f"API reported X-Total-Count: {api_total}")

    

    from tools.write_csv import write_csv

    out = "commission_history.csv"
    n = write_csv(rows, out)  # auto dò cột, tự flatten nested dict
    print(f"Đã ghi {n} dòng vào {out}")

    return 0
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
