# -*- coding: utf-8 -*-
"""
db_smoke_test.py
================

Script kiểm tra nhanh module DB của OnusLibs:

1) Lấy thông tin DB từ secure store (Keyring/ENV) qua DbSettings.from_secure().
2) Healthcheck kết nối bằng DB.healthcheck().
3) Đọc thử vài dòng từ bảng onchain_diary bằng DB.query().
4) Ghi thử 1 dòng vào bảng tmp_onuslibs_smoke bằng DB.execute().

Yêu cầu chuẩn bị:

- Đã lưu thông tin DB vào Keyring hoặc ENV theo chuẩn DbSettings.from_secure.

  Ví dụ Keyring:

    $svc="OnusLibs"
    python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_HOST','127.0.0.1')"
    python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PORT','3306')"
    python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_USER','onusreport')"
    python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_PASSWORD','xxx')"
    python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_NAME','onusreport')"
    python -c "import keyring; s='$svc'; keyring.set_password(s,'DB_SSL_CA','')"  # nếu không dùng SSL

- Bảng onchain_diary đã tồn tại và có dữ liệu.

- Bảng tmp_onuslibs_smoke đã tồn tại với schema:

    CREATE TABLE `tmp_onuslibs_smoke` (
      `id` int NOT NULL,
      `name` varchar(50) DEFAULT NULL,
      `score` int DEFAULT NULL,
      `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`)
    );

- Đã cài pymysql:
    pip install pymysql
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any, Dict, List

from onuslibs.db.settings import DbSettings
from onuslibs.db.core import DB


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OnusLibs DB smoke test: DbSettings.from_secure -> DB -> SELECT/INSERT."
    )

    parser.add_argument(
        "--fallback-env",
        action="store_true",
        help="Ưu tiên đọc cấu hình DB từ ENV trước (tương đương ONUSLIBS_FALLBACK_ENV=true).",
    )

    parser.add_argument(
        "--onchain-limit",
        type=int,
        default=5,
        help="Số dòng đọc thử từ bảng onchain_diary (mặc định 5).",
    )

    # Tham số cho bảng tmp_onuslibs_smoke
    parser.add_argument(
        "--id",
        type=int,
        default=None,
        help="Giá trị id để insert vào tmp_onuslibs_smoke (mặc định = timestamp giây hiện tại).",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Giá trị name để insert vào tmp_onuslibs_smoke (mặc định auto).",
    )
    parser.add_argument(
        "--score",
        type=int,
        default=100,
        help="Giá trị score để insert vào tmp_onuslibs_smoke (mặc định 100).",
    )

    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    # 1) Lấy DbSettings từ secure store (Keyring/ENV)
    print(">>> Đang đọc DbSettings từ secure store (Keyring/ENV)...")
    db_settings = DbSettings.from_secure(
        service=None,                       # để DbSettings tự lấy từ OnusSettings hoặc ENV
        fallback_env=args.fallback_env or None,
    )

    # In thông tin an toàn (không log password)
    safe = {
        "host": getattr(db_settings, "host", None),
        "port": getattr(db_settings, "port", None),
        "user": getattr(db_settings, "user", None),
        "name": getattr(db_settings, "name", None),
        "ssl_ca": bool(getattr(db_settings, "ssl_ca", None)),
        "connect_timeout": getattr(db_settings, "connect_timeout", None),
    }
    print("    DbSettings:", safe)
    print()

    # 2) Tạo DB wrapper và healthcheck
    db = DB(settings=db_settings)

    print(">>> Đang healthcheck DB (SELECT 1)...")
    ok = db.healthcheck()
    if not ok:
        print("[ERROR] Healthcheck DB thất bại (SELECT 1 không thành công).", flush=True)
        return 1

    print(">>> OK: healthcheck DB thành công.")
    print()

    # 3) Test đọc bảng onchain_diary
    limit = max(1, int(args.onchain_limit))
    print(f">>> Đọc thử {limit} dòng từ bảng onchain_diary ...")
    sql_select = "SELECT * FROM onchain_diary LIMIT %s"
    rows: List[Dict[str, Any]] = db.query(sql_select, (limit,))
    print(f"    Số dòng đọc được: {len(rows)}")
    for i, row in enumerate(rows, start=1):
        print(f"  Row {i}: {row}")
    print()

    # 4) Test ghi vào bảng tmp_onuslibs_smoke
    #    Schema: id (PK, int, NOT NULL), name (varchar), score (int), updated_at auto.
    now = datetime.now()
    smoke_id = args.id if args.id is not None else int(now.timestamp())
    smoke_name = args.name or f"OnusLibs smoke {now.strftime('%Y-%m-%d %H:%M:%S')}"
    smoke_score = args.score

    print(">>> Ghi thử vào bảng tmp_onuslibs_smoke ...")
    print("    id   =", smoke_id)
    print("    name =", smoke_name)
    print("    score=", smoke_score)

    sql_insert = "INSERT INTO tmp_onuslibs_smoke(id, name, score) VALUES (%s, %s, %s)"
    affected = db.execute(sql_insert, (smoke_id, smoke_name, smoke_score))
    print(f">>> OK: đã thực hiện INSERT, rows affected = {affected}.")
    print(">>> Hãy kiểm tra trong DB để xác nhận bản ghi được tạo.")
    print(">>> Gợi ý: SELECT * FROM tmp_onuslibs_smoke ORDER BY updated_at DESC LIMIT 10;")

    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
