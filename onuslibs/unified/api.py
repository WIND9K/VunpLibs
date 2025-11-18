from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..config.settings import OnusSettings
from ..http.client import HttpClient
from ..pagination.header_pager import HeaderPager
from ..security.headers import build_headers

__all__ = ["fetch_json"]

log = logging.getLogger(__name__)


# ========= Helpers chung =========


def _normalize_fields(fields: Optional[Sequence[str] | str]) -> Optional[str]:
    """Chuẩn hoá `fields` thành chuỗi CSV hoặc None.

    - None / rỗng => None
    - str         => tách theo dấu phẩy, strip từng phần
    - sequence    => map sang str, strip từng phần
    """
    if not fields:
        return None
    if isinstance(fields, str):
        parts = [p.strip() for p in fields.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in fields if str(p).strip()]
    return ",".join(parts) if parts else None


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """Trích danh sách item từ response JSON.

    Ưu tiên:
    - nếu payload là list            => trả luôn list
    - nếu payload là dict và có key:
        - 'pageItems' là list        => dùng pageItems
        - 'items' là list            => dùng items
    - ngược lại                      => []
    """
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("pageItems"), list):
            return list(payload["pageItems"])
        if isinstance(payload.get("items"), list):
            return list(payload["items"])
    return []


def _soft_check_fields(items: List[Dict[str, Any]], fields_csv: Optional[str]) -> None:
    """Cảnh báo mềm nếu một số field top-level không có trong item đầu tiên.

    Không raise để an toàn runtime – chỉ log WARNING để dev kiểm tra.
    """
    if not items or not fields_csv:
        return

    first = items[0]
    missing = [f for f in fields_csv.split(",") if f and f not in first]
    if missing:
        log.warning(
            "strict_fields=True nhưng các field sau không có trong item đầu tiên: %s",
            ", ".join(missing),
        )


def _parse_iso(dt_str: str) -> datetime:
    """Parse chuỗi ISO 8601 đơn giản thành datetime.

    - Hỗ trợ dạng có offset hoặc không offset.
    - Nếu chỉ 'YYYY-MM-DD' thì tự thêm 'T00:00:00'.
    """
    s = dt_str.strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T00:00:00")
        raise


def _to_iso(dt: datetime) -> str:
    """Chuẩn hoá datetime sang ISO, bỏ microseconds (nếu có)."""
    if dt.microsecond:
        dt = dt.replace(microsecond=0)
    return dt.isoformat()


def _build_segments(start: datetime, end: datetime, hours: int) -> List[tuple[datetime, datetime]]:
    """Chia khoảng thời gian [start, end] thành các segment dài `hours` giờ.

    - Nếu hours <= 0 hoặc start >= end => trả [(start, end)].
    - Segment cuối có thể ngắn hơn, đảm bảo kết thúc đúng `end`.
    """
    if hours <= 0 or end <= start:
        return [(start, end)]

    segments: List[tuple[datetime, datetime]] = []
    cur = start
    delta = timedelta(hours=hours)

    while cur < end:
        seg_start = cur
        seg_end = cur + delta
        if seg_end > end:
            seg_end = end
        segments.append((seg_start, seg_end))
        if seg_end == end:
            break
        cur = seg_end

    if not segments:
        segments.append((start, end))
    return segments


def _init_http_client(st: OnusSettings, client: Optional[HttpClient]) -> HttpClient:
    """Khởi tạo HttpClient.

    - Nếu caller đã truyền client => dùng lại (thuận tiện test / DI).
    - Ngược lại, tạo HttpClient mới với base_url từ settings.
    """
    if client is not None:
        return client
    # HttpClient hiện tại tự đọc OnusSettings nội bộ (rate-limit, timeout, HTTP/2...)
    return HttpClient(st)


# ---------- 1 window (1 datePeriod hoặc không dùng datePeriod) ----------


