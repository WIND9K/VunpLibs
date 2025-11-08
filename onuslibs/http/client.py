# ===========================
# onuslibs/http/client.py
# HTTP Client: HTTP/2 (nếu có h2), timeout, rate-limit, retry 429/5xx (backoff mũ nhỏ)
# ===========================

from __future__ import annotations
from typing import Optional, Dict, Any, Callable
import time, random
import threading
from email.utils import parsedate_to_datetime

import httpx

from ..config.settings import OnusSettings

# --- helper: kiểm tra có hỗ trợ HTTP/2 (cần package 'h2') ---
def _http2_supported() -> bool:
    try:
        import h2  # noqa: F401
        return True
    except Exception:
        return False

# --- helper: sleep (có thể monkeypatch trong test) ---
def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)

class RateLimiter:
    """
    Limiter đơn giản, thread-safe, giới hạn ~req_per_sec cho toàn bộ luồng dùng chung instance.
    Chiến lược: spacing cố định (interval = 1 / rps). Mỗi acquire() sẽ chờ nếu "quá sớm".
    """
    def __init__(self, req_per_sec: float):
        self.interval = 0.0 if (req_per_sec is None or req_per_sec <= 0) else 1.0 / float(req_per_sec)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_allowed - now)
            base = max(now, self._next_allowed)
            self._next_allowed = base + self.interval
        if wait > 0:
            _sleep(wait)

class HttpClient:
    """
    HTTP client dựa trên httpx.Client với:
    - HTTP/2 khi có 'h2' (ngược lại tự downgrade về HTTP/1.1).
    - Timeout cấu hình được.
    - Rate-limit theo req_per_sec (spacing cố định).
    - Retry 429/5xx với backoff mũ nhỏ + jitter; tôn trọng Retry-After nếu có.
    """
    def __init__(
        self,
        settings: Optional[OnusSettings] = None,
        *,
        max_retries: int = 3,
        backoff_base: float = 0.25,
        backoff_cap: float = 5.0,
        jitter_fn: Optional[Callable[[float, float], float]] = None,
        transport: Optional[httpx.BaseTransport] = None,
        headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self.settings = settings or OnusSettings()
        rps = float(getattr(self.settings, "req_per_sec", 0.0) or 0.0)
        timeout_s = float(getattr(self.settings, "timeout_s", 60.0) or 60.0)
        verify_ssl = bool(getattr(self.settings, "verify_ssl", True))
        http2_enabled = bool(getattr(self.settings, "http2", True)) and _http2_supported()

        self._limiter = RateLimiter(rps)
        self.max_retries = max(0, int(max_retries))
        self.backoff_base = float(backoff_base)
        self.backoff_cap = float(backoff_cap)
        self.jitter_fn = jitter_fn or (lambda a, b: random.uniform(a, b))

        default_headers = {
            "User-Agent": user_agent or getattr(self.settings, "user_agent", "OnusLibs/3 HTTP"),
        }
        if headers:
            default_headers.update(headers)

        # Chuẩn bị kwargs cho httpx.Client
        client_kwargs = dict(
            http2=http2_enabled,
            timeout=timeout_s,
            verify=verify_ssl,
            headers=default_headers,
            transport=transport,
        )

        # Tương thích nhiều phiên bản httpx: chỉ truyền proxies khi được hỗ trợ
        proxies = getattr(self.settings, "proxy", None) or None  # httpx vẫn có thể lấy proxy từ ENV nếu None
        try:
            if proxies is not None:
                self._client = httpx.Client(**client_kwargs, proxies=proxies)
            else:
                self._client = httpx.Client(**client_kwargs)
        except TypeError:
            # Phiên bản httpx không nhận tham số 'proxies' -> bỏ qua proxies
            self._client = httpx.Client(**client_kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def _join(self, path: str) -> str:
        base = (getattr(self.settings, "base_url", "") or "").rstrip("/")
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not base:
            raise ValueError("base_url is empty; set ONUSLIBS_BASE_URL")
        return base + path if path.startswith("/") else base + "/" + path

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or (500 <= status_code <= 599)

    def _compute_retry_after(self, response: httpx.Response) -> Optional[float]:
        ra = response.headers.get("Retry-After")
        if not ra:
            return None
        try:  # numeric seconds
            secs = float(ra.strip())
            if secs >= 0:
                return secs
        except ValueError:
            pass
        try:  # HTTP-date
            dt = parsedate_to_datetime(ra)
            delta = dt.timestamp() - time.time()
            return max(0.0, delta)
        except Exception:
            return None

    def _backoff_delay(self, attempt: int) -> float:
        base = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        # thêm jitter nhẹ để tránh thác lũ
        return min(self.backoff_cap, base + self.jitter_fn(0.0, self.backoff_base / 4.0))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        data: Any = None,
    ) -> httpx.Response:
        url = self._join(path)
        last_err: Optional[BaseException] = None
        last_response: Optional[httpx.Response] = None

        for attempt in range(self.max_retries + 1):
            self._limiter.acquire()
            try:
                resp = self._client.request(method, url, params=params, headers=headers, json=json, data=data)
            except httpx.RequestError as exc:
                last_err = exc
                if attempt < self.max_retries:
                    _sleep(self._backoff_delay(attempt))
                    continue
                raise

            status = resp.status_code
            if 200 <= status < 400:
                return resp

            if self._is_retryable_status(status):
                if attempt < self.max_retries:
                    ra = self._compute_retry_after(resp)
                    delay = ra if ra is not None else self._backoff_delay(attempt)
                    _sleep(delay)
                    last_response = resp
                    continue
                resp.raise_for_status()

            resp.raise_for_status()

        if last_err is not None:
            raise last_err
        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError("HttpClient._request: unexpected fallthrough")

    def get(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        return self._request("GET", path, params=params, headers=headers)

    def post(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        data: Any = None,
    ) -> httpx.Response:
        return self._request("POST", path, params=params, headers=headers, json=json, data=data)

    def put(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        data: Any = None,
    ) -> httpx.Response:
        return self._request("PUT", path, params=params, headers=headers, json=json, data=data)

    def delete(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        return self._request("DELETE", path, params=params, headers=headers)
