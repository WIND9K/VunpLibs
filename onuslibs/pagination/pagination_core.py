from __future__ import annotations
from typing import Any, Dict, Generator, Optional, Callable, Tuple, TYPE_CHECKING, List
from datetime import datetime, timedelta, timezone
import time as _time
from math import ceil

if TYPE_CHECKING:
    from onuslibs.pagination.config_pagination_core import Config

def _normalize_items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return (
            data.get("items")
            or data.get("data")
            or data.get("results")
            or data.get("content")
            or []
        )
    return []

def _lc_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not headers:
        return {}
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}

def _parse_int(v: Optional[str]) -> Optional[int]:
    try:
        return int(str(v).strip()) if v is not None else None
    except Exception:
        return None

def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()

def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def _get(src, key, default=None):
    if src is None:
        return default
    if isinstance(src, dict):
        return src.get(key, default)
    return getattr(src, key, default)

def fetch_all(
    cfg: "Config",
    *,
    start_date: datetime,
    end_date: datetime,
    client_request: Callable[[str, str, Dict[str, Any]], Tuple[int, Any, Dict[str, str]]],
    on_batch: Optional[Callable[[list], None]] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Cyclos (datePeriod + page=0):
      - Nếu strategy.split_by_day=True: tự cắt [start,end) thành các ngày [00:00,24:00) rồi xử lý từng ngày.
      - Mỗi khoảng: 1 PROBE lấy X-Total-Count -> num_windows = ceil(total/pageSize) -> chia N cửa sổ đều thời gian.
      - Với mỗi cửa sổ: gọi page=0; nếu header báo overflow (Has-Next/Page-Count>1/Total>pageSize) thì CHIA ĐÔI đệ quy.
      - boundary_mode='closed-open' mặc định để tránh lệch ±1 record ở ranh.
    """
    base_params = dict(_get(cfg, "params", {}) or {})
    method = (_get(cfg, "method", "GET") or "GET").upper()
    endpoint = _get(cfg, "endpoint", "")

    paging = _get(cfg, "paging", None)
    limits = _get(cfg, "limits", None)
    strategy = _get(cfg, "strategy", None)

    per_page_key = _get(paging, "per_page_param", "pageSize")
    page_key     = _get(paging, "page_param", "page")

    page_size    = int(_get(paging, "page_size", 20000))
    rps          = float(_get(limits, "req_per_sec", 3.0))

    epsilon_sec      = int(_get(strategy, "epsilon_seconds", 1) or 1)
    probe_page_size  = int(_get(strategy, "probe_page_size", 1) or 1)
    boundary_mode    = str(_get(strategy, "boundary_mode", "closed-open")).lower()
    split_by_day     = bool(_get(strategy, "split_by_day", False))

    def _throttle(last_ts: float) -> float:
        if rps <= 0:
            return _time.monotonic()
        now = _time.monotonic()
        elapsed = now - last_ts
        delay = max(0.0, 1.0 / rps - elapsed)
        if delay > 0:
            _time.sleep(delay)
        return _time.monotonic()

    def _day_windows(a: datetime, b: datetime) -> List[Tuple[datetime, datetime]]:
        # closed-open ngày
        out: List[Tuple[datetime, datetime]] = []
        cur = a
        while cur < b:
            next_day = datetime(cur.year, cur.month, cur.day) + timedelta(days=1)
            nxt = b if next_day > b else next_day
            out.append((cur, nxt))
            cur = nxt
        return out

    def _process_range(range_from: datetime, range_to: datetime) -> Generator[Dict[str, Any], None, None]:
        """Xử lý 1 khoảng thời gian (có thể là 1 ngày)."""
        last_call = 0.0
        # 1) PROBE
        probe_params = dict(base_params)
        probe_params["datePeriod"] = f"{_iso(range_from)},{_iso(range_to)}"
        probe_params[page_key] = 0
        probe_params[per_page_key] = probe_page_size

        last_call = _throttle(last_call)
        status, _, headers = client_request(method, endpoint, probe_params)
        if status >= 400:
            raise RuntimeError(f"HTTP {status} khi gọi {endpoint} với params={probe_params}")
        h = _lc_headers(headers)
        total = _parse_int(h.get("x-total-count"))
        if total is None:
            # fallback 1 lần với page_size thật
            probe_params2 = dict(probe_params)
            probe_params2[per_page_key] = page_size
            last_call = _throttle(last_call)
            status, data2, _ = client_request(method, endpoint, probe_params2)
            if status >= 400:
                raise RuntimeError(f"HTTP {status} khi gọi {endpoint} với params={probe_params2}")
            total = len(_normalize_items(data2))

        # 2) số cửa sổ
        num_windows = int(ceil(float(total) / float(page_size))) if page_size > 0 else 1
        if num_windows < 1:
            num_windows = 1

        # 3) chia đều thời gian
        if num_windows == 1:
            windows = [(range_from, range_to)]
        else:
            slot = (range_to - range_from) / num_windows
            windows: List[Tuple[datetime, datetime]] = []
            for i in range(num_windows):
                w_start = range_from + i * slot
                w_end   = range_from + (i + 1) * slot if i < num_windows - 1 else range_to
                if i > 0 and boundary_mode == "closed-closed":
                    w_start = min(w_end, w_start + timedelta(seconds=epsilon_sec))
                windows.append((w_start, w_end))

        def _split_window(a: datetime, b: datetime) -> Tuple[Tuple[datetime, datetime], Tuple[datetime, datetime]]:
            mid = a + (b - a) / 2
            if boundary_mode == "closed-closed":
                left  = (a, mid)
                right = (min(b, mid + timedelta(seconds=epsilon_sec)), b)
            else:  # closed-open
                left  = (a, mid)
                right = (mid, b)
            return left, right

        def _fetch_window(a: datetime, b: datetime) -> Generator[Dict[str, Any], None, None]:
            nonlocal last_call
            params = dict(base_params)
            params["datePeriod"] = f"{_iso(a)},{_iso(b)}"
            params[page_key] = 0
            params[per_page_key] = page_size

            last_call = _throttle(last_call)
            status, data, headers = client_request(method, endpoint, params)
            if status >= 400:
                raise RuntimeError(f"HTTP {status} khi gọi {endpoint} với params={params}")

            hh = _lc_headers(headers)
            items = _normalize_items(data)

            # Nhận diện overflow
            win_total = _parse_int(hh.get("x-total-count"))
            page_cnt  = _parse_int(hh.get("x-page-count"))
            has_next  = (hh.get("x-has-next-page", "").lower() == "true")
            overflow = False
            if win_total is not None and page_size > 0 and win_total > page_size:
                overflow = True
            if page_cnt is not None and page_cnt > 1:
                overflow = True
            if has_next:
                overflow = True

            if overflow:
                if (b - a).total_seconds() <= 1:
                    # quá hẹp để chia tiếp – trả items hiện có
                    pass
                else:
                    (a1, b1), (a2, b2) = _split_window(a, b)
                    for it in _fetch_window(a1, b1):
                        yield it
                    if a2 < b2:
                        for it in _fetch_window(a2, b2):
                            yield it
                    return

            if on_batch:
                on_batch(items)
            for it in items:
                yield it

        for a, b in windows:
            for it in _fetch_window(a, b):
                yield it

    # -------- điểm vào chính --------
    s = _to_naive_utc(start_date)
    e = _to_naive_utc(end_date)
    if s >= e:
        return

    if split_by_day:
        for day_from, day_to in _day_windows(s, e):
            for it in _process_range(day_from, day_to):
                yield it
    else:
        for it in _process_range(s, e):
            yield it
