# -*- coding: utf-8 -*-
from typing import Dict, List, Iterator
import time
import httpx
from .settings import OnusSettings
from .http_client import build_headers
from .utils import url_join_safe, parse_filters, extract_items

def users_by_ids(
    ids: List[str], *, endpoint: str = "/api/users", id_param: str = "usersToInclude",
    fields: List[str] | str = None, page_size: int | None = None,
    timeout_s: float | None = None, http2: bool | None = None
) -> List[dict]:
    s = OnusSettings()
    url = url_join_safe(s.base_url, endpoint)
    headers = build_headers(s)
    if page_size is None: page_size = s.page_size
    if timeout_s is None: timeout_s = s.request_timeout_s
    if http2 is None: http2 = s.http2

    params: Dict[str, str] = {"page": "0", "pageSize": str(page_size)}
    if isinstance(fields, list) and fields:
        params["fields"] = ",".join(fields)
    elif isinstance(fields, str) and fields.strip():
        params["fields"] = fields.strip()
    params[id_param] = ",".join([str(x).strip() for x in ids if str(x).strip()])

    with httpx.Client(http2=http2, timeout=timeout_s) as client:
        r = client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return extract_items(r.json())

def list_users(
    *, endpoint: str = "/api/users", filters: str | Dict[str, str] = "",
    fields: List[str] | str = None, page_size: int | None = None,
    timeout_s: float | None = None, http2: bool | None = None, req_per_sec: float = 0.0,
    max_rows: int = 0
) -> Iterator[dict]:
    s = OnusSettings()
    url = url_join_safe(s.base_url, endpoint)
    headers = build_headers(s)
    if page_size is None: page_size = s.page_size
    if timeout_s is None: timeout_s = s.request_timeout_s
    if http2 is None: http2 = s.http2

    params: Dict[str, str] = {"page": "0", "pageSize": str(page_size)}
    fdict = parse_filters(filters) if isinstance(filters, str) else (filters or {})
    params.update(fdict)
    if isinstance(fields, list) and fields:
        params["fields"] = ",".join(fields)
    elif isinstance(fields, str) and fields.strip():
        params["fields"] = fields.strip()

    seen = 0
    with httpx.Client(http2=http2, timeout=timeout_s) as client:
        while True:
            r = client.get(url, headers=headers, params=params)
            r.raise_for_status()
            for it in extract_items(r.json()):
                yield it
                seen += 1
                if max_rows > 0 and seen >= max_rows:
                    return
            hdr = {k.lower(): v for k, v in r.headers.items()}
            has_next = hdr.get("x-has-next-page", "false").lower() == "true"
            if not has_next:
                return
            params["page"] = str(int(params["page"]) + 1)
            if req_per_sec > 0:
                time.sleep(1.0 / req_per_sec)