def _fetch_single_window(
    st: OnusSettings,
    endpoint: str,
    params: Optional[Dict[str, Any]],
    *,
    fields: Optional[Sequence[str] | str],
    page_size: Optional[int],
    paginate: bool,
    order_by: Optional[str],
    strict_fields: bool,
    unique_key: Optional[str],
    on_batch: Optional[Callable[[List[Dict[str, Any]]], None]],
    client: Optional[HttpClient],
    pager_func: Optional[
        Callable[[HttpClient, str, Dict[str, Any], Dict[str, str], int], Iterable[List[Dict[str, Any]]]]
    ],
    extra_headers: Optional[Dict[str, str]],
    parallel: bool,
    workers: Optional[int],
) -> List[Dict[str, Any]]:
    """Xử lý 1 'cửa sổ' dữ liệu.

    Các bước:

    - build_headers
    - build params (fields / orderBy / pageSize)
    - phân trang bằng HeaderPager (hoặc pager DI / song song nếu có)
    - hoặc single GET nếu paginate=False
    - dedupe theo unique_key trong phạm vi cửa sổ này (nếu được yêu cầu)
    """
    # 1) headers
    hdrs: Dict[str, str] = build_headers(st)
    if extra_headers:
        hdrs.update(extra_headers)

    # 2) params
    final_params: Dict[str, Any] = dict(params or {})
    fields_csv = _normalize_fields(fields)
    if fields_csv:
        final_params["fields"] = fields_csv
    if order_by:
        final_params["orderBy"] = order_by

    # Khi bật paginate, "page" phải do HeaderPager điều khiển.
    if paginate:
        final_params.pop("page", None)  # bỏ page caller truyền vào
        final_params.setdefault(
            "pageSize",
            page_size or getattr(st, "page_size", None),
        )

    # 3) HttpClient
    cli = _init_http_client(st, client)

    results: List[Dict[str, Any]] = []
    seen: set = set() if unique_key else set()

    def _merge_items(items: List[Dict[str, Any]]) -> None:
        nonlocal results, seen
        if not items:
            return
        if unique_key:
            out: List[Dict[str, Any]] = []
            for it in items:
                k = it.get(unique_key)
                if k in seen:
                    continue
                if k is not None:
                    seen.add(k)
                out.append(it)
            items = out
        if not items:
            return
        if on_batch:
            try:
                on_batch(items)
            except Exception as e:  # pragma: no cover - bảo vệ runtime
                log.warning("on_batch raise: %s", e)
        results.extend(items)

    # 4) phân trang
    if paginate:
        pager = pager_func

        if pager is None and parallel:
            # Thử dùng parallel_pager nếu có
            try:
                from ..pagination.parallel_pager import (
                    header_fetch_all_parallel as _parallel,
                )

                def pager(
                    cli2: HttpClient,
                    ep: str,
                    params: Optional[Dict[str, Any]] = None,
                    headers: Optional[Dict[str, str]] = None,
                    page_size: Optional[int] = None,
                ) -> Iterable[List[Dict[str, Any]]]:
                    return _parallel(
                        cli2,
                        ep,
                        params=params or {},
                        headers=headers or {},
                        page_size=(page_size or getattr(st, "page_size", None)),
                        max_workers=workers,
                    )

            except Exception:
                pager = None

        if pager is None:
            # tuần tự dùng HeaderPager (chuẩn Cyclos)
            def pager(
                cli2: HttpClient,
                ep: str,
                params: Optional[Dict[str, Any]] = None,
                headers: Optional[Dict[str, str]] = None,
                page_size: Optional[int] = None,
            ) -> Iterable[List[Dict[str, Any]]]:
                pg = HeaderPager(
                    cli2,
                    ep,
                    params=params or {},
                    headers=headers or {},
                    page_size=(page_size or getattr(st, "page_size", None)),
                )
                return pg.fetch_all()

        for batch in pager(
            cli,
            endpoint,
            params=final_params,
            headers=hdrs,
            page_size=(page_size or getattr(st, "page_size", None)),
        ):
            items = _extract_items(batch)
            if strict_fields:
                _soft_check_fields(items, fields_csv)
            _merge_items(items)

        return results

    # không paginate: single GET
    resp = cli.get(endpoint, params=final_params, headers=hdrs)
    payload = resp.json()
    items = _extract_items(payload)
    if strict_fields:
        _soft_check_fields(items, fields_csv)
    _merge_items(items)
    return results


# ---------- Facade chính: fetch_json ----------

