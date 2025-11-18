# -*- coding: utf-8 -*-
"""Ví dụ dùng OnusLibs: lấy lịch sử USDT onchain receive.

Mục tiêu:
- Code càng đơn giản càng tốt.
- App chỉ quan tâm: endpoint, params (start/end date), fields.
- Toàn bộ phân trang, hybrid auto-segment... để OnusLibs xử lý qua `fetch_json`.

Chạy mẫu:
  # Lấy 1 ngày
  python -m examples.onchain_usdt_receive --date 2025-11-11

  # Lấy nhiều ngày (test hybrid auto-segment range dài)
  python -m examples.onchain_usdt_receive --start-date 2025-11-01 --end-date 2025-11-16

  # Ghi CSV với đường dẫn mặc định
  python -m examples.onchain_usdt_receive --start-date 2025-11-01 --end-date 2025-11-16 --out-csv
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional

from onuslibs.config.settings import OnusSettings
from onuslibs.unified.api import fetch_json
from onuslibs.utils.date_utils import build_date_period

# Thử import helpers in-house (không bắt buộc)
try:
    from tools.print_json import print_json
except ModuleNotFoundError:  # fallback đơn giản
    import json

    def print_json(data: Any, **kwargs: Any) -> None:
        print(json.dumps(data, ensure_ascii=False, indent=2, **kwargs))


try:
    from tools.write_csv import write_csv
except ModuleNotFoundError:
    def write_csv(rows: List[Dict[str, Any]], path: str) -> int:
        """Fallback: ghi CSV rất đơn giản (chỉ phẳng level 1).

        Trong project thật nên dùng tools.write_csv chuẩn.
        """
        import csv

        if not rows:
            return 0
        fieldnames = sorted({k for r in rows for k in r.keys()})
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)


# =========================
# CẤU HÌNH ENDPOINT & FIELDS
# =========================

ENDPOINT = "/api/transfers"

# Fields đúng theo URL mẫu:
#   transactionNumber,date,amount,
#   from.user.id,from.user.display,
#   to.user.id,to.user.display,
#   type.internalName
DEFAULT_FIELDS: List[str] = [
    "transactionNumber",
    "date",
    "amount",
    "from.user.id",
    "from.user.display",
    "to.user.id",
    "to.user.display",
    "type.internalName",
]

# Các filter cố định của endpoint
DEFAULT_TRANSFER_FILTERS = "usdtacc.onchain_receive"
DEFAULT_ORDER = "dateAsc"  # dùng cho order_by trong fetch_json


# =========================
# HELPERS cấu hình / params
# =========================

def resolve_fields(fields_csv: Optional[str]) -> List[str]:
    """Ghép fields: nếu CLI có --fields thì override, ngược lại dùng DEFAULT_FIELDS."""
    if not fields_csv:
        return DEFAULT_FIELDS[:]
    parts = [p.strip() for p in fields_csv.split(",") if p.strip()]
    return parts or DEFAULT_FIELDS[:]


def build_params(start_date: str, end_date: str) -> Dict[str, Any]:
    """Build params đơn giản cho fetch_json.

    - Ghép datePeriod bằng helper của OnusLibs.
    - Không set page / pageSize / orderBy ở đây (để fetch_json lo).
    """
    date_period = build_date_period(start_date, end_date)
    return {
        "transferFilters": DEFAULT_TRANSFER_FILTERS,
        "datePeriod": date_period,
        # có thể bổ sung thêm filter khác nếu cần (direction, status, ...)
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch USDT onchain receive qua OnusLibs (ví dụ đơn giản)."
    )

    # Chọn 1 trong 2 mode: --date hoặc (--start-date + --end-date)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="Lấy 1 ngày (YYYY-MM-DD).", default=None)
    g.add_argument("--start-date", help="Ngày bắt đầu (YYYY-MM-DD).", default=None)

    p.add_argument(
        "--end-date",
        help="Ngày kết thúc (YYYY-MM-DD) – bắt buộc nếu dùng --start-date.",
        default=None,
    )
    p.add_argument(
        "--fields",
        help="Danh sách fields dạng CSV (override DEFAULT_FIELDS).",
        default=None,
    )
    p.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="pageSize mỗi trang (mặc định đọc từ ONUSLIBS_PAGE_SIZE).",
    )
    p.add_argument(
        "--order",
        choices=["dateAsc", "dateDesc"],
        default=DEFAULT_ORDER,
        help=f"Thứ tự sắp xếp (mặc định {DEFAULT_ORDER}).",
    )
    p.add_argument(
        "--out-json",
        help="Ghi toàn bộ kết quả ra file JSON.",
        default=None,
    )
    p.add_argument(
        "--out-csv",
        help="Ghi kết quả ra CSV (mặc định: files/onchain_usdt_receive.csv nếu không chỉ định).",
        nargs="?",
        const="files/onchain_usdt_receive.csv",
        default=None,
    )

    return p


# ============
# MAIN LOGIC
# ============

def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1) Xử lý ngày
    if args.date:
        start_date = end_date = args.date
    else:
        if not args.start_date or not args.end_date:
            raise SystemExit("Phải truyền đủ --start-date và --end-date")
        start_date = args.start_date
        end_date = args.end_date

    # 2) Fields
    fields = resolve_fields(args.fields)

    # 3) Params cho fetch_json
    params = build_params(start_date, end_date)

    # 4) Gọi OnusLibs Facade
    settings = OnusSettings()  # tự đọc .env / ENV (BASE_URL, PAGE_SIZE, auto-segment,…)

    rows: List[Dict[str, Any]] = fetch_json(
        endpoint=ENDPOINT,
        params=params,
        fields=fields,
        page_size=args.page_size,
        paginate=True,          # lịch sử => nên phân trang
        order_by=args.order,    # chuẩn hoá: order_by truyền riêng, không gắn trong params
        settings=settings,
        unique_key="transactionNumber",  # chống trùng nếu segment/time overlap
    )

    # 5) Xuất kết quả
    print(f"Fetched {len(rows)} rows.")
    if args.out_json:
        # print_json(rows, to_file=args.out_json)  # nếu tools.print_json hỗ trợ to_file
        with open(args.out_json, "w", encoding="utf-8") as f:
            import json as _json
            _json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"Đã ghi JSON: {args.out_json}")
    else:
        # In nhanh vài dòng đầu cho dev xem
        if rows:
            # print("Ví dụ 3 dòng đầu:")
            # print_json(rows[:3])
        if len(rows) > 5:
            print(f"... (ẩn bớt, tổng cộng {len(rows)} dòng)")

    if args.out_csv:
        n = write_csv(rows, args.out_csv)
        print(f"Đã ghi {n} dòng vào {args.out_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
