from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional
from math import ceil

__all__ = ["HeaderPager"]

def _parse_bool(v: str | None) -> bool:
    """
    Chuẩn hoá chuỗi bool từ HTTP headers.
    Hỗ trợ: "true"/"1"/"yes"/"on" (không phân biệt hoa/thường).
    """
    if v is None:
        return False
    return str(v).strip().lower() in ("true", "1", "yes", "on")

def _parse_int(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except Exception:
        return None

class HeaderPager:
    """
    HeaderPager — phân trang theo header Cyclos.

    Dừng khi:
      - X-Has-Next-Page != true, HOẶC
      - batch rỗng, HOẶC
      - đạt trang cuối suy ra từ X-Page-Count / X-Total-Count, HOẶC
      - server trả 422/400/404 cho page > 0 (coi như hết trang).
    """

    def __init__(
        self,
        http_client: Any,
        endpoint: str,
        params: Dict[str, Any] | None,
        headers: Dict[str, str] | None,
        page_size: int,
    ) -> None:
        self.http_client = http_client
        self.endpoint = endpoint
        self.params: Dict[str, Any] = dict(params or {})
        self.headers: Dict[str, str] = dict(headers or {})
        ps = int(page_size) if page_size else 10000
        if ps < 1:
            raise ValueError("page_size must be >= 1")
        self.page_size: int = ps

    @staticmethod
    def _extract_items(payload: Any) -> List[Dict[str, Any]]:
        """
        Chuẩn hoá dữ liệu trả về thành list[dict].
        Ưu tiên: list -> pageItems -> items -> []
        """
        if isinstance(payload, list):
            return list(payload)
        if isinstance(payload, dict):
            if isinstance(payload.get("pageItems"), list):
                return list(payload["pageItems"])
            if isinstance(payload.get("items"), list):
                return list(payload["items"])
        return []

    def fetch_all(self) -> Iterable[List[Dict[str, Any]]]:
        """
        Sinh lần lượt từng mẻ (batch) dữ liệu theo trang.
        Không giữ state ngoài `page`; caller chịu trách nhiệm gom kết quả nếu cần.
        """
        page = int(self.params.get("page", 0) or 0)
        last_page_idx: Optional[int] = None  # 0-based (nếu suy ra được)

        while True:
            p = dict(self.params)
            p["page"] = page
            p["pageSize"] = self.page_size

            try:
                resp = self.http_client.get(self.endpoint, params=p, headers=self.headers)
                resp.raise_for_status()
            except Exception as e:
                # Graceful-stop khi out-of-range page (422/400/404) ở page > 0
                try:
                    from httpx import HTTPStatusError  # lazy import để tránh hard dep
                except Exception:
                    HTTPStatusError = tuple()  # type: ignore
                if isinstance(e, HTTPStatusError):  # type: ignore
                    code = e.response.status_code  # type: ignore
                    if page > 0 and code in (422, 400, 404):
                        break
                raise

            # Chuẩn hoá header → chữ thường 1 lần
            headers_l = {k.lower(): v for k, v in resp.headers.items()}

            # Suy ra trang cuối nếu có thể (ưu tiên X-Page-Count, sau đó X-Total-Count)
            if last_page_idx is None:
                pc = _parse_int(headers_l.get("x-page-count"))
                if pc and pc > 0:
                    last_page_idx = pc - 1  # 1-based -> 0-based
                else:
                    tc = _parse_int(headers_l.get("x-total-count"))
                    if tc is not None and self.page_size > 0:
                        last_page_idx = max(0, ceil(tc / self.page_size) - 1) if tc > 0 else 0

            data = resp.json()
            items = self._extract_items(data)

            # Không yield rỗng
            if not items:
                break

            yield items

            # Nếu header báo hết → dừng
            has_next = _parse_bool(headers_l.get("x-has-next-page"))
            if has_next is False:
                break

            # Nếu đã biết trang cuối → dừng khi đạt
            if last_page_idx is not None and page >= last_page_idx:
                break

            page += 1