def fetch_json(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    fields: Optional[Sequence[str] | str] = None,
    page_size: Optional[int] = None,
    paginate: bool = True,
    order_by: Optional[str] = None,
    strict_fields: bool = False,
    unique_key: Optional[str] = None,
    settings: Optional[OnusSettings] = None,
    on_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    # DI / mở rộng
    client: Optional[HttpClient] = None,
    pager_func: Optional[
        Callable[[HttpClient, str, Dict[str, Any], Dict[str, str], int], Iterable[List[Dict[str, Any]]]]
    ] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    # Parallel: nếu None -> dùng settings.pager_parallel (ONUSLIBS_PARALLEL)
    parallel: Optional[bool] = None,
    workers: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Facade GET JSON với hybrid auto-segment theo datePeriod.

    Hành vi tổng quát (v3 – hybrid):

    - Đọc base_url, page_size, rate-limit... từ OnusSettings (ENV).
    - Nếu **không có** `datePeriod` hoặc `paginate=False`:
        -> chỉ gọi `_fetch_single_window` 1 lần (không cắt thời gian).
    - Nếu có `datePeriod` và `paginate=True`:
        1) Chia khoảng thời gian lớn thành nhiều window theo
           `ONUSLIBS_MAX_WINDOW_DAYS` (nếu > 0).
        2) Với từng window, nếu bật `AUTO_SEGMENT` và có
           `ONUSLIBS_MAX_ROWS_PER_WINDOW`:
               - Peek `X-Total-Count` 1 lần.
               - Tự chia window thành nhiều segment nhỏ sao cho
                 mỗi segment ~<= MAX_ROWS_PER_WINDOW (ước tính).
        3) Với từng segment thời gian:
               - Gọi `_fetch_single_window` để phân trang theo header.
               - Nếu vẫn gặp lỗi 422 do pagination và `AUTO_SEGMENT=True`:
                   -> fallback chia đôi segment theo thời gian tối đa
                      `ONUSLIBS_MAX_SEGMENT_SPLIT_DEPTH` lần.

    Mục tiêu:

    - Khi dữ liệu ít (< limit server) -> chỉ 1 segment, số request tối thiểu.
    - Khi dữ liệu nhiều (> limit, gây 422) -> lib tự chia nhỏ datePeriod
      dựa trên số dòng ước tính, không cần dùng ONUSLIBS_DATE_SEGMENT_HOURS.
    """
    st = settings or OnusSettings()
    base_params: Dict[str, Any] = dict(params or {})

    # parallel: nếu caller không truyền -> lấy từ ENV (pager_parallel)
    eff_parallel: bool = bool(st.pager_parallel) if parallel is None else bool(parallel)

    paginate = bool(paginate)
    raw_dp = base_params.get("datePeriod")

    # Cấu hình segmentation từ OnusSettings / ENV
    auto_segment = bool(getattr(st, "auto_segment", False))

    max_split_depth = getattr(st, "max_segment_split_depth", 0) or 0
    try:
        max_split_depth = int(max_split_depth)
    except Exception:
        max_split_depth = 0
    if max_split_depth < 0:
        max_split_depth = 0

    max_rows_conf = getattr(st, "max_rows_per_window", None)
    try:
        max_rows_per_window = int(max_rows_conf) if max_rows_conf is not None else 0
    except Exception:
        max_rows_per_window = 0
    if max_rows_per_window < 0:
        max_rows_per_window = 0

    max_window_conf = getattr(st, "max_window_days", None)
    try:
        max_window_days = int(max_window_conf) if max_window_conf is not None else 0
    except Exception:
        max_window_days = 0
    if max_window_days < 0:
        max_window_days = 0

    seg_parallel_conf = bool(getattr(st, "segment_parallel", False))
    seg_workers_conf = getattr(st, "segment_max_workers", None)
    if not isinstance(seg_workers_conf, int) or seg_workers_conf <= 0:
        seg_workers_conf = None

    # ---- Không có datePeriod hoặc không phân trang: 1 window duy nhất ----
    if not raw_dp or not paginate:
        return _fetch_single_window(
            st=st,
            endpoint=endpoint,
            params=base_params,
            fields=fields,
            page_size=page_size,
            paginate=paginate,
            order_by=order_by,
            strict_fields=strict_fields,
            unique_key=unique_key,
            on_batch=on_batch,
            client=client,
            pager_func=pager_func,
            extra_headers=extra_headers,
            parallel=eff_parallel,
            workers=workers,
        )

    # ---- Có datePeriod + paginate=True: chuẩn bị window theo MAX_WINDOW_DAYS ----
    try:
        start_str, end_str = str(raw_dp).split(",", 1)
    except ValueError:
        raise ValueError(
            f"Invalid datePeriod format: {raw_dp!r}. Expected 'start,end' in ISO."
        )

    start_dt = _parse_iso(start_str)
    end_dt = _parse_iso(end_str)
    if end_dt < start_dt:
        raise ValueError(
            f"datePeriod end < start: start={start_str!r}, end={end_str!r}"
        )

    # Bước 1: chia thành các window theo ngày (nếu có MAX_WINDOW_DAYS)
    windows: List[tuple[datetime, datetime]] = []
    if max_window_days > 0:
        cur = start_dt
        delta = timedelta(days=max_window_days)
        while cur < end_dt:
            win_start = cur
            win_end = cur + delta
            if win_end > end_dt:
                win_end = end_dt
            windows.append((win_start, win_end))
            cur = win_end
    else:
        windows.append((start_dt, end_dt))

    if not windows:
        windows.append((start_dt, end_dt))

    # HttpClient dùng chung cho mọi segment + request peek
    shared_client = _init_http_client(st, client)

    # page_size hiệu lực để gửi lên API (dùng cả cho peek)
    eff_page_size = page_size or getattr(st, "page_size", None) or 20000
    try:
        eff_page_size = int(eff_page_size)
    except Exception:
        eff_page_size = 20000
    if eff_page_size <= 0:
        eff_page_size = 20000

    def _estimate_total_rows(seg_start: datetime, seg_end: datetime) -> Optional[int]:
        """Peek 1 lần X-Total-Count cho 1 window.

        Nếu header thiếu hoặc sai định dạng -> trả None để caller skip row-split.
        """
        seg_params = dict(base_params)
        seg_params["datePeriod"] = f"{_to_iso(seg_start)},{_to_iso(seg_end)}"
        seg_params["page"] = 0
        seg_params["pageSize"] = eff_page_size

        hdrs = build_headers(st)
        if extra_headers:
            hdrs = dict(hdrs)
            hdrs.update(extra_headers)

        resp = shared_client.get(endpoint, params=seg_params, headers=hdrs)

        headers = resp.headers
        total_val: Optional[str] = None
        for k in ("X-Total-Count", "x-total-count", "X-Total-count", "x-total-Count"):
            if k in headers:
                total_val = headers.get(k)
                break
        if total_val is None:
            log.warning(
                "Row-segment: missing X-Total-Count header cho window %s..%s, bỏ qua chia theo rows.",
                seg_start,
                seg_end,
            )
            return None
        try:
            return int(total_val)
        except Exception:
            log.warning(
                "Row-segment: invalid X-Total-Count=%r cho window %s..%s, bỏ qua chia theo rows.",
                total_val,
                seg_start,
                seg_end,
            )
            return None

    # Bước 2: từ windows -> segments sau khi tính toán theo MAX_ROWS_PER_WINDOW
    segments: List[tuple[datetime, datetime]] = []

    if auto_segment and max_rows_per_window > 0:
        for win_start, win_end in windows:
            total_rows = _estimate_total_rows(win_start, win_end)
            if total_rows is None or total_rows <= 0 or total_rows <= max_rows_per_window:
                # Không rõ / ít dòng -> giữ nguyên window
                segments.append((win_start, win_end))
                continue

            # Tính số segment cần cắt (non-recursive)
            n_segments = (total_rows + max_rows_per_window - 1) // max_rows_per_window
            if n_segments <= 1:
                segments.append((win_start, win_end))
                continue

            window_len = win_end - win_start
            if window_len.total_seconds() <= 0:
                segments.append((win_start, win_end))
                continue

            seg_len = window_len / n_segments
            cur = win_start
            for i in range(n_segments):
                seg_start = cur
                if i == n_segments - 1:
                    seg_end = win_end
                else:
                    seg_end = seg_start + seg_len
                if seg_end <= seg_start:
                    # bảo vệ trường hợp rounding kỳ quặc
                    seg_end = seg_start + timedelta(seconds=1)
                    if seg_end > win_end:
                        seg_end = win_end
                segments.append((seg_start, seg_end))
                cur = seg_end
    else:
        # Không bật auto-segment hoặc không cấu hình rows -> chỉ dùng windows
        segments = list(windows)

    if not segments:
        segments.append((start_dt, end_dt))

    results: List[Dict[str, Any]] = []
    seen: set = set() if unique_key else set()

    def _merge_batch(batch: List[Dict[str, Any]]) -> None:
        """Gom kết quả từ 1 segment vào results, dedupe cross-segment.

        - Nếu không có unique_key => chỉ append.
        - Nếu có unique_key      => bỏ qua record trùng key across segment.
        """
        nonlocal results, seen
        if not batch:
            return
        if unique_key:
            out: List[Dict[str, Any]] = []
            for it in batch:
                k = it.get(unique_key)
                if k in seen:
                    continue
                if k is not None:
                    seen.add(k)
                out.append(it)
            batch = out
            if not batch:
                return
        if on_batch:
            try:
                on_batch(batch)
            except Exception as e:  # pragma: no cover - bảo vệ runtime
                log.warning("on_batch raise: %s", e)
        results.extend(batch)

    def _run_window(seg_start: datetime, seg_end: datetime) -> List[Dict[str, Any]]:
        """Chạy fetch cho 1 cửa sổ thời gian cụ thể (không tự chia nhỏ).

        Luôn override lại `datePeriod` theo (seg_start, seg_end).
        """
        seg_params = dict(base_params)
        seg_params["datePeriod"] = f"{_to_iso(seg_start)},{_to_iso(seg_end)}"
        return _fetch_single_window(
            st=st,
            endpoint=endpoint,
            params=seg_params,
            fields=fields,
            page_size=page_size,
            paginate=paginate,
            order_by=order_by,
            strict_fields=strict_fields,
            unique_key=None,  # dedupe cross-segment xử lý ở _merge_batch
            on_batch=None,
            client=shared_client,
            pager_func=pager_func,
            extra_headers=extra_headers,
            parallel=eff_parallel,
            workers=workers,
        )

    def _is_pagination_422(err: Exception) -> bool:
        msg = str(err)
        if "422" in msg and "Pagination error" in msg:
            return True
        cause = getattr(err, "__cause__", None)
        if cause is not None:
            cmsg = str(cause)
            if "422" in cmsg and "Pagination error" in cmsg:
                return True
        return False

    def _run_with_split(seg_start: datetime, seg_end: datetime, depth: int) -> List[Dict[str, Any]]:
        """Chạy 1 segment, nếu gặp 422 thì chia đôi theo thời gian (auto-segment fallback 422).

        - Chỉ kích hoạt khi `auto_segment=True` và `max_split_depth>0`.
        - Nếu vượt quá depth cho phép vẫn 422 => log cảnh báo và raise.
        """
        try:
            return _run_window(seg_start, seg_end)
        except Exception as e:  # pragma: no cover - bảo vệ runtime
            if not (auto_segment and max_split_depth > 0 and _is_pagination_422(e)):
                # Không phải 422 do pagination hoặc auto-segment tắt -> re-raise
                raise
            if depth >= max_split_depth:
                log.error(
                    "Auto-segment: reached max split depth=%s for window %s..%s nhưng API vẫn trả 422.",
                    max_split_depth,
                    seg_start,
                    seg_end,
                )
                raise

            # Chia đôi khoảng thời gian và thử lại hai nửa
            mid = seg_start + (seg_end - seg_start) / 2
            # Tránh phân đoạn zero-length (bảo vệ floating rounding)
            if mid <= seg_start or mid >= seg_end:
                log.error(
                    "Auto-segment: cannot further split window %s..%s (depth=%s) - segment quá nhỏ.",
                    seg_start,
                    seg_end,
                    depth,
                )
                raise

            left_rows = _run_with_split(seg_start, mid, depth + 1)
            right_rows = _run_with_split(mid, seg_end, depth + 1)
            return left_rows + right_rows

    def _process_segment(seg: tuple[datetime, datetime]) -> List[Dict[str, Any]]:
        seg_start, seg_end = seg
        if auto_segment and max_split_depth > 0:
            return _run_with_split(seg_start, seg_end, 0)
        # Không bật auto-segment fallback 422 -> chỉ chạy 1 lần
        return _run_window(seg_start, seg_end)

    # ===== Chạy các segment (tuần tự hoặc song song tuỳ ENV) =====
    if seg_parallel_conf and len(segments) > 1:
        max_workers = seg_workers_conf or getattr(st, "max_inflight", 4) or len(segments)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_process_segment, seg): seg for seg in segments}
            for fut in as_completed(future_map):
                seg_rows = fut.result()
                _merge_batch(seg_rows)
    else:
        for seg in segments:
            seg_rows = _process_segment(seg)
            _merge_batch(seg_rows)

    return results
