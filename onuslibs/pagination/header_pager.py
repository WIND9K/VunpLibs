# onuslibs/pagination/header_pager.py
# =============================================================================
# HeaderPager: Phân trang theo chuẩn header của Cyclos/Wallet
# - Ưu tiên suy ra tổng trang từ X-Page-Count / X-Total-Count
# - Nếu không có, fallback X-Has-Next-Page; nếu vẫn "khó tin", dùng kích thước batch
# - Dừng êm khi server trả 400/404/422 (coi như page vượt phạm vi/hết trang)
# =============================================================================

from __future__ import annotations

from math import ceil                     # dùng để tính số trang từ total/page_size
from typing import Any, Dict, Iterable, List, Optional
from httpx import HTTPStatusError         # để bắt lỗi trạng thái HTTP cấp ứng dụng


__all__ = ["HeaderPager", "header_fetch_all"]


# -----------------------------------------------------------------------------
# Helpers (private)
# -----------------------------------------------------------------------------
def _lower_headers(h: Any) -> Dict[str, str]:
    """
    Chuẩn hoá header về chữ thường để tra cứu khoẻ:
    - httpx.Headers có thể key theo case-insensitive; ta ép về dict[str,str].
    """
    return {str(k).lower(): str(v) for k, v in dict(h).items()}


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """
    Chuẩn hoá payload về list[dict] cho Facade:
    - Server có thể trả: list[...] hoặc { items:[...] } hoặc { pageItems:[...] }.
    - Trường hợp khác -> trả list rỗng.
    """
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("pageItems"), list):
            return list(payload["pageItems"])
        if isinstance(payload.get("items"), list):
            return list(payload["items"])
    return []


