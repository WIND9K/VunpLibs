# onuslibs/api.py
from __future__ import annotations
import time
import logging
from typing import Any, Dict, Optional
import requests
from .compat_env import get_token

logger = logging.getLogger("onuslibs.api")

class HttpError(RuntimeError):
    """Raised when HTTP status is not ok (>=400)."""

def call_api(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
    retries: int = 2,
    backoff_sec: float = 1.0,
    token: Optional[str] = None,
) -> Any:
    """Helper đơn lẻ; khuyến nghị dùng OnusLibsClient thay vì module này."""
    tok = token or get_token()
    if not tok:
        raise RuntimeError("Missing Access-Client-Token. Set ONUSLIBS_TOKEN/ACCESS_CLIENT_TOKEN in ENV/.env")
    h = {"Access-Client-Token": tok, **(headers or {})}
    last_err: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, headers=h, params=params, json=json, timeout=timeout)
            if r.status_code >= 400:
                raise HttpError(f"HTTP {r.status_code}: {r.text[:200]}")
            try:
                return r.json()
            except ValueError:
                return r.text
        except Exception as e:
            last_err = e
            if attempt >= retries:
                break
            time.sleep(backoff_sec * (attempt + 1))
    raise last_err or RuntimeError("Unknown request error")
