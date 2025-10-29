# -*- coding: utf-8 -*-
from typing import Dict, List, Tuple, Iterable
import asyncio
from math import ceil
from datetime import datetime
import httpx

from .limiter import RateLimiter
from .header_paging import fetch_window_header_paging
from .time_windows import day_slices, MS
from ..utils import parse_filters, url_join_safe
from ..http_client import build_headers, make_async_client
from ..settings import OnusSettings

async def fetch_window_with_bisect(
    client: httpx.AsyncClient, url: str, headers: Dict[str,str], filters: Dict[str,str],
    w_start: datetime, w_end: datetime, page_size: int, fields: List[str],
    timeout_s: float, limiter: RateLimiter, debug: bool,
    segment_min_seconds: float, segment_safety_ratio: float
) -> List[dict]:
    if (w_end - w_start).total_seconds() <= segment_min_seconds:
        items, _, _, _, _ = await fetch_window_header_paging(
            client, url, headers, filters, w_start, w_end, page_size, fields,
            timeout_s, limiter, debug, allow_multi_page=False
        )
        return items

    items, complete, _, _, last_len = await fetch_window_header_paging(
        client, url, headers, filters, w_start, w_end, page_size, fields,
        timeout_s, limiter, debug, allow_multi_page=False
    )
    if not complete and last_len >= int(page_size * segment_safety_ratio):
        mid = w_start + (w_end - w_start) / 2
        left_end = max(w_start, min(w_end, mid - MS))
        left_items = await fetch_window_with_bisect(
            client, url, headers, filters, w_start, left_end, page_size, fields,
            timeout_s, limiter, debug, segment_min_seconds, segment_safety_ratio
        )
        right_items = await fetch_window_with_bisect(
            client, url, headers, filters, mid, w_end, page_size, fields,
            timeout_s, limiter, debug, segment_min_seconds, segment_safety_ratio
        )
        return left_items + right_items
    return items

async def plan_by_total_and_fetch(
    client: httpx.AsyncClient, url: str, headers: Dict[str,str], filters: Dict[str,str],
    w_start: datetime, w_end: datetime, page_size: int, fields: List[str],
    timeout_s: float, limiter: RateLimiter, debug: bool,
    total_count_hint: int, segment_min_seconds: float, segment_safety_ratio: float
) -> List[dict]:
    K = max(2, ceil(total_count_hint / page_size))
    items_all: List[dict] = []
    for i in range(K):
        seg_start = w_start + (w_end - w_start) * (i / K)
        seg_end   = w_start + (w_end - w_start) * ((i + 1) / K)
        if i < K - 1:
            seg_end = min(w_end, seg_end - MS)

        win_items, complete, _, _, last_len = await fetch_window_header_paging(
            client, url, headers, filters, seg_start, seg_end, page_size, fields,
            timeout_s, limiter, debug, allow_multi_page=False
        )
        if complete or last_len < int(page_size * segment_safety_ratio):
            items_all.extend(win_items)
            continue

        extra = await fetch_window_with_bisect(
            client, url, headers, filters, seg_start, seg_end, page_size, fields,
            timeout_s, limiter, debug, segment_min_seconds, segment_safety_ratio
        )
        items_all.extend(extra)
    return items_all

async def fetch_one_day(
    client: httpx.AsyncClient, url: str, headers: Dict[str,str], filters: Dict[str,str],
    day_start: datetime, day_end: datetime, page_size: int, fields: List[str],
    timeout_s: float, limiter: RateLimiter, debug: bool,
    force_segmented_paging: bool, segment_min_seconds: float, segment_safety_ratio: float
) -> List[dict]:
    items0, complete0, total_cnt0, paging_ok0, last_len0 = await fetch_window_header_paging(
        client, url, headers, filters, day_start, day_end, page_size, fields,
        timeout_s, limiter, debug, allow_multi_page=not force_segmented_paging
    )
    if total_cnt0 > 0 and total_cnt0 <= page_size and last_len0 < page_size:
        return items0

    if force_segmented_paging or not paging_ok0 or not complete0:
        if total_cnt0 > 0:
            return await plan_by_total_and_fetch(
                client, url, headers, filters, day_start, day_end, page_size, fields,
                timeout_s, limiter, debug, total_cnt0, segment_min_seconds, segment_safety_ratio
            )
        return await fetch_window_with_bisect(
            client, url, headers, filters, day_start, day_end, page_size, fields,
            timeout_s, limiter, debug, segment_min_seconds, segment_safety_ratio
        )
    return items0

def _chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

async def async_fetch_dateperiod(
    endpoint: str, start: datetime, end: datetime, *, filters: str|Dict[str,str] = "",
    fields: List[str] | str = None, split_by_day: bool = True,
    page_size: int | None = None, day_workers: int = 1,
    req_per_sec: float | None = None, http2: bool | None = None,
    timeout_s: float | None = None, debug: bool = False,
    force_segmented_paging: bool = True,
    segment_safety_ratio: float = 0.95, segment_min_seconds: float = 1.0
) -> List[dict]:
    s = OnusSettings()
    base_url = s.base_url
    if page_size is None: page_size = s.page_size
    if req_per_sec is None: req_per_sec = s.req_per_sec
    if http2 is None: http2 = s.http2
    if timeout_s is None: timeout_s = s.request_timeout_s

    url = url_join_safe(base_url, endpoint)
    headers = build_headers(s)
    fdict = parse_filters(filters) if isinstance(filters, str) else (filters or {})
    if isinstance(fields, str):  # CSV string
        fields = [x.strip() for x in fields.split(",") if x.strip()]

    slices = day_slices(start, end) if split_by_day else [(start, end)]
    limiter = RateLimiter(req_per_sec)
    out: List[dict] = []

    async with make_async_client(http2=http2, timeout_s=timeout_s) as client:
        for batch in _chunked(slices, max(1, day_workers)):
            tasks = [
                fetch_one_day(
                    client, url, headers, fdict, d0, d1, page_size, fields or [],
                    timeout_s, limiter, debug,
                    force_segmented_paging, segment_min_seconds, segment_safety_ratio
                )
                for (d0, d1) in batch
            ]
            results = await asyncio.gather(*tasks)
            for items in results:
                out.extend(items)
    return out

def fetch_all(*args, **kwargs) -> List[dict]:
    """Wrapper sync cho async_fetch_dateperiod (dùng trong tool/test/CLI)."""
    return asyncio.run(async_fetch_dateperiod(*args, **kwargs))
