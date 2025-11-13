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


# ---------- helpers cơ bản ----------


def _normalize_fields(
    fields: Optional[Sequence[str] | str],
) -> Optional[str]:
    """Chấp nhận list/tuple hoặc CSV string -> trả về CSV sạch (hoặc None)."""
    if not fields:
        return None
    if isinstance(fields, str):
        parts = [p.strip() for p in fields.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in fields if str(p).strip()]
    return ",".join(parts) if parts else None


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """Ưu tiên: list -> pageItems -> items -> []."""
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("pageItems"), list):
            return list(payload["pageItems"])
        if isinstance(payload.get("items"), list):
            return list(payload["items"])
    return []


def _soft_check_fields(items: List[Dict[str, Any]], fields_csv: Optional[str]) -> None:
    """Cảnh báo mềm nếu field top-level thiếu; không raise để an toàn runtime."""
    if not items or not fields_csv:
        return
    want = [p.strip() for p in fields_csv.split(",") if p.strip()]
    if not want:
        return
    sample = items[0]
    missing = [f for f in want if "." not in f and f not in sample]
    if missing:
        log.warning("Thiếu một số field trong payload: %s", ", ".join(missing))


# ---------- helpers segmentation datePeriod ----------


def _parse_dateperiod(raw: str) -> tuple[datetime, datetime]:
    """Parse 'start,end' ISO strings thành 2 datetime."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"datePeriod không hợp lệ: {raw!r}")
    try:
        start = datetime.fromisoformat(parts[0])
        end = datetime.fromisoformat(parts[1])
    except Exception as e:  # pragma: no cover - lỗi cấu hình
        raise ValueError(f"Không parse được datePeriod: {raw!r}") from e
    if start > end:
        start, end = end, start
    return start, end


def _build_segments(
    start: datetime, end: datetime, hours: int
) -> List[tuple[datetime, datetime]]:
    """
    Chia [start, end] thành nhiều segment liên tiếp, mỗi segment tối đa 'hours' giờ.

    - Nếu hours <= 0: trả về đúng 1 segment (start, end).
    - Các segment liên tiếp nhau (end của segment trước == start của segment sau).
    - Nếu API coi end "bao gồm", có thể trùng biên; nên kết hợp unique_key để dedupe.
    """
    if hours <= 0:
        return [(start, end)]
    segments: List[tuple[datetime, datetime]] = []
    cur = start
    delta = timedelta(hours=hours)
    while cur < end:
        nxt = cur + delta
        if nxt >= end:
            segments.append((cur, end))
            break
        segments.append((cur, nxt))
        cur = nxt
    return segments


def _init_http_client(st: OnusSettings, client: Optional[HttpClient]) -> HttpClient:
    """Khởi tạo HttpClient tương thích cả kiểu (settings) và (base_url: str)."""
    if client is not None:
        return client
    try:
        # Kiểu cũ: HttpClient(settings)
        return HttpClient(st)
    except TypeError:
        # Kiểu mới: HttpClient(base_url="...")
        return HttpClient(getattr(st, "base_url", ""))


# ---------- 1 window (1 datePeriod) ----------


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
    Xử lý 1 'cửa sổ' dữ liệu (một datePeriod hoặc không dùng datePeriod):

    - build_headers
    - build params (fields / orderBy / pageSize)
    - phân trang bằng HeaderPager (hoặc pager DI / song song nếu có)
    - hoặc single GET nếu paginate=False
    - dedupe theo unique_key trong phạm vi cửa sổ này
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
    if paginate:
        final_params.setdefault("pageSize", page_size or getattr(st, "page_size", None))

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

        # Nếu parallel=True và có parallel_pager -> dùng; nếu không -> fallback
        if pager is None and parallel:
            try:  # pragma: no cover - optional
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
                except Exception as e:  # pragma: no cover - callback error
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
        except Exception as e:  # pragma: no cover
            log.warning("on_batch raise: %s", e)
    results.extend(items)
    return results


# ---------- facade duy nhất ----------


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
    # Parallel (opt-in cho phân trang bên trong 1 window)
    parallel: bool = False,
    workers: Optional[int] = None,
    # Segmentation theo datePeriod (tự động nếu có)
    date_param: str = "datePeriod",
    segment_date: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    Facade GET JSON hợp nhất (REST-first, Facade duy nhất).

    Hành vi:

      • Nếu KHÔNG có `datePeriod` hoặc `ONUSLIBS_DATE_SEGMENT_HOURS <= 0`:
          -> Xử lý y như bản cũ: một "cửa sổ" params, phân trang bằng HeaderPager.

      • Nếu CÓ `datePeriod` và `ONUSLIBS_DATE_SEGMENT_HOURS > 0`:
          -> Tự chia datePeriod thành nhiều segment (theo giờ),
             với mỗi segment gọi `_fetch_single_window` (có phân trang).
          -> Có thể chạy song song giữa các segment nếu
             `ONUSLIBS_SEGMENT_PARALLEL=true`.

    Các options:

      • unique_key:
          - Nếu set -> khử trùng lặp toàn cục giữa TẤT CẢ trang + segment.
      • strict_fields:
          - Cảnh báo thiếu field top-level, không raise.
      • parallel:
          - Bật phân trang song song bên trong 1 window nếu có `parallel_pager`.
      • segment_date:
          - None (mặc định): tự động segment nếu có datePeriod + hours>0.
          - True: ép bật segmentation (nếu có datePeriod).
          - False: tắt segmentation, luôn coi như 1 window.
    """
    st = settings or OnusSettings()

    base_params: Dict[str, Any] = dict(params or {})
    raw_dp = base_params.get(date_param)
    hours = st.date_segment_hours or 0

    paginate = bool(paginate)

    # Quyết định segmentation tự động
    auto_segment = bool(paginate and raw_dp and hours > 0)

    if segment_date is True:
        do_segment = bool(raw_dp and hours > 0)
    elif segment_date is False:
        do_segment = False
    else:
        do_segment = auto_segment

    # === Nhánh KHÔNG segment: giữ hành vi cũ 100% ===
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
            parallel=parallel,
            workers=workers,
        )

    # === Nhánh CÓ segment theo datePeriod ===
    try:
        start_dt, end_dt = _parse_dateperiod(str(raw_dp))
    except Exception as e:
        log.warning(
            "Không thể segment datePeriod=%r, fallback 1 window. Lỗi: %s", raw_dp, e
        )
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
            parallel=parallel,
            workers=workers,
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
            parallel=parallel,
            workers=workers,
        )

    # Dùng chung 1 HttpClient cho tất cả segment
    shared_client = _init_http_client(st, client)

    results: List[Dict[str, Any]] = []
    seen: set = set() if unique_key else set()

    def _merge_batch(batch: List[Dict[str, Any]]) -> None:
        nonlocal results, seen
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
            except Exception as e:  # pragma: no cover
                log.warning("on_batch raise (segment): %s", e)
        results.extend(batch)

    def _run_segment(seg: tuple[datetime, datetime]) -> List[Dict[str, Any]]:
        seg_start, seg_end = seg
        seg_params = dict(base_params)
        seg_params[date_param] = (
            f"{seg_start.isoformat()},{seg_end.isoformat()}"
        )
        # Bên trong mỗi segment KHÔNG dedupe theo unique_key (dedupe toàn cục bên ngoài)
        rows = _fetch_single_window(
            st=st,
            endpoint=endpoint,
            params=seg_params,
            fields=fields,
            page_size=page_size,
            paginate=paginate,
            order_by=order_by,
            strict_fields=strict_fields,
            unique_key=None,
            on_batch=None,
            client=shared_client,
            pager_func=pager_func,
            extra_headers=extra_headers,
            parallel=parallel,
            workers=workers,
        )
        return rows

    # Chạy các segment: song song hoặc tuần tự
    if st.segment_parallel and len(segments) > 1:
        try:  # pragma: no cover - phụ thuộc runtime
            from concurrent.futures import ThreadPoolExecutor, as_completed

            max_workers = st.segment_max_workers or st.max_inflight or len(segments)
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_run_segment, seg) for seg in segments]
                for fut in as_completed(futures):
                    seg_rows = fut.result()
                    _merge_batch(seg_rows)
        except Exception as e:
            log.warning(
                "Segment parallel gặp lỗi, fallback chạy tuần tự: %s", e
            )
            for seg in segments:
                seg_rows = _run_segment(seg)
                _merge_batch(seg_rows)
    else:
        for seg in segments:
            seg_rows = _run_segment(seg)
            _merge_batch(seg_rows)

    return results
