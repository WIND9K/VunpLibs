"""
tests/app_user.py

Ứng dụng chạy thật trên môi trường của bạn để kiểm tra OnusLibs.
Cách dùng (PowerShell/VsCode):
--------------------------------
# Cài package ở chế độ editable để import đúng source
pip install -e .

# Chạy với danh sách userid (phân tách bằng dấu phẩy, hoặc truyền nhiều lần)
python -m tests.app_user --user-ids 6277729706994698142

# Hoặc:
python -m tests.app_user 6277729706994698142 6277729712345678901

# Tuỳ chọn:
  --paginate              # bật phân trang theo HeaderPager (không gửi page/pageSize)
  --page-size 2000        # tuỳ chỉnh pageSize (khi không phân trang)
  --fields "id,name,email,customValues,group.name"
  --verbose
  --dry-run               # chỉ in URL + headers preview, không gọi API

Yêu cầu:
- Keyring đã có ACCESS_CLIENT_TOKEN trong service ONUSLIBS_KEYRING_SERVICE (mặc định: OnusLibs).
- ENV đã set ONUSLIBS_BASE_URL=https://wallet.vndc.io (hoặc base URL hợp lệ khác).
"""

from __future__ import annotations
import argparse
import sys
import json
from typing import List

from onuslibs.config.settings import OnusSettings
from onuslibs.security.headers import build_headers, preview_headers
from onuslibs.unified.api import fetch_json

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)  # nạp .env ở project root nếu có

from .config_api import (
    ENDPOINT,
    FIELDS_DEFAULT,
    STATUSES,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    build_params,
    build_url,
)

def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run live user fetch via OnusLibs.")
    p.add_argument("user_ids", nargs="*", help="Danh sách userid (có thể truyền nhiều).")  # positional
    p.add_argument("--user-ids", dest="user_ids_csv", default=None, help="Danh sách userid, phân tách bằng dấu phẩy.")
    p.add_argument("--fields", default=FIELDS_DEFAULT, help="Danh sách fields (CSV). Mặc định dùng cấu hình chuẩn.")
    p.add_argument("--paginate", action="store_true", help="Bật phân trang qua HeaderPager.")
    p.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="pageSize khi gọi one-shot (paginate=False)." )
    p.add_argument("--verbose", action="store_true", help="In thêm thông tin debug.")
    p.add_argument("--dry-run", action="store_true", help="Chỉ in URL + headers preview, không gọi API.")
    return p.parse_args(argv)

def main(argv: List[str]) -> int:
    args = parse_args(argv)

    # Gom danh sách userid từ positional + --user-ids
    ids: List[str] = []
    if args.user_ids:
        ids.extend([str(x) for x in args.user_ids])
    if args.user_ids_csv:
        ids.extend([s.strip() for s in args.user_ids_csv.split(",") if s.strip()])
    ids = [x for x in ids if x]
    if not ids:
        print("[ERR] Thiếu userid. Ví dụ: python -m tests.app_user --user-ids 6277729706994698142", file=sys.stderr)
        return 2

    # Setup settings + headers
    s = OnusSettings()
    headers = build_headers(s)   # xác nhận token + header hợp lệ
    if args.verbose or args.dry_run:
        print("[INFO] base_url:", s.base_url)
        print("[INFO] headers:", preview_headers(headers, s))

    url = build_url(s.base_url)
    if args.dry_run:
        sample_params = build_params(ids[0], fields=args.fields, page=None if args.paginate else DEFAULT_PAGE, page_size=None if args.paginate else args.page_size, statuses=STATUSES)
        print("[DRY-RUN] URL:", url)
        print("[DRY-RUN] params:", sample_params)
        return 0

    any_fail = False
    total_all = 0

    for uid in ids:
        # Với paginate=True: không gửi page/pageSize → OnusLibs sẽ tự phân trang theo HeaderPager
        params = build_params(uid, fields=args.fields,
                              page=None if args.paginate else DEFAULT_PAGE,
                              page_size=None if args.paginate else args.page_size,
                              statuses=STATUSES)

        try:
            rows = fetch_json(
                endpoint=ENDPOINT,
                params=params,
                paginate=bool(args.paginate),
                page_size=args.page_size,
                strict_fields=True,         # fail-fast nếu field sai → tốt cho dev
                settings=s,
            )
            total = len(rows)
            total_all += total
            print(f"[OK] userid={uid} → {total} record(s)")
            if rows:
                print(json.dumps(rows[0], ensure_ascii=False, indent=2))
        except Exception as e:
            any_fail = True
            print(f"[ERR] userid={uid}: {e}", file=sys.stderr)

    if args.verbose:
        print(f"[SUMMARY] tổng số bản ghi: {total_all}")

    return 1 if any_fail else 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
