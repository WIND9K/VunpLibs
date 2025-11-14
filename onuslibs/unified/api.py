from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..config.settings import OnusSettings
from ..http.client import HttpClient
from ..pagination.header_pager import HeaderPager
from ..security.headers import build_headers

__all__ = ["fetch_json"]

log = logging.getLogger(__name__)


# ============================================================================
# Helpers chung
# ============================================================================


def _normalize_fields(
    fields: Optional[Sequence[str] | str],
) -> Optional[str]:
    """
    Chấp nhận list/tuple hoặc CSV string -> trả về CSV sạch (hoặc None).
    """
    if not fields:
        return None
    if isinstance(fields, str):
        parts = [p.strip() for p in fields.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in fields if str(p).strip()]
    return ",".join(parts) if parts else None


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """
    Ưu tiên: list -> pageItems -> items -> [].
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
    """
    Cảnh báo mềm nếu một số field top-level không có trong item đầu tiên.
    Không raise để an toàn runtime.
    """
    if not items or not fields_csv:
        return
    want = [p.strip() for p in fields_csv.split(",") if p.strip()]
    if not want:
        return
    sample = items[0]
    missing = [f for f in want if "." not in f and f not in sample]
    if missing:
        log.warning("Thiếu một số field trong payload: %s", ", ".join(missing))


# ============================================================================
# Helpers cho datePeriod (segmentation)
# ============================================================================


def _parse_iso(dt_str: str) -> datetime:
    """
    Parse chuỗi ISO 8601 đơn giản thành datetime.

    - Hỗ trợ dạng có offset hoặc không offset.
    - Nếu chỉ 'YYYY-MM-DD' thì tự thêm T00:00:00.
    """
    s = dt_str.strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T00:00:00")
        raise


def _to_iso(dt: datetime) -> str:
    """
    Cắt microseconds, giữ nguyên tz, dùng cho datePeriod.
    """
    if dt.microsecond:
        dt = dt.replace(microsecond=0)
    return dt.isoformat()


def _build_segments(
    start: datetime,
    end: datetime,
    hours: int,
) -> List[tuple[datetime, datetime]]:
    """
    Chia [start, end] thành nhiều segment liên tiếp, mỗi segment
    dài tối đa `hours` giờ.
    """
    if hours <= 0:
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

    return segments


def _init_http_client(st: OnusSettings, client: Optional[HttpClient]) -> HttpClient:
    """
    Khởi tạo HttpClient tương thích cả kiểu (settings) và (base_url: str).
    """
    if client is not None:
        return client
    try:
        return HttpClient(st)
    except TypeError:
        return HttpClient(getattr(st, "base_url", ""))


# ============================================================================
# 1 window (không tự cắt datePeriod)
# ============================================================================


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
    pager_func: Optional[Callable[..., Iterable[List[Dict[str, Any]]]]],
    extra_headers: Optional[Dict[str, str]],
    parallel: bool,
    workers: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Xử lý 1 'cửa sổ' dữ liệu:

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

    def _maybe_dedupe(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not unique_key:
            return batch
        out: List[Dict[str, Any]] = []
        for it in batch:
            k = it.get(unique_key)
            if k in seen:
                continue
            if k is not None:
                seen.add(k)
            out.append(it)
        return out

    # 4) phân trang
    if paginate:
        pager = pager_func

        if pager is None and parallel:
            try:  # optional
                from ..pagination.parallel_pager import (
                    header_fetch_all_parallel as _parallel,
                )

                def pager(cli2, ep, params=None, headers=None, page_size=None):
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
            def pager(cli2, ep, params=None, headers=None, page_size=None):
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
            items = _maybe_dedupe(items)
            if not items:
                continue
            if on_batch:
                try:
                    on_batch(items)
                except Exception as e:
                    log.warning("on_batch raise: %s", e)
            results.extend(items)
        return results

    # 4') single GET (không phân trang)
    resp = cli.get(endpoint, params=final_params, headers=hdrs)
    resp.raise_for_status()
    items = _extract_items(resp.json())
    if strict_fields:
        _soft_check_fields(items, fields_csv)
    items = _maybe_dedupe(items)
    if on_batch and items:
        try:
            on_batch(items)
        except Exception as e:
            log.warning("on_batch raise: %s", e)
    results.extend(items)
    return results


# ============================================================================
# Facade duy nhất: fetch_json (có thể tự cắt datePeriod theo ENV)
# ============================================================================


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
    pager_func: Optional[Callable[..., Iterable[List[Dict[str, Any]]]]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    # Parallel: nếu None -> dùng settings.pager_parallel (ONUSLIBS_PARALLEL)
    parallel: Optional[bool] = None,
    workers: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Facade GET JSON:

    - Đọc base_url, page_size, rate-limit... từ OnusSettings (ENV).
    - Nếu có datePeriod + ONUSLIBS_DATE_SEGMENT_HOURS > 0 + paginate=True:
        -> tự chia datePeriod thành nhiều segment giờ cố định,
           gọi _fetch_single_window cho từng segment.
    - Ngược lại:
        -> chỉ gọi _fetch_single_window 1 lần (không segment).
    """
    st = settings or OnusSettings()
    base_params: Dict[str, Any] = dict(params or {})

    # parallel: nếu caller không truyền -> lấy từ ENV (pager_parallel)
    eff_parallel: bool = (
        bool(st.pager_parallel) if parallel is None else bool(parallel)
    )

    raw_dp = base_params.get("datePeriod")
    hours = getattr(st, "date_segment_hours", 0) or 0
    paginate = bool(paginate)

    # Quyết định segmentation: hoàn toàn theo ENV + có datePeriod hay không
    do_segment = bool(paginate and raw_dp and hours > 0)

    # ---- Không segment: 1 window duy nhất ----
    if not do_segment:
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

    # ---- Segment theo datePeriod ----
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

    segments = _build_segments(start_dt, end_dt, hours)
    if not segments:
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

    shared_client = _init_http_client(st, client)

    results: List[Dict[str, Any]] = []
    seen: set = set() if unique_key else set()

    def _merge_batch(batch: List[Dict[str, Any]]) -> None:
        """
        Gom kết quả từ 1 segment vào results, dedupe cross-segment theo unique_key.
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
            except Exception as e:
                log.warning("on_batch raise (segment): %s", e)
        results.extend(batch)

    def _run_segment(seg: tuple[datetime, datetime]) -> List[Dict[str, Any]]:
        seg_start, seg_end = seg
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
            unique_key=None,  # dedupe cross-segment ở ngoài
            on_batch=None,
            client=shared_client,
            pager_func=pager_func,
            extra_headers=extra_headers,
            parallel=eff_parallel,
            workers=workers,
        )

    # hiện tại chạy segment tuần tự; nếu muốn, sau này có thể dùng st.segment_parallel
    for seg in segments:
        seg_rows = _run_segment(seg)
        _merge_batch(seg_rows)

    return results
