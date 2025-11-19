# -*- coding: utf-8 -*-
"""
Example: Fetch VNDC Offchain Send OnusPro transfers (pro_vndc_send)
using OnusLibs fetch_json (hybrid auto-segment).

Chạy mẫu:
  # Lấy 1 ngày
  python -m examples.pro_vndc_send --date 2025-11-11

  # Lấy nhiều ngày (test hybrid auto-segment range dài)
  python -m examples.pro_vndc_send --start-date 2025-11-0 --end-date 2025-11-15

  # Lấy nhiều ngày và ghi CSV mặc định
  python -m examples.pro_vndc_send --start-date 2025-11-10 --end-date 2025-11-15 --out-csv

Yêu cầu:
  - Đã set ENV OnusLibs, ví dụ:
      ONUSLIBS_BASE_URL=https://wallet.vndc.io
      ONUSLIBS_PAGE_SIZE=2000                 # tuỳ chọn
      ONUSLIBS_MAX_WINDOW_DAYS=1              # chia theo ngày
      ONUSLIBS_MAX_ROWS_PER_WINDOW=8000       # trần an toàn < 10k record/segment
      ONUSLIBS_AUTO_SEGMENT=true
      ONUSLIBS_MAX_SEGMENT_SPLIT_DEPTH=4
      ONUSLIBS_PARALLEL=true/false            # song song phân trang
      ONUSLIBS_SEGMENT_PARALLEL=true/false    # song song theo segment
  - Đã cấu hình token trong keyring/env theo OnusLibs spec.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Any, Dict, List, Optional

from onuslibs.unified.api import fetch_json
from onuslibs.utils.date_utils import build_date_period  # dùng helper chung

# ==========================
# Cấu hình endpoint & fields
# ==========================

ENDPOINT = "/api/transfers"

# Theo spec cũ: dùng transferTypes cho pro offchain send
TRANSFER_TYPES = "vndcacc.vndc_offchain_send_onuspro"

FIELDS: List[str] = [
    "transactionNumber",
    "date",
    "amount",
    "from.user.id",
    "from.user.display",
    "to.user.id",
    "to.user.display",
    "type.internalName",
]


# ==========================
# Helpers build params
# ==========================

def build_params(start_day: str, end_day: str) -> Dict[str, Any]:
    """Build params cho khoảng ngày [start_day, end_day]."""
    return {
        "transferTypes": TRANSFER_TYPES,
        "amountRange": "",
        "datePeriod": build_date_period(start_day, end_day),
        "user": "",
        # pageSize, page, orderBy sẽ do fetch_json + HeaderPager xử lý
    }


def resolve_fields(fields_csv: Optional[str]) -> List[str]:
    """Cho phép override FIELDS qua --fields, nếu cần."""
    if not fields_csv:
        return FIELDS[:]
    parts = [p.strip() for p in fields_csv.split(",") if p.strip()]
    return parts or FIELDS[:]


# ==========================
# write_csv helper (tools hoặc fallback)
# ==========================

try:
    from tools.write_csv import write_csv
except ModuleNotFoundError:  # fallback đơn giản
    import csv

    def write_csv(rows: List[Dict[str, Any]], path: str) -> int:
        """Fallback: ghi CSV đơn giản, chỉ flatten level 1."""
        if not rows:
            return 0
        fieldnames = sorted({k for r in rows for k in r.keys()})
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)


# ==========================
# CLI
# ==========================

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch VNDC Offchain Send OnusPro transfers via OnusLibs."
    )

    # Chọn 1 trong 2 mode: --date hoặc (--start-date + --end-date)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--date",
        help="Lấy 1 ngày (YYYY-MM-DD). Ví dụ: 2025-11-11",
        default=None,
    )
    g.add_argument(
        "--start-date",
        help="Ngày bắt đầu (YYYY-MM-DD). Ví dụ: 2025-11-01",
        default=None,
    )

    parser.add_argument(
        "--end-date",
        help="Ngày kết thúc (YYYY-MM-DD) – bắt buộc nếu dùng --start-date.",
        default=None,
    )
    parser.add_argument(
        "--limit-print",
        type=int,
        default=5,
        help="Số dòng in demo ra màn hình (mặc định 5).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="In toàn bộ kết quả ra stdout dạng JSON (1 dòng). Cẩn thận nếu nhiều dữ liệu.",
    )
    parser.add_argument(
        "--fields",
        help="Danh sách fields dạng CSV (override FIELDS mặc định).",
        default=None,
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="pageSize mỗi trang (mặc định đọc từ ONUSLIBS_PAGE_SIZE).",
    )
    parser.add_argument(
        "--out-csv",
        help="Ghi kết quả ra CSV (mặc định: files/pro_vndc_send.csv nếu không chỉ định).",
        nargs="?",
        const="files/pro_vndc_send.csv",
        default=None,
    )

    return parser.parse_args(argv)


# ==========================
# Main
# ==========================

def main(argv: List[str]) -> int:
    args = parse_args(argv)

    # Xác định start_date / end_date
    if args.date:
        start_date = end_date = args.date
    else:
        if not args.start_date or not args.end_date:
            print("[ERROR] Phải truyền đủ --start-date và --end-date khi không dùng --date", file=sys.stderr)
            return 1
        start_date = args.start_date
        end_date = args.end_date

    # Validate format ngày sớm
    try:
        date.fromisoformat(start_date)
        date.fromisoformat(end_date)
    except Exception:
        print(
            f"[ERROR] Ngày không đúng format YYYY-MM-DD: start={start_date!r}, end={end_date!r}",
            file=sys.stderr,
        )
        return 1

    # Build params & fields
    params = build_params(start_date, end_date)
    fields = resolve_fields(args.fields)

    if start_date == end_date:
        print(f"Đang fetch VNDC Offchain Send OnusPro cho ngày {start_date} ...")
    else:
        print(f"Đang fetch VNDC Offchain Send OnusPro cho khoảng {start_date} -> {end_date} ...")

    # Gọi OnusLibs
    rows: List[Dict[str, Any]] = fetch_json(
        endpoint=ENDPOINT,
        params=params,
        fields=fields,
        page_size=args.page_size,
        # order_by có thể để None nếu backend mặc định theo date,
        # hoặc "dateAsc"/"dateDesc" nếu muốn rõ ràng; để None là an toàn.
        order_by=None,
        unique_key="transactionNumber",  # chống trùng khi hybrid segment chia nhiều đoạn thời gian
        parallel=True,                   # cho phép song song phân trang (còn tuỳ ONUSLIBS_PARALLEL)
    )

    total = len(rows)
    print(f"Hoàn tất, tổng số record: {total}")

    # In demo vài dòng (nếu không dump JSON full)
    limit = max(0, int(args.limit_print))
    if not args.json and limit > 0 and total > 0:
        print(f"\n===== {min(limit, total)} dòng đầu tiên =====")
        for i, r in enumerate(rows[:limit], start=1):
            print(f"[{i}] tx={r.get('transactionNumber')} date={r.get('date')} amount={r.get('amount')}")
            print(
                f"    from: {r.get('from', {}).get('user', {}).get('id')} - "
                f"{r.get('from', {}).get('user', {}).get('display')}"
            )
            print(
                f"    to  : {r.get('to', {}).get('user', {}).get('id')} - "
                f"{r.get('to', {}).get('user', {}).get('display')}"
            )
            print(f"    type: {r.get('type', {}).get('internalName')}")
            print("-" * 40)

    # Dump full JSON nếu cần
    if args.json:
        print("\n===== JSON full =====")
        print(json.dumps(rows, ensure_ascii=False))

    # Ghi CSV nếu được yêu cầu
    if args.out_csv:
        out_path = args.out_csv
        n = write_csv(rows, out_path)
        print(f"Đã ghi {n} dòng vào {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
