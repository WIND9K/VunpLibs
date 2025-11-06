# -*- coding: utf-8 -*-
"""
Chạy:
  set ONUSLIBS_BASE_URL=https://wallet.vndc.io
  set ONUSLIBS_ACCESS_CLIENT_TOKEN=***TOKEN***
  python app_users.py
"""
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import csv
from pathlib import Path
from typing import List, Dict, Any

from onuslibs.pagination.segmented import fetch_all

# (tuỳ chọn) đọc .env khi dev
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app_users_config import get_users_config, UsersAppConfig
from onuslibs.settings import OnusSettings        # validate ENV (ném lỗi nếu thiếu)
from onuslibs.simple import users_by_ids          # no-datePeriod helper

def write_csv_result(rows: List[Dict[str, Any]], csv_path: str, *, overwrite: bool = True) -> str:
    """Ghi CSV để đối soát nhanh kết quả."""
    if not csv_path:
        return ""
    p = Path(csv_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite or not p.exists() else "a"
    headers = list({k for r in rows for k in r.keys()}) if rows else []
    with p.open(mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers) if headers else None
        if mode == "w" and headers:
            w.writeheader()
        if rows and w:
            w.writerows(rows)
    print(f"[CSV] wrote: {p} ({len(rows)} rows, mode={'overwrite' if mode=='w' else 'append'})")
    return str(p)

def fetch_users(cfg: UsersAppConfig) -> List[Dict[str, Any]]:
    """Hàm lấy dữ liệu người dùng theo danh sách IDs (không datePeriod)."""
    # Validate ENV (sẽ raise RuntimeError nếu thiếu)
    _ = OnusSettings()

    rows = users_by_ids(
        ids=[str(x).strip() for x in cfg.ids if str(x).strip()],
        endpoint=cfg.endpoint,
        id_param=cfg.id_param,
        fields=cfg.fields,
        page_size=cfg.limits.page_size,
        timeout_s=cfg.limits.timeout_s,
        http2=cfg.limits.http2,
    )
    return rows

def main():
    cfg = get_users_config()     # tách cấu hình ra riêng
    rows = fetch_users(cfg)      # tách hàm gọi onuslibs ra riêng
    print(f"[OK] rows: {len(rows)}")
    write_csv_result(rows, cfg.output.csv_path, overwrite=cfg.output.overwrite)

if __name__ == "__main__":
    main()