# -----------------------------------------------------------------------------
# Core class
# -----------------------------------------------------------------------------
class HeaderPager:
    """
    Trình phân trang tuần tự theo header Cyclos/Wallet.

    Thiết kế:
      - Lấy trang hiện tại -> yield items.
      - Ở trang đầu, cố gắng suy ra tổng số trang:
        + Ưu tiên X-Page-Count; nếu không có, dùng X-Total-Count / page_size.
      - Nếu biết tổng trang -> đi đến trang cuối theo kế hoạch (0..last).
      - Nếu KHÔNG biết tổng trang -> dựa vào X-Has-Next-Page.
        + Nếu header này không đáng tin, fallback kích thước batch: len(items) < page_size -> trang cuối.
      - Khi server trả 400/404/422 ở trang tiếp theo -> dừng êm (không raise).
    """

    def __init__(
        self,
        http_client: Any,                 # Đối tượng HttpClient (Module 3)
        endpoint: str,                    # Ví dụ: "/api/users"
        *,
        params: Optional[Dict[str, Any]] = None,   # params gốc (không ép page/pageSize ở đây)
        headers: Optional[Dict[str, str]] = None,  # headers gốc (Authorization, UA, ...)
        page_size: Optional[int] = None,           # nếu None sẽ dùng mặc định 10000
    ) -> None:
        self.http_client = http_client
        self.endpoint = endpoint
        self.params: Dict[str, Any] = dict(params or {})
        self.headers: Dict[str, str] = dict(headers or {})
        # đảm bảo page_size hợp lệ, tránh 0/âm
        ps = int(page_size or 10000)
        self.page_size: int = ps if ps >= 1 else 10000

    # -------------------------------------------------------------------------
    # API chính: stream từng "batch" (list[dict]) theo thứ tự page tăng dần.
    # -------------------------------------------------------------------------
    def fetch_all(self) -> Iterable[List[Dict[str, Any]]]:
        """
        Yield lần lượt các batch (list[dict]) cho từng trang.
        Không raise cho 400/404/422 ở trang tiếp theo -> dừng êm.
        """

        # Page bắt đầu: tôn trọng self.params.get("page", 0) nếu có
        page = int(self.params.get("page", 0) or 0)

        # Lưu kế hoạch trang cuối nếu suy ra được (index, 0-based)
        last_page_idx: Optional[int] = None

        # Vòng lặp trang
        while True:
            # Ghép params riêng cho lần gọi này:
            # - Không làm bẩn self.params gốc
            # - Ép page & pageSize rõ ràng để server hiểu đúng
            p = dict(self.params)
            p["page"] = page
            p["pageSize"] = self.page_size

            try:
                # Gửi request GET qua HttpClient (đã có limiter, retry, timeout...)
                resp = self.http_client.get(self.endpoint, params=p, headers=self.headers)
                # Nếu status 4xx/5xx -> raise để xét mã cụ thể
                resp.raise_for_status()
            except HTTPStatusError as e:
                # Hết trang/vượt phạm vi: server có thể trả 400/404/422 cho page tiếp theo
                code = e.response.status_code
                if code in (400, 404, 422):
                    break  # dừng êm
                # Mã khác: ném tiếp cho tầng trên xử lý (timeout, 5xx sau retry, ...)
                raise

            # Đọc JSON & bóc items
            data = resp.json()
            items = _extract_items(data)
            # Chuẩn hoá header để dễ tra
            headers = _lower_headers(resp.headers)

            # Ở lượt đầu tiên -> cố gắng suy ra tổng số trang để "đi theo kế hoạch"
            if last_page_idx is None:
                # 1) Ưu tiên X-Page-Count (tổng số trang 1-based)
                page_count = (headers.get("x-page-count") or "").strip()
                if page_count.isdigit():
                    # last index = page_count - 1 (0-based)
                    last_page_idx = max(0, int(page_count) - 1)
                else:
                    # 2) Thử X-Total-Count nếu không có X-Page-Count
                    total_count = (headers.get("x-total-count") or "").strip()
                    if total_count.isdigit() and self.page_size > 0:
                        total = int(total_count)
                        # ceil(total/page_size) - 1 -> last index (0-based); total=0 -> 0
                        last_page_idx = max(0, ceil(total / self.page_size) - 1) if total > 0 else 0
                # Nếu cả hai header không có/không hợp lệ -> last_page_idx vẫn None -> fallback phía dưới

            # Yield batch hiện tại cho Facade (unified.fetch_json)
            yield items

            # Nếu đã biết trang cuối -> dừng khi chạm tới
            if last_page_idx is not None:
                if page >= last_page_idx:
                    break
            else:
                # Fallback 1: dựa header X-Has-Next-Page (true/false)
                has_next = (headers.get("x-has-next-page") or "").lower() == "true"
                if not has_next:
                    # Fallback 2: nếu has_next không đáng tin -> dùng kích thước batch
                    # - Nếu items < page_size => coi như trang cuối
                    if len(items) < self.page_size:
                        break
                    # - Nếu len(items) == page_size mà has_next=false: vẫn "thử" thêm 1 trang
                    #   vòng sau gặp 400/404/422 -> dừng êm (tránh dừng sớm)
                    #   hoặc gặp batch nhỏ hơn -> dừng
                    # => Không break ở đây để "thử thêm" 1 vòng

            # Tăng page để lấy trang kế tiếp
            page += 1


# -----------------------------------------------------------------------------
# Facade-friendly wrapper
# -----------------------------------------------------------------------------
def header_fetch_all(
    http_client: Any,
    endpoint: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    page_size: Optional[int] = None,
) -> Iterable[List[Dict[str, Any]]]:
    """
    Hàm trợ giúp để unified.api.fetch_json(...) có thể tiêm 'pager_func' tuỳ ý.
    Trả về generator yield từng batch (list[dict]) theo thứ tự page tăng dần.
    """
    pager = HeaderPager(
        http_client=http_client,
        endpoint=endpoint,
        params=params,
        headers=headers,
        page_size=page_size,
    )
    return pager.fetch_all()
