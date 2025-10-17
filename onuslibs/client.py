from __future__ import annotations
from typing import Any, Dict, Tuple, Optional
from urllib.parse import urljoin
import requests
from .compat_env import get_token

DEFAULT_TIMEOUT = 60

class OnusLibsClient:
    """
    HTTP client tối giản cho ONUS/Cyclos:
      - Đọc Access-Client-Token từ .env/ENV (ONUSLIBS_TOKEN / ACCESS_CLIENT_TOKEN).
      - Thêm headers mặc định.
      - Trả (status_code, data|text, headers) với fallback parse JSON.
    """
    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None,
    ):
        if not base_url:
            raise ValueError("base_url là bắt buộc và phải được truyền từ config dự án.")
        self.base_url = base_url.strip().replace("\u2026", "").replace("…", "").rstrip("/")
        self.timeout = timeout if timeout and timeout > 0 else DEFAULT_TIMEOUT
        self.session = requests.Session()
        self.token = token or get_token()
        if not self.token:
            raise RuntimeError("Thiếu Access-Client-Token. Hãy đặt ONUSLIBS_TOKEN (hoặc ACCESS_CLIENT_TOKEN) trong ENV/.env.")

        self.default_headers: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Access-Client-Token": self.token,
        }
        if headers:
            self.default_headers.update(headers)

    def make_request(self, method: str, path: str, params: Dict[str, Any] = None) -> Tuple[int, Any, Dict[str, str]]:
        url = urljoin(self.base_url + "/", (path or "").lstrip("/"))
        resp = self.session.request(
            method=method.upper(),
            url=url,
            params=(params or {}),
            headers=self.default_headers,
            timeout=self.timeout,
            allow_redirects=True,
        )
        headers = dict(resp.headers or {})
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return resp.status_code, data, headers
