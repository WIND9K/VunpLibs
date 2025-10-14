# onuslibs/api.py
from __future__ import annotations
import time
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple, Callable
import requests

from .client import OnusAuth

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
    auth: Optional[OnusAuth] = None,
) -> Any:
    """Gọi API chung với Access-Client-Token, retry và log.
    
    Args:
        method: "GET" | "POST" | "PUT" | "DELETE".
        url: Endpoint đầy đủ.
        headers: Header bổ sung nếu có.
        params: Query string.
        json: JSON body.
        timeout: Timeout mỗi request (giây).
        retries: Số lần thử lại khi lỗi mạng/5xx.
        backoff_sec: Delay giữa các lần retry.
        auth: Nếu None sẽ tự khởi tạo OnusAuth().

    Returns:
        r.json() nếu là JSON hợp lệ, ngược lại r.text.
    """
    _auth = auth or OnusAuth()
    h = {"Access-Client-Token": _auth.access_client_token, **(headers or {})}
    last_err: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            logger.debug("API %s %s params=%s json=%s", method, url, params, json)
            r = requests.request(method, url, headers=h, params=params, json=json, timeout=timeout)
            if r.status_code >= 400:
                # ghi log ở cấp WARNING để tiện tra soát
                logger.warning("HTTP %s %s -> %s %s", method, url, r.status_code, r.text[:500])
                raise HttpError(f"HTTP {r.status_code}: {r.text[:300]}")
            try:
                return r.json()
            except Exception:
                return r.text
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff_sec * (attempt + 1))
                continue
            logger.error("API error after %s attempts: %s", attempt + 1, e)
            raise

def paginate_get(
    url: str,
    *,
    params: Dict[str, Any],
    page_key: str = "page",
    size_key: str = "pageSize",
    total_header: str = "X-Total-Count",
    page_start: int = 0,
    auth: Optional[OnusAuth] = None,
    timeout: int = 60,
    retries: int = 2,
    backoff_sec: float = 1.0,
) -> Tuple[List[Any], int]:
    """Lấy toàn bộ trang (GET) dựa vào header tổng.
    
    Trả về (all_rows, total_count). Nếu không có header tổng, dừng khi trang rỗng.
    """
    _auth = auth or OnusAuth()
    _params = dict(params)
    _params[page_key] = page_start

    all_rows: List[Any] = []
    total = None

    while True:
        data = call_api(
            "GET", url, params=_params, auth=_auth,
            timeout=timeout, retries=retries, backoff_sec=backoff_sec,
        )
        # data có thể là list hoặc obj; với API VNDC commission thường là list
        rows = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else []
        if not rows:
            break
        all_rows.extend(rows)

        # lấy total từ header bằng 1 request phụ nhẹ (hoặc cho phép caller truyền total nếu có)
        # tip: nếu cần tiết kiệm, có thể sửa call_api để trả kèm response headers
        # Ở đây để đơn giản, gọi trực tiếp requests.head (tuỳ endpoint có cho HEAD không)
        # => Nếu không HEAD được, phương án thay thế: ước lượng bằng len và break khi rỗng.
        # Để thực dụng với VNDC API: thường trả header ngay trong GET.
        # Vì call_api trả body, ta cần phiên bản call_api_raw nếu muốn headers.
        # Tạm thời cho phép dừng khi số hàng < size.
        size = int(_params.get(size_key, 10000))
        if len(rows) < size:
            break

        _params[page_key] += 1

    total = len(all_rows) if total is None else total
    return all_rows, total

# Sugar methods
def get(url: str, **kwargs) -> Any:
    return call_api("GET", url, **kwargs)

def post(url: str, **kwargs) -> Any:
    return call_api("POST", url, **kwargs)

def put(url: str, **kwargs) -> Any:
    return call_api("PUT", url, **kwargs)

def delete(url: str, **kwargs) -> Any:
    return call_api("DELETE", url, **kwargs)
