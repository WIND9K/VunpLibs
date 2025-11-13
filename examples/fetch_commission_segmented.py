"""
examples/fetch_commission_segmented.py

Ví dụ dùng OnusLibs với facade cấp cao fetch_json_segmented:

- Đọc ONUSLIBS_* từ ENV (base_url, page_size, date_segment_hours, ...)
- Tự chia nhỏ datePeriod theo ONUSLIBS_DATE_SEGMENT_HOURS
  để tránh backend limit offset ~10k records.
- Vẫn dùng HeaderPager bên dưới để phân trang theo 5 header:
    X-Total-Count, X-Page-Size, X-Current-Page, X-Page-Count, X-Has-Next-Page
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List

from onuslibs.config import OnusSettings
from onuslibs.unified import fetch_json_segmented


# Endpoint commission chuẩn (theo get_commission.py trước đó)
ENDPOINT = "/api/vndc_commission/accounts/vndc_commission_acc/history"

# Chỉ dùng 1 preset duy nhất: "basic"
BASIC_FIELDS = ",".join(
    [
        "date",
        "transactionNumber",
        "relatedAccount.user.id",
        "relatedAccount.user.display",
        "amount",
        "description",
    ]
)

DEFAULT_ORDER = "dateAsc"  # có thể đổi sang dateDesc nếu cần


def build_params(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Tạo params chuẩn cho API commission history.

    - start_date / end_date là YYYY-MM-DD
    - datePeriod luôn là:
        <start>T00:00:00.000,<end>T23:59:59.999
    """
    start_iso = f"{start_date}T00:00:00.000"
    end_iso = f"{end_date}T23:59:59.999"

    return {
        "chargedBack": "false",
        "transferFilters": "vndc_commission_acc.commission_buysell",
        "datePeriod": f"{start_iso},{end_iso}",
        "orderBy": DEFAULT_ORDER,
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch commission history with segmented datePeriod via OnusLibs."
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Ngày bắt đầu (YYYY-MM-DD). Ví dụ: 2025-10-11",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Ngày kết thúc (YYYY-MM-DD). Ví dụ: 2025-10-11",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="Override pageSize nếu cần. Nếu bỏ trống -> dùng ONUSLIBS_PAGE_SIZE.",
    )
    parser.add_argument(
        "--no-paginate",
        action="store_true",
        help="Tắt phân trang (chỉ 1 request / segment). Mặc định là bật paginate.",
    )
    parser.add_argument(
        "--debug-count",
        action="store_true",
        help="In ra tổng số dòng và một vài record mẫu để kiểm tra.",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    # Load settings từ ENV (Module 1)
    s = OnusSettings()

    # Xây params gốc (1 datePeriod lớn)
    params = build_params(args.start_date, args.end_date)

    # Gọi facade segmented:
    # - Nếu ONUSLIBS_DATE_SEGMENT_HOURS <= 0 -> fetch_json_segmented sẽ
    #   tự fallback về fetch_json (không segment).
    # - Nếu > 0 -> datePeriod sẽ được tự chia nhỏ thành nhiều đoạn.
    rows: List[Dict[str, Any]] = fetch_json_segmented(
        endpoint=ENDPOINT,
        params=params,
        fields=BASIC_FIELDS,
        order_by=DEFAULT_ORDER,
        settings=s,
        page_size=args.page_size,       # None => dùng ONUSLIBS_PAGE_SIZE
        paginate=not args.no_paginate,  # mặc định True
        unique_key="transactionNumber", # dedupe cross-segment nếu trùng
        date_param="datePeriod",        # tên param datePeriod trong API
        pager_func=None,                # dùng HeaderPager mặc định
    )

    total = len(rows)
    print(f"Total fetched rows: {total}")
    
    # 4) Xuất & thống kê
    from tools.print_json import print_json
    print_json(len(rows))

    # if args.debug_count and total > 0:
        # print("Sample row[0]:")
        # print(rows[0])

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
