from __future__ import annotations

"""
Facade cấp cao cho OnusLibs: fetch_json_segmented

Mục tiêu:
  - Dùng lại fetch_json (facade lõi) + HeaderPager cho phân trang.
  - Tự động chia nhỏ 1 datePeriod lớn thành nhiều khúc theo ENV:
        ONUSLIBS_DATE_SEGMENT_HOURS
    để tránh backend limit offset (thường ~10k records).
  - ENV-first: app KHÔNG cần truyền thêm tham số split, chỉ chỉnh ENV.

Nguyên tắc:
  - Nếu:
        - Không có param datePeriod (hoặc date_param khác),
        - HOẶC ONUSLIBS_DATE_SEGMENT_HOURS <= 0
    => Gọi thẳng fetch_json (không segment).
  - Nếu có datePeriod + date_segment_hours > 0:
        - Parse "start,end"
        - Chia [start,end] thành các đoạn length <= date_segment_hours (giờ)
        - Gọi fetch_json cho từng đoạn, rồi gom kết quả.
  - Nếu unique_key != None:
        - Dedupe cross-segment theo unique_key sau khi gom.

Lưu ý:
  - Việc phân trang trong MỖI segment vẫn do HeaderPager xử lý,
    thông qua fetch_json(..., paginate=True, pager_func=...).
"""

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..config.settings import OnusSettings
from .api import fetch_json


# ---------------------------------------------------------------------------
# Helpers xử lý thời gian
# ---------------------------------------------------------------------------


def _parse_iso(dt_str: str) -> datetime:
    """
    Parse chuỗi ISO 8601 đơn giản thành datetime.

    - Hỗ trợ cả dạng có offset (2025-10-11T00:00:00+07:00)
      lẫn dạng không offset (2025-10-11T00:00:00).
    - Không ép timezone: giữ nguyên theo fromisoformat.
    """
    s = dt_str.strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Fallback đơn giản: nếu chỉ có "YYYY-MM-DD", tự thêm T00:00:00
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T00:00:00")
        raise


def _to_iso(dt: datetime) -> str:
    """
    Chuyển datetime về chuỗi ISO dùng cho datePeriod.

    - Giữ nguyên offset nếu dt có tzinfo.
    - Cắt microseconds cho gọn.
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
    Chia đoạn [start, end] thành nhiều segment liên tiếp, mỗi segment
    dài tối đa `hours` giờ.

    - Giả định start <= end.
    - Segment cuối có thể ngắn hơn.
    """
    if hours <= 0:
        # Không nên xảy ra nếu đã validate, nhưng cứ bảo vệ
        return [(start, end)]

    segments: List[tuple[datetime, datetime]] = []
    cur = start
    delta = timedelta(hours=hours)

    # Dùng while cur < end để tránh trùng lặp mốc end
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


# ---------------------------------------------------------------------------
# Facade segmented
# ---------------------------------------------------------------------------


def fetch_json_segmented(
    endpoint: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    fields: Optional[str] = None,
    order_by: Optional[str] = None,
    settings: Optional[OnusSettings] = None,
    page_size: Optional[int] = None,
    paginate: bool = True,
    unique_key: Optional[str] = None,
    date_param: str = "datePeriod",
    pager_func: Optional[
        Callable[..., Iterable[List[Dict[str, Any]]]]
    ] = None,
) -> List[Dict[str, Any]]:
    """
    Facade cấp cao cho các API có datePeriod dễ vượt >10k records.

    - Nếu không có date_period hoặc date_segment_hours <= 0:
        -> Gọi thẳng fetch_json (không segment).
    - Nếu có:
        -> Tự chia datePeriod thành nhiều khúc theo ONUSLIBS_DATE_SEGMENT_HOURS,
           gọi fetch_json cho từng khúc, rồi gom kết quả.

    Tham số:
        endpoint    : endpoint REST, ví dụ "/api/transfers"
        params      : dict param gốc, chứa cả datePeriod
        fields      : CSV các field, truyền thẳng xuống fetch_json
        order_by    : chuỗi orderBy, truyền thẳng xuống fetch_json
        settings    : OnusSettings; nếu None -> OnusSettings() (ENV-first)
        page_size   : override pageSize; nếu None -> dùng settings.page_size
        paginate    : True -> bật HeaderPager; False -> mỗi segment là 1 GET
        unique_key  : nếu set, dedupe cross-segment theo field này
        date_param  : tên param dùng làm datePeriod (mặc định "datePeriod")
        pager_func  : pager override (vd để chạy song song); truyền xuống fetch_json
    """
    st = settings or OnusSettings()
    ps = page_size or st.page_size
    p: Dict[str, Any] = dict(params or {})

    # Lấy datePeriod từ params (vd "2025-10-11T00:00:00,2025-10-11T23:59:59")
    raw_dp = p.get(date_param)
    if not raw_dp or st.date_segment_hours is None or st.date_segment_hours <= 0:
        # Không segment -> dùng lại fetch_json (facade lõi) như cũ
        return fetch_json(
            endpoint=endpoint,
            params=p,
            fields=fields,
            order_by=order_by,
            settings=st,
            page_size=ps,
            paginate=paginate,
            unique_key=unique_key,
            pager_func=pager_func,
        )

    # ---- Parse datePeriod "start,end" ----
    try:
        start_str, end_str = str(raw_dp).split(",", 1)
    except ValueError:
        raise ValueError(
            f"Invalid {date_param} format: {raw_dp!r}. "
            f"Expected 'start,end' in ISO 8601."
        )
    start_dt = _parse_iso(start_str)
    end_dt = _parse_iso(end_str)
    if end_dt < start_dt:
        raise ValueError(
            f"{date_param} end < start: start={start_str!r}, end={end_str!r}"
        )

    # ---- Xây danh sách segments theo ENV date_segment_hours ----
    segments = _build_segments(start_dt, end_dt, st.date_segment_hours)

    all_rows: List[Dict[str, Any]] = []
    # Không dedupe ngay trong từng segment; để cuối cùng dedupe 1 lần
    for seg_start, seg_end in segments:
        seg_params = dict(p)
        seg_params[date_param] = f"{_to_iso(seg_start)},{_to_iso(seg_end)}"

        rows = fetch_json(
            endpoint=endpoint,
            params=seg_params,
            fields=fields,
            order_by=order_by,
            settings=st,
            page_size=ps,
            paginate=paginate,
            unique_key=None,  # dedupe cross-segment ở dưới
            pager_func=pager_func,
        )
        all_rows.extend(rows)

    # ---- Dedupe cross-segment nếu có unique_key ----
    if unique_key:
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for r in all_rows:
            key = r.get(unique_key)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped

    return all_rows
