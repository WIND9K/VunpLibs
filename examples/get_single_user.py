# examples/get_single_user.py
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from onuslibs.unified.api import fetch_json

# Endpoint dành cho user
ENDPOINT = "/api/users"

# Các field muốn lấy cho 1 user
FIELDS: List[str] = [
    "id",
    "name",
    "email",
    "customValues.date_of_birth",
    "customValues.gender",
    "customValues.vip_level",
    "customValues.listed",
    "customValues.document_type",
    "group.name",
    "address.city",
]


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch thông tin 1 user từ /api/users qua OnusLibs."
    )
    parser.add_argument(
        "--userid",
        required=True,
        help="User ID cần fetch. Ví dụ: 6277729722014433182",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="In toàn bộ kết quả ra stdout dạng JSON (1 dòng).",
    )
    return parser.parse_args(argv)


def build_params(userid: str) -> Dict[str, Any]:
    """Build params để lấy 1 user.

    Tuỳ API thực tế, bạn chỉnh lại key filter cho đúng:
    - Có thể là 'id'
    - Hoặc 'ids'
    - Hoặc 'user', ...
    Ở đây tạm thời dùng 'id' cho đơn giản.
    """
    return {
        "id": userid,
    }


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    params = build_params(args.userid)

    # Với GET 1 user, không cần phân trang, tránh lỗi 422 ở page cao.
    rows: List[Dict[str, Any]] = fetch_json(
        endpoint=ENDPOINT,
        params=params,
        fields=FIELDS,
        order_by=None,
        unique_key="id",
        paginate=False,   # CHỐT: không dùng pagination, gọi 1 request duy nhất
        # strict_fields=True,   # DEV/TEST nếu muốn canh schema field
        # on_batch=...         # nếu muốn stream về DB
        # parallel: để mặc định cho OnusSettings/ENV quyết định
    )

    if not rows:
        print(f"Không tìm thấy user với id={args.userid}")
        return 0

    user = rows[0]

    if args.json:
        # In full JSON 1 dòng để dễ pipe sang jq, file, ...
        print(json.dumps(user, ensure_ascii=False))
    else:
        # In tóm tắt một số field quan trọng
        print("=== USER INFO ===")
        print(f"id    : {user.get('id')}")
        print(f"name  : {user.get('name')}")
        print(f"email : {user.get('email')}")

        cv = user.get("customValues") or {}
        print(f"dob   : {cv.get('date_of_birth')}")
        print(f"gender: {cv.get('gender')}")
        print(f"vip   : {cv.get('vip_level')}")
        print(f"listed: {cv.get('listed')}")
        print(f"doc   : {cv.get('document_type')}")

        group = user.get("group") or {}
        print(f"group : {group.get('name')}")

        addr = user.get("address") or {}
        print(f"city  : {addr.get('city')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
