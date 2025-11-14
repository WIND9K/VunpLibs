# -*- coding: utf-8 -*-
"""
Example: Fetch VNDC Offchain Send OnusPro transfers (pro_vndc_send)
using OnusLibs fetch_json.

Chạy mẫu:
  python -m examples.pro_vndc_send --date 2025-11-11

Yêu cầu:
  - Đã set ENV OnusLibs:
      ONUSLIBS_BASE_URL=https://wallet.vndc.io
      ONUSLIBS_PAGE_SIZE=10000              # tuỳ chọn
      ONUSLIBS_DATE_SEGMENT_HOURS=0         # hoặc >0 nếu muốn segment theo giờ
      ONUSLIBS_PARALLEL=true/false          # song song phân trang
  - Đã cấu hình token trong keyring/env theo OnusLibs spec.

  python -m examples.pro_vndc_send --date 2025-11-11

"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any, Dict, List

from onuslibs.unified.api import fetch_json
from onuslibs.utils.date_utils import build_date_period  # dùng helper chung


# ==========================
# Cấu hình endpoint & fields
# ==========================

ENDPOINT = "/api/transfers"

TRANSFER_TYPES = "vndcacc.vndc_offchain_send_onuspro"

FIELDS = [
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

def build_params_for_date(day: str) -> Dict[str, Any]:
    """Build params cho 1 ngày, dùng cho endpoint /api/transfers."""
    return {
        "transferTypes": TRANSFER_TYPES,
        "amountRange": "",
        # dùng helper của OnusLibs: start = end = day
        "datePeriod": build_date_period(day, day),
        "user": "",
        # pageSize, page sẽ do fetch_json + HeaderPager xử lý
    }


# ==========================
# CLI
# ==========================

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch VNDC Offchain Send OnusPro transfers via OnusLibs."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Ngày cần fetch (YYYY-MM-DD). Ví dụ: 2025-11-11",
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
    return parser.parse_args(argv)


# ==========================
# Main
# ==========================

def main(argv: List[str]) -> int:
    args = parse_args(argv)

    # Validate date format sớm một chút (optional)
    try:
        date.fromisoformat(args.date)
    except Exception:
        print(f"[ERROR] --date không đúng format YYYY-MM-DD: {args.date!r}", file=sys.stderr)
        return 1

    params = build_params_for_date(args.date)

    print(f"Đang fetch transfers OnusPro cho ngày {args.date} ...")

    rows: List[Dict[str, Any]] = fetch_json(
        endpoint=ENDPOINT,
        params=params,
        fields=FIELDS,
        # order_by có thể để None nếu backend đã mặc định theo date,
        # hoặc set "dateAsc"/"dateDesc" nếu muốn rõ ràng:
        order_by=None,
        unique_key="transactionNumber",
        # strict_fields=True,   # DEV/TEST nếu muốn canh schema
        # on_batch=...         # nếu muốn stream về DB
        parallel=True,
    )

    total = len(rows)
    print(f"Hoàn tất, tổng số record: {total}")

    # In demo vài dòng
    # limit = max(0, int(args.limit_print))
    # if limit > 0:
    #     print(f"\n===== {min(limit, total)} dòng đầu tiên =====")
    #     for i, r in enumerate(rows[:limit], start=1):
    #         print(f"[{i}] tx={r.get('transactionNumber')} date={r.get('date')} amount={r.get('amount')}")
    #         print(
    #             f"    from: {r.get('from', {}).get('user', {}).get('id')} - "
    #             f"{r.get('from', {}).get('user', {}).get('display')}"
    #         )
    #         print(
    #             f"    to  : {r.get('to', {}).get('user', {}).get('id')} - "
    #             f"{r.get('to', {}).get('user', {}).get('display')}"
    #         )
    #         print(f"    type: {r.get('type', {}).get('internalName')}")
    #         print("-" * 40)

    # Nếu muốn dump full JSON
    if args.json:
        print("\n===== JSON full =====")
        print(json.dumps(rows, ensure_ascii=False))

    from tools.write_csv import write_csv

    out = "files/commission_history.csv"
    n = write_csv(rows, out)  # auto dò cột, tự flatten nested dict
    print(f"Đã ghi {n} dòng vào {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
