from __future__ import annotations

"""
OnusLibs v3 — Module 4: Pagination (HeaderPager)

- Dùng header phân trang kiểu Cyclos:
    X-Total-Count, X-Page-Size, X-Current-Page, X-Page-Count, X-Has-Next-Page
- Làm việc với HttpClient (duck-typed: chỉ cần có .get() trả về httpx.Response).
- Không import ngược lại unified -> tránh vòng lặp import.
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional

import httpx

__all__ = ["HeaderPager", "header_fetch_all"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_bool(val: Optional[str]) -> Optional[bool]:
    """
    Chuẩn hóa chuỗi header bool ("true"/"false"/"1"/"0"/...) về bool / None.
    """
    if val is None:
        return None
    s = val.strip().lower()
    if not s:
        return None
    if s in ("true", "1", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "n", "off"):
        return False
    return None


def _parse_int(val: Optional[str]) -> Optional[int]:
    """
    Chuẩn hóa chuỗi header số về int / None.
    """
    if val is None:
        return None
    s = val.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """
    Chuẩn hoá payload JSON về list[dict].

    Backend có thể trả:
      - trực tiếp list[dict]
      - hoặc dict với key "items" / "pageItems" / "data" / "rows"
    """
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        for key in ("items", "pageItems", "data", "rows"):
            v = payload.get(key)
            if isinstance(v, list):
                return list(v)
    return []


# ---------------------------------------------------------------------------
# Core pager
# ---------------------------------------------------------------------------


class HeaderPager:
    """
    Trình phân trang chuẩn Cyclos dựa trên header.

    Tham số:
        http_client : instance HttpClient (hoặc object tương đương) có .get()
        endpoint    : path API, ví dụ "/api/transfers"
        params      : dict params gốc (có thể chứa "page" và "pageSize")
        headers     : headers mặc định đã build (Access-Client-Token, UA,...)
        page_size   : pageSize mong muốn. Nếu None -> dùng params["pageSize"]
        page_param  : tên param số trang, mặc định "page" (0-based)

    Giao ước:
        - Mỗi lần gọi fetch_all() sẽ:
            1) Bắt đầu từ page = params.get(page_param, 0) (0-based)
            2) Gọi GET tuần tự các trang
            3) Yield từng batch (list[dict]) cho tới khi hết trang.
    """

    def __init__(
        self,
        http_client: Any,
        endpoint: str,
        params: Mapping[str, Any],
        headers: Mapping[str, str],
        page_size: Optional[int] = None,
        *,
        page_param: str = "page",
    ) -> None:
        self.http_client = http_client
        self.endpoint = endpoint
        self.params: Dict[str, Any] = dict(params)
        self.headers: Dict[str, str] = dict(headers)
        self.page_param = page_param

        # Nếu truyền page_size -> ưu tiên; nếu không -> lấy từ params nếu có
        explicit = page_size
        if explicit is not None and explicit > 0:
            self.page_size = explicit
        else:
            ps = self.params.get("pageSize")
            self.page_size = int(ps) if isinstance(ps, int) and ps > 0 else None

    # ------------------------------------------------------------------
    def fetch_all(self) -> Iterable[List[Dict[str, Any]]]:
        """
        Yield lần lượt các batch (list[dict]) cho từng trang.

        Chiến lược dừng:
          1) Nếu header X-Page-Count có giá trị > 0:
               - Sau khi đọc 1 response, nếu page+1 >= X-Page-Count -> dừng.
          2) Nếu không có X-Page-Count:
               - Dùng X-Has-Next-Page (nếu có) để quyết định tiếp tục / dừng.
          3) Fallback:
               - Nếu biết page_size, và len(items) < page_size -> dừng.
               - Nếu len(items) == 0 -> dừng.

        Đối với lỗi 4xx/5xx:
          - httpx.HTTPStatusError (400/404/422) trên trang > trang bắt đầu:
                + Nếu header báo vẫn còn trang (X-Page-Count > page+1) -> raise RuntimeError
                + Ngược lại -> coi như hết trang, dừng êm.
          - Các lỗi khác -> propagate (raise).
        """

        # Trang bắt đầu (0-based) nếu params đã set sẵn
        start_page = _parse_int(str(self.params.get(self.page_param, "0"))) or 0
        page = start_page

        # Ghi nhớ tổng số trang nếu backend cung cấp (X-Page-Count: 1-based)
        known_page_count: Optional[int] = None

        while True:
            # Ghép params riêng cho lượt này (không mutate params gốc)
            page_params: Dict[str, Any] = dict(self.params)
            page_params[self.page_param] = page
            if self.page_size:
                page_params["pageSize"] = self.page_size

            try:
                resp = self.http_client.get(
                    self.endpoint, params=page_params, headers=self.headers
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:  # type: ignore[reportGeneralTypeIssues]
                code = e.response.status_code

                # Các lỗi 400/404/422 trên trang > start_page thường là out-of-range
                if code in (400, 404, 422) and page > start_page:
                    # Nếu header đã báo tổng số trang mà vẫn bị lỗi ở giữa -> coi như cấu hình sai
                    if known_page_count is not None and page < known_page_count:
                        raise RuntimeError(
                            "Pagination error: server từ chối page="
                            f"{page} với status={code} trong khi header báo "
                            f"tổng {known_page_count} trang. "
                            "Hãy giảm ONUSLIBS_PAGE_SIZE hoặc thu hẹp date range."
                        ) from e
                    # Không biết tổng trang -> coi như đã vượt giới hạn, dừng êm
                    break

                # Lỗi khác (hoặc lỗi ngay trang đầu) -> propagate cho tầng trên xử lý
                raise

            # Lấy header + payload
            headers = resp.headers or {}
            payload = resp.json()

            items = _extract_items(payload)
            if not items and page == start_page:
                # Trang đầu tiên rỗng -> không có dữ liệu -> dừng luôn
                break

            # Chuẩn hoá header số / bool
            total_count = _parse_int(
                headers.get("X-Total-Count") or headers.get("x-total-count")
            )
            page_size_hdr = _parse_int(
                headers.get("X-Page-Size") or headers.get("x-page-size")
            )
            current_page_hdr = _parse_int(
                headers.get("X-Current-Page") or headers.get("x-current-page")
            )
            if known_page_count is None:
                known_page_count = _parse_int(
                    headers.get("X-Page-Count") or headers.get("x-page-count")
                )
            has_next = _normalize_bool(
                headers.get("X-Has-Next-Page") or headers.get("x-has-next-page")
            )

            # (total_count, current_page_hdr) hiện chưa dùng, nhưng giữ lại để mở rộng / debug
            _ = total_count, current_page_hdr  # tránh cảnh báo "unused"

            # Yield batch hiện tại cho caller
            yield items

            # ---- Quyết định dừng / tiếp tục ----

            # Ưu tiên 1: nếu biết tổng số trang (1-based)
            if known_page_count is not None:
                # page là 0-based, nên nếu page+1 >= known_page_count -> đã ở trang cuối
                if page + 1 >= known_page_count:
                    break
                page += 1
                continue

            # Ưu tiên 2: dựa trên has_next từ header
            if has_next is False:
                break
            if has_next is True:
                page += 1
                continue

            # Ưu tiên 3: fallback theo kích thước batch
            effective_page_size = self.page_size or page_size_hdr
            if effective_page_size is not None and effective_page_size > 0:
                if len(items) < effective_page_size:
                    # Batch nhỏ hơn page_size -> trang cuối
                    break
                # Nếu len == page_size -> thử trang kế tiếp
                page += 1
                continue

            # Nếu đến đây mà không có thông tin gì về page_count / has_next / page_size:
            # - Nếu batch rỗng -> dừng
            # - Nếu không -> vẫn thử trang kế để tránh miss dữ liệu
            if not items:
                break
            page += 1


# ---------------------------------------------------------------------------
# Hàm tiện ích: dùng như pager function truyền vào unified.fetch_json
# ---------------------------------------------------------------------------

def header_fetch_all(
    http_client: Any,
    endpoint: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    page_size: Optional[int] = None,
    page_param: str = "page",
) -> Iterable[List[Dict[str, Any]]]:
    """
    Hàm tiện ích tạo HeaderPager và yield các batch.

    Dùng khi muốn tiêm 1 hàm pager vào unified.fetch_json (pager_func=...)
    hoặc khi muốn dùng trực tiếp thay vì khởi tạo class bằng tay.
    """
    pager = HeaderPager(
        http_client=http_client,
        endpoint=endpoint,
        params=params or {},
        headers=headers or {},
        page_size=page_size,
        page_param=page_param,
    )
    return pager.fetch_all()
