# -*- coding: utf-8 -*-
"""
Chạy:
  set ONUSLIBS_BASE_URL=https://wallet.vndc.io
  set ACCESS_CLIENT_TOKEN=***TOKEN***   # hoặc ONUSLIBS_ACCESS_CLIENT_TOKEN / ONUS_ACCESS_CLIENT_TOKEN
  python app_commission.py
"""
import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import csv
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# (tuỳ chọn) đọc .env khi dev:
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app_config import get_config, AppConfig
from onuslibs.settings import OnusSettings          # validate ENV
from onuslibs import fetch_all                      # hàm core đã tích hợp thuật toán v2
from onuslibs.utils import parse_filters            # parse filters k=v&k2=v2


def daterange_utc(start_dt, end_dt):
    cur = start_dt
    while cur.date() <= end_dt.date():
        day_start = datetime.datetime(cur.year, cur.month, cur.day, 0, 0, 0, tzinfo=cur.tzinfo)
        day_end   = day_start + timedelta(days=1) - timedelta(seconds=1)
        yield max(day_start, start_dt), min(day_end, end_dt)
        cur += timedelta(days=1)

def demo_multiday_visual(cfg: AppConfig):
    logging.info("[DEMO] Visualizing day-level concurrency with max_workers=%s", cfg.limits.day_workers)
    tasks = []
    with ThreadPoolExecutor(max_workers=cfg.limits.day_workers) as ex:
        for d_start, d_end in daterange_utc(cfg.start, cfg.end):
            day_label = d_start.date().isoformat()
            logging.info("[start] day=%s", day_label)
            # Mỗi task gọi fetch_all giới hạn đúng 1 ngày
            fut = ex.submit(lambda s=d_start, e=d_end: fetch_all(
                endpoint=cfg.endpoint,
                start=s, end=e,
                filters=parse_filters(cfg.filters_qs),
                fields=cfg.fields,
                split_by_day=True,
                page_size=cfg.limits.page_size,
                day_workers=1,           # mỗi task xử lý 1 ngày nên để 1
                req_per_sec=cfg.limits.req_per_sec,
                http2=cfg.limits.http2,
                timeout_s=cfg.limits.timeout_s,
                debug=False
            ))
            tasks.append((day_label, fut))
        # thu kết quả + in done
        total = 0
        for day_label, fut in tasks:
            rows = fut.result()
            logging.info("[done ] day=%s  rows=%s", day_label, len(rows))
            total += len(rows)
    return total

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

def fetch_commission(cfg: AppConfig) -> List[Dict[str, Any]]:
    """Hàm lấy dữ liệu (gọi OnusLibs) — tách rời khỏi main."""
    # Validate ENV (ném lỗi nếu thiếu)
    _ = OnusSettings()

    # Hiển thị cấu hình cấp ngày trước khi gọi để xác nhận chạy đa luồng
    logging.info("DAY WORKERS = %s | RANGE = %s .. %s",
                 cfg.limits.day_workers, cfg.start, cfg.end)

    rows = fetch_all(
        endpoint=cfg.endpoint,
        start=cfg.start,
        end=cfg.end,
        filters=parse_filters(cfg.filters_qs),
        fields=cfg.fields,
        split_by_day=True,
        # limits
        page_size=cfg.limits.page_size,
        day_workers=cfg.limits.day_workers,
        req_per_sec=cfg.limits.req_per_sec,
        http2=cfg.limits.http2,
        timeout_s=cfg.limits.timeout_s,
        # thuật toán v2
        debug=True,
        force_segmented_paging=cfg.algo.force_segmented_paging,
        segment_safety_ratio=cfg.algo.segment_safety_ratio,
        segment_min_seconds=cfg.algo.segment_min_seconds,
    )
    return rows

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    cfg = get_config()               # tách cấu hình ra riêng
    rows = fetch_commission(cfg)     # tách hàm lấy data ra riêng
    print(f"[OK] rows: {len(rows)}")
    write_csv_result(rows, cfg.output.csv_path, overwrite=cfg.output.overwrite)

if __name__ == "__main__":
    main()
