# -*- coding: utf-8 -*-
from typing import Dict, List
from datetime import datetime
import dlt
from .pagination.segmented import async_fetch_dateperiod
from .utils import parse_filters

@dlt.source
def source(
    endpoint: str,
    start: str | datetime,
    end: str | datetime,
    *,
    filters: str | Dict[str, str] = "",
    fields: List[str] | str = None,
    split_by_day: bool = True,
    page_size: int | None = None,
    day_workers: int = 1,
    req_per_sec: float | None = None,
    http2: bool | None = None,
    timeout_s: float | None = None,
    debug: bool = False,
    force_segmented_paging: bool = True,
    segment_safety_ratio: float = 0.95,
    segment_min_seconds: float = 1.0
):
    """Tạo DLT source; resource mặc định: transfers."""
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)

    fdict = parse_filters(filters) if isinstance(filters, str) else (filters or {})

    @dlt.resource(name="transfers")
    def transfers():
        # DLT resource sync → gọi async core bằng asyncio.run
        import asyncio
        data = asyncio.run(async_fetch_dateperiod(
            endpoint, start, end,
            filters=fdict, fields=fields, split_by_day=split_by_day,
            page_size=page_size, day_workers=day_workers,
            req_per_sec=req_per_sec, http2=http2, timeout_s=timeout_s,
            debug=debug, force_segmented_paging=force_segmented_paging,
            segment_safety_ratio=segment_safety_ratio,
            segment_min_seconds=segment_min_seconds
        ))
        for row in data:
            yield row

    return (transfers,)
