# -*- coding: utf-8 -*-
from __future__ import annotations
# === DEBUG FLOW helpers ===
import time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
from typing import Iterable, Tuple

def _sleep_ms(ms: int):
    if ms and ms > 0:
        time.sleep(ms / 1000.0)

def _headers_lower(resp) -> dict:
    return {k.lower(): v for k, v in resp.headers.items()}

def _extract_items_loc(payload: Any) -> List[Dict[str, Any]]:
    # list -> pageItems -> items -> []
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("pageItems"), list):
            return list(payload["pageItems"])
        if isinstance(payload.get("items"), list):
            return list(payload["items"])
    return []

from httpx import HTTPStatusError
def header_fetch_all_seq_debug(
    http_client: Any,
    endpoint: str,
    *,
    params: Dict[str, Any],
    headers: Dict[str, str],
    page_size: int,
    delay_ms: int = 0,
    max_pages: Optional[int] = None,
) -> Iterable[List[Dict[str, Any]]]:
    page = int(params.get("page", 0) or 0)
    taken = 0
    while True:
        p = dict(params); p["page"] = page; p["pageSize"] = page_size
        print(f"[SEQ] → Request page={page} pageSize={page_size}")
        _sleep_ms(delay_ms)
        try:
            resp = http_client.get(endpoint, params=p, headers=headers)
            print(f"[SEQ] ← Status={resp.status_code} page={page}")
            resp.raise_for_status()
            items = _extract_items_loc(resp.json())
            h = _headers_lower(resp)
            if page == 0:
                print("[SEQ] X-Total-Count:", h.get("x-total-count"), "| X-Page-Count:", h.get("x-page-count"))

            has_next = (h.get("x-has-next-page") or "").lower() == "true"
            print(f"[SEQ] • Yield page={page} items={len(items)} has_next={has_next}")
        except HTTPStatusError as e:
            code = e.response.status_code
            if code in (400, 404, 422):
                print(f"[SEQ] stop: page={page} out-of-range (HTTP {code})")
                return
            raise  # lỗi khác thì nổi lên

        items = _extract_items_loc(resp.json())
        h = _headers_lower(resp)
        has_next = (h.get("x-has-next-page") or "").lower() == "true"
        print(f"[SEQ] • Yield page={page} items={len(items)} has_next={has_next}")
        yield items

        if not has_next or not items:
            print("[SEQ] done (no next/empty batch)")
            return
        page += 1
        
def header_fetch_all_parallel_debug(
    http_client: Any,
    endpoint: str,
    *,
    params: Dict[str, Any],
    headers: Dict[str, str],
    page_size: int,
    delay_ms: int = 0,
    max_pages: Optional[int] = None,
    workers: Optional[int] = None,
) -> Iterable[List[Dict[str, Any]]]:
    # Lấy page 0 trước để đọc header
    p0 = int(params.get("page", 0) or 0)
    p = dict(params); p["page"] = p0; p["pageSize"] = page_size
    print(f"[PAR] → Request page={p0} (bootstrap) pageSize={page_size}")
    _sleep_ms(delay_ms)
    resp0 = http_client.get(endpoint, params=p, headers=headers)
    print(f"[PAR] ← Status={resp0.status_code} page={p0}")
    resp0.raise_for_status()
    items0 = _extract_items_loc(resp0.json())
    hdr0 = _headers_lower(resp0)
    if not items0:
        print("[PAR] page0 empty → stop")
        return
    print(f"[PAR] • Yield page={p0} items={len(items0)} (bootstrap)")
    yield items0

    # Tính tổng trang
    last_page_idx = None
    pc = (hdr0.get("x-page-count") or "").strip()
    if pc.isdigit():
        last_page_idx = max(0, int(pc) - 1)
    else:
        tc = (hdr0.get("x-total-count") or "").strip()
        if tc.isdigit() and page_size > 0:
            total = int(tc)
            last_page_idx = max(0, ceil(total / page_size) - 1) if total > 0 else 0

    # Nếu không tính được tổng trang → fallback tuần tự cho phần còn lại
    if last_page_idx is None:
        print("[PAR] cannot infer total pages → fallback SEQ for remainder")
        for batch in header_fetch_all_seq_debug(
            http_client, endpoint,
            params={**params, "page": p0 + 1},
            headers=headers,
            page_size=page_size,
            delay_ms=delay_ms,
            max_pages=max_pages,
        ):
            yield batch
        return

    start = p0 + 1
    end   = last_page_idx
    if max_pages is not None:
        end = min(end, start + max_pages - 1)
    if end < start:
        print("[PAR] no remaining pages")
        return

    # workers
    if workers is None:
        try:
            from onuslibs.config.settings import OnusSettings
            workers = max(1, int(OnusSettings().max_inflight))
        except Exception:
            workers = 4
    workers = max(1, min(int(workers), 16))  # clamp an toàn

    print(f"[PAR] plan: workers={workers} fetch pages {start}..{end}")

    
    def _fetch(i: int) -> Tuple[int, List[Dict[str, Any]]]:
        tp = threading.get_ident()
        pp = dict(params); pp["page"] = i; pp["pageSize"] = page_size
        print(f"[PAR][T{tp}] → Request page={i}")
        _sleep_ms(delay_ms)
        try:
            r = http_client.get(endpoint, params=pp, headers=headers)
            print(f"[PAR][T{tp}] ← Status={r.status_code} page={i}")
            r.raise_for_status()
        except HTTPStatusError as e:
            code = e.response.status_code
            if code in (400, 404, 422):   # coi như page vượt phạm vi
                print(f"[PAR][T{tp}] stop page={i} out-of-range (HTTP {code})")
                return i, []
            raise
        items = _extract_items_loc(r.json())
        print(f"[PAR][T{tp}] • Done page={i} items={len(items)}")
        return i, items

    buffer: Dict[int, List[Dict[str, Any]]] = {}
    next_to_yield = start
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch, i): i for i in range(start, end + 1)}
        for fut in as_completed(futs):
            i, items = fut.result()
            buffer[i] = items
            while next_to_yield in buffer:
                b = buffer.pop(next_to_yield)
                if b:
                    print(f"[PAR] • Yield page={next_to_yield} items={len(b)}")
                    yield b
                else:
                    print(f"[PAR] • Skip empty page={next_to_yield}")
                next_to_yield += 1

    print("[PAR] done")

