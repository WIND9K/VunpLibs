# onuslibs/pagination/parallel_pager.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import ceil
import httpx

from .header_pager import HeaderPager  # tái dùng _extract_items()

def _fetch_single(http_client: Any, endpoint: str,
                  params: Dict[str, Any], headers: Dict[str, str],
                  page_size: int, page_index: int) -> Tuple[int, List[Dict[str, Any]], Dict[str, str]]:
    p = dict(params); p["page"] = page_index; p["pageSize"] = page_size
    resp = http_client.get(endpoint, params=p, headers=headers)
    resp.raise_for_status()
    items = HeaderPager._extract_items(resp.json())
    hdrs  = {k.lower(): v for k, v in resp.headers.items()}
    return page_index, items, hdrs

def header_fetch_all_parallel(
    http_client: Any,
    endpoint: str,
    *,
    params: Dict[str, Any],
    headers: Dict[str, str],
    page_size: int,
    max_workers: Optional[int] = None,   # mặc định lấy từ OnusSettings.max_inflight
) -> Iterable[List[Dict[str, Any]]]:
    """
    Pager chạy song song theo trang, nhưng vẫn:
      - Tôn trọng limiter RPS của HttpClient
      - Giữ thứ tự trang khi yield (0 -> N-1)
      - Dừng êm khi gặp 400/404/422 ở page > 0
      - Fallback tuần tự nếu không suy ra tổng số trang
    """
    # 1) Lấy page 0 (và yield ngay) để đọc header
    p0 = int(params.get("page", 0) or 0)
    try:
        _, items0, hdr0 = _fetch_single(http_client, endpoint, params, headers, page_size, page_index=p0)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 404, 422):
            return
        raise
    if not items0:
        return
    yield items0

    # 2) Tính trang cuối từ header (ưu tiên X-Page-Count, rồi X-Total-Count)
    last_page_idx: Optional[int] = None
    pc = (hdr0.get("x-page-count") or "").strip()
    if pc.isdigit():
        last_page_idx = max(0, int(pc) - 1)
    else:
        tc = (hdr0.get("x-total-count") or "").strip()
        if tc.isdigit() and page_size > 0:
            total = int(tc)
            last_page_idx = max(0, ceil(total / page_size) - 1) if total > 0 else 0

    # Không xác định được tổng số trang -> chạy tuần tự phần còn lại
    if last_page_idx is None:
        for batch in HeaderPager(http_client, endpoint, {"page": p0 + 1, **params}, headers, page_size).fetch_all():
            yield batch
        return

    start = p0 + 1
    end   = last_page_idx
    if end < start:
        return

    # 3) Xác định số worker: clamp để an toàn
    if max_workers is None:
        try:
            from ..config.settings import OnusSettings
            mw = int(OnusSettings().max_inflight)
        except Exception:
            mw = 4
    else:
        mw = int(max_workers)
    # ràng buộc cứng để không làm server “sốc”
    if mw < 1: mw = 1
    if mw > 16: mw = 16  # hard cap

    results: Dict[int, List[Dict[str, Any]]] = {}
    next_to_yield = start  # giữ thứ tự yield tăng dần
    buffer: Dict[int, List[Dict[str, Any]]] = {}

    def _safe_fetch(i: int) -> Tuple<int, List[Dict[str, Any]]]:
        try:
            _, items, _ = _fetch_single(http_client, endpoint, params, headers, page_size, page_index=i)
            return (i, items)
        except httpx.HTTPStatusError as e:
            # page vượt phạm vi -> coi như hết
            if i > 0 and e.response.status_code in (400, 404, 422):
                return (i, [])
            raise

    with ThreadPoolExecutor(max_workers=mw) as ex:
        futs = {ex.submit(_safe_fetch, i): i for i in range(start, end + 1)}
        for fut in as_completed(futs):
            i, items = fut.result()
            buffer[i] = items if items else []
            # yield theo thứ tự khi liên tiếp có sẵn
            while next_to_yield in buffer:
                batch = buffer.pop(next_to_yield)
                if batch:
                    yield batch
                next_to_yield += 1
