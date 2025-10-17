from __future__ import annotations
from typing import Any, Dict, Tuple, Callable

def make_client_request(onus_client) -> Callable[[str, str, Dict[str, Any]], Tuple[int, Any, Dict[str, str]]]:
    """Adapter: (method, endpoint, params) -> (status, data, headers)"""
    def _client_request(method: str, endpoint: str, params: Dict[str, Any]):
        return onus_client.make_request(method=method, path=endpoint, params=dict(params or {}))
    return _client_request

def wrap_dateperiod(client_request: Callable[[str, str, Dict[str, Any]], Tuple[int, Any, Dict[str, str]]]):
    """
    Gộp 'from' + 'to' → 'datePeriod=a,b' nếu có.
    Không loại bỏ các tham số khác (page, pageSize, chargedBack, transferFilters, ...).
    """
    def _wrapped(method: str, endpoint: str, params: Dict[str, Any]):
        q = dict(params or {})
        f = q.pop("from", None)
        t = q.pop("to", None)
        if f and t and "datePeriod" not in q:
            q["datePeriod"] = f"{f},{t}"
        return client_request(method, endpoint, q)
    return _wrapped