"""
Fetch commission history (VNDC) qua OnusLibs Facade – cấu hình tách ở đầu trang.

Chạy mẫu:
  python -m examples.fetch_commission_history --date 2025-10-11
  python -m examples.fetch_commission_history --start-date 2025-10-01 --end-date 2025-10-11 --preset full
  python -m examples.fetch_commission_history --date 2025-10-11 --fields date,amount,description
"""

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
        items = _extract_items_loc(resp.json())
        h = _headers_lower(resp)
        if page == 0:
            print("[SEQ] X-Total-Count:", h.get("x-total-count"), "| X-Page-Count:", h.get("x-page-count"))

        has_next = (h.get("x-has-next-page") or "").lower() == "true"
        print(f"[SEQ] • Yield page={page} items={len(items)} has_next={has_next}")

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
        # Flow quan sát
    p.add_argument("--parallel", action="store_true", help="Bật phân trang đa luồng (song song).")
    p.add_argument("--workers", type=int, default=None, help="Số luồng khi chạy --parallel (mặc định lấy từ ENV).")
    p.add_argument("--debug-flow", action="store_true", help="In log trực quan từng request/trang.")
    p.add_argument("--delay-ms", type=int, default=0, help="Ngủ (ms) trước MỖI request để dễ quan sát.")
    p.add_argument("--max-pages", type=int, default=None, help="Giới hạn số trang tải (chỉ cho demo quan sát).")

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
        # 3) Fetch
    s = OnusSettings()  # tự nạp ENV/.env

    pager_override = None
    if args.debug_flow:
        if args.parallel:
            def pager_override(cli, ep, params=None, headers=None, page_size=None):
                return header_fetch_all_parallel_debug(
                    cli, ep,
                    params=params or {},
                    headers=headers or {},
                    page_size=page_size or args.page_size,
                    delay_ms=args.delay_ms,
                    max_pages=args.max_pages,
                    workers=args.workers,
                )
        else:
            def pager_override(cli, ep, params=None, headers=None, page_size=None):
                return header_fetch_all_seq_debug(
                    cli, ep,
                    params=params or {},
                    headers=headers or {},
                    page_size=page_size or args.page_size,
                    delay_ms=args.delay_ms,
                    max_pages=args.max_pages,
                )

    print(f"RUN MODE: {'PARALLEL' if args.parallel else 'SEQUENTIAL'} | DEBUG={args.debug_flow} | DELAY={args.delay_ms}ms")
    total = {"n": 0}
    def _count_batch(items: List[Dict[str, Any]]) -> None:
        total["n"] += len(items)
        # In tiến độ khi debug-flow để dễ quan sát
        if args.debug_flow:
            print(f"[SUM] +{len(items)} → running_total={total['n']}")

    rows: List[Dict[str, Any]] = fetch_json(
        endpoint=ENDPOINT,
        params=params,
        fields=fields,              # list[str]
        paginate=True,              # lịch sử → nên phân trang
        page_size=args.page_size,   # ghi đè ENV khi cần
        order_by=None,              # đã set orderBy trong params
        settings=s,
        unique_key=None,
        parallel=(args.parallel and not pager_override),  # nếu tự override pager thì parallel=False ở facade
        pager_func=pager_override,
        on_batch=_count_batch,     
    )
    print(f"[SUMMARY] total_items={len(rows)}")

    # 4) Xuất & thống kê
    # if args.out_json:
    #     # print_json(rows, to_file=args.out_json)
    #     print(f"Đã ghi JSON: {len(rows)} dòng -> {args.out_json}")
    # else:
    #     print_json(rows)
    #     print(f"\nTotal fetched rows: {len(rows)}")

    # api_total = try_get_api_total_count(s, ENDPOINT, params)
    # if api_total is not None:
    #     print(f"API reported X-Total-Count: {api_total}")

    

    # from tools.write_csv import write_csv

    # out = "commission_history.csv"
    # n = write_csv(rows, out)  # auto dò cột, tự flatten nested dict
    # print(f"Đã ghi {n} dòng vào {out}")

    return 0
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
