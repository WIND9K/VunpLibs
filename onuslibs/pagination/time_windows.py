# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

MS  = timedelta(milliseconds=1)
SEC = timedelta(seconds=1)

def day_slices(ws: datetime, we: datetime) -> List[Tuple[datetime, datetime]]:
    out: List[Tuple[datetime, datetime]] = []
    tz = ws.tzinfo or timezone.utc
    cur = datetime(ws.year, ws.month, ws.day, 0, 0, 0, tzinfo=tz)
    while cur <= we:
        day_start = max(cur, ws)
        next_day  = cur + timedelta(days=1)
        day_end   = min(we, next_day - MS)
        if day_start <= day_end:
            out.append((day_start, day_end))
        cur = next_day
    return out
