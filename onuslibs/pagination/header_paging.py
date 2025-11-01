# -*- coding: utf-8 -*-
from typing import Dict, List, Tuple
import httpx
from httpx import HTTPStatusError
from .limiter import RateLimiter
from ..utils import extract_items, iso_ms
from ..pagination.time_windows import MS

def _get_int(h: Dict[str, str], name: str, default: int = 0) -> int:
    try:
        return int(h.get(name, str(default)) or default)
    except Exception:
        return default

def params_dateperiod(s_iso: str, e_iso: str, page: int, page_size: int) -> Dict[str, str]:
    return {"datePeriod": f"{s_iso},{e_iso}", "page": str(page), "pageSize": str(page_size)}

async def get_page(client: httpx.AsyncClient, url: str, headers: Dict[str, str],
                   params: Dict[str, str], timeout_s: float,
                   limiter: RateLimiter):
    await limiter.acquire()
    r = await client.get(url, headers=headers, params=params, timeout=timeout_s)
    r.raise_for_status()
    return r

async def fetch_window_header_paging(
    client: httpx.AsyncClient, url: str, headers: Dict[str, str], filters: Dict[str, str],
    w_start, w_end, page_size: int, fields: List[str],
    timeout_s: float, limiter: RateLimiter, debug: bool,
    allow_multi_page: bool = True
) -> Tuple[List[dict], bool, int, bool, int]:
    """
    Trả: (items, complete, total_count, paging_ok, last_len)
    - allow_multi_page=False: chỉ gọi page=0 (cho segment).
    """
    items_all: List[dict] = []
    paging_ok = True

    params = dict(filters)
    params.update(params_dateperiod(iso_ms(w_start), iso_ms(w_end), page=0, page_size=page_size))
    if fields:
        params["fields"] = ",".join(fields)

    r0 = await get_page(client, url, headers, params, timeout_s, limiter)
    it0 = extract_items(r0.json()); items_all.extend(it0)
    h0 = {k.lower(): v for k, v in r0.headers.items()}
    cur        = _get_int(h0, "x-current-page", 0)
    pcount     = _get_int(h0, "x-page-count",  0)
    total_cnt  = _get_int(h0, "x-total-count", 0)
    has_next   = h0.get("x-has-next-page", "false").lower() == "true"
    last_len   = len(it0)

    if debug:
        print(f"[HDR] {w_start}..{w_end} p0={last_len} cur={cur} pcount={pcount} next={has_next} total={total_cnt}")

    if not allow_multi_page:
        if total_cnt > 0:
            return items_all, (len(items_all) >= total_cnt), total_cnt, True, last_len
        return items_all, (last_len < page_size), total_cnt, True, last_len

    # multi-page (hiếm dùng ở v2)
    p = cur + 1
    while has_next and (pcount == 0 or p < pcount):
        params["page"] = str(p)
        try:
            r = await get_page(client, url, headers, params, timeout_s, limiter)
        except HTTPStatusError as e:
            sc = e.response.status_code if e.response else None
            if sc in (422, 404):
                paging_ok = False
                break
            raise
        it = extract_items(r.json()); items_all.extend(it)
        hh = {k.lower(): v for k, v in r.headers.items()}
        cur      = _get_int(hh, "x-current-page", cur)
        pcount   = _get_int(hh, "x-page-count",  pcount)
        has_next = hh.get("x-has-next-page", "false").lower() == "true"
        last_len = len(it)

        if total_cnt > 0 and len(items_all) >= total_cnt:
            return items_all, True, total_cnt, True, last_len
        p = cur + 1

    if total_cnt > 0:
        return items_all, (len(items_all) >= total_cnt), total_cnt, paging_ok, last_len
    return items_all, (last_len < page_size or not has_next), total_cnt, paging_ok, last_len
