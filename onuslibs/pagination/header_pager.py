from __future__ import annotations
from typing import Any, Dict, Iterable, List

__all__ = ["HeaderPager"]

def _parse_bool(v: str | None) -> bool:
    """
    Chuẩn hoá chuỗi bool từ HTTP headers.
    Hỗ trợ nhiều biến thể: "true"/"1"/"yes"/"on" (không phân biệt hoa/thường).
    """
    if v is None:
        return False
    return str(v).strip().lower() in ("true", "1", "yes", "on")

class HeaderPager:
    """
    HeaderPager — phân trang theo header Cyclos

    Ý tưởng
    -------
    - API trả về header `X-Has-Next-Page` để cho biết còn trang tiếp theo không.
    - Mỗi lần gọi, ta gắn `page` (bắt đầu 0) và `pageSize` vào params.
    - Dừng khi:
      1) `X-Has-Next-Page` != true, **hoặc**
      2) batch rỗng (len(items) == 0).

    Dữ liệu trả về
    --------------
    - Hỗ trợ 3 dạng payload:
      - list thuần: `[{...}, {...}]`
      - dict có `pageItems`: `{"pageItems": [...]}`
      - dict có `items`: `{"items": [...]}`

    Ví dụ
    -----
    ```python
    pager = HeaderPager(http_client, "/api/users", params={"statuses":"active"}, headers=build_headers(), page_size=1000)
    for batch in pager.fetch_all():
        # xử lý batch (list[dict])
        ...
    ```
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
        self.page_size: int = int(page_size) if page_size else 10000

    @staticmethod
    def _extract_items(payload: Any) -> List[Dict[str, Any]]:
        """
        Chuẩn hóa dữ liệu trả về thành list[dict].
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

        while True:
            p = dict(self.params)
            p["page"] = page
            p["pageSize"] = self.page_size

            resp = self.http_client.get(self.endpoint, params=p, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            items = self._extract_items(data)

            # Chuẩn hoá header → chữ thường 1 lần
            headers_l = {k.lower(): v for k, v in resp.headers.items()}
            has_next = _parse_bool(headers_l.get("x-has-next-page"))

            # Dừng nếu hết trang hoặc batch rỗng (không yield rỗng)
            if not items or not has_next:
                if items:    # trang cuối vẫn có dữ liệu
                    yield items
                break

            yield items
            page += 1

