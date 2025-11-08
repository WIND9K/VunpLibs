# onuslibs/unified/api.py
from __future__ import annotations
from typing import Any, Dict, List, Callable, Optional, Sequence   # <-- thêm Sequence
from ..http.client import HttpClient
from ..config.settings import OnusSettings
from ..security.headers import build_headers
from ..pagination.header_pager import HeaderPager

__all__ = ["fetch_json"]

def _normalize_fields(fields: Optional[Sequence[str] | str]) -> Optional[str]:
    """Chấp nhận list/tuple hoặc CSV string -> trả về CSV sạch."""
    if not fields:
        return None
    if isinstance(fields, str):
        parts = [p.strip() for p in fields.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in fields if str(p).strip()]
    return ",".join(parts) if parts else None

def fetch_json(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    fields: Optional[Sequence[str] | str] = None,        # <-- hỗ trợ list/tuple
    page_size: Optional[int] = None,
    paginate: bool = True,
    order_by: Optional[str] = None,
    strict_fields: bool = False,                         # (chưa dùng: no-op)
    unique_key: Optional[str] = None,
    settings: Optional[OnusSettings] = None,
    on_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
) -> List[Dict[str, Any]]:
    settings = settings or OnusSettings()
    client = HttpClient(settings)  # giữ nguyên

    # 1) headers + params
    hdrs: Dict[str, str] = build_headers(settings)
    p: Dict[str, Any] = dict(params or {})
    f = _normalize_fields(fields)
    if f is not None:
        p["fields"] = f
    if order_by:
        p["orderBy"] = order_by

    results: List[Dict[str, Any]] = []
    seen = set() if unique_key else None

    def _consume(batch: List[Dict[str, Any]]):
        """Gom vào results và gọi on_batch với mẻ đã dedupe (nếu cần)."""
        if not batch:
            return
        if seen is None:
            emit = batch
            results.extend(batch)
        else:
            emit: List[Dict[str, Any]] = []
            for it in batch:
                k = it.get(unique_key)  # type: ignore[arg-type]
                if (k is None) or (k not in seen):
                    if k is not None:
                        seen.add(k)
                    results.append(it)
                    emit.append(it)
        if on_batch and emit:
            on_batch(emit)  # <-- chỉ chuyển mẻ đã dedupe cho callback

    if not paginate:
        resp = client.get(endpoint, params=p, headers=hdrs)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else (data.get("pageItems") or data.get("items") or [])
        _consume(items)
        return results

    pager = HeaderPager(client, endpoint, p, hdrs, page_size or settings.page_size)
    for batch in pager.fetch_all():
        _consume(batch)
    return results
