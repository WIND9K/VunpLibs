"""
tests/config_api.py

Cấu hình API dùng cho test thực tế OnusLibs.
- Chuẩn hoá endpoint, fields, statuses, page/pageSize.
- Cung cấp hàm build_params() để tái sử dụng giữa các script test.
"""

from __future__ import annotations
from typing import Dict

# Endpoint cố định cho bài test người dùng
ENDPOINT: str = "/api/users"

# Fields chuẩn (đã loại trùng 'name')
FIELDS_DEFAULT: str = (
    "id,name,email,"
    "customValues.date_of_birth,customValues.gender,"
    "group.name,customValues.vip_level,customValues.listed,"
    "address.city,customValues.document_type"
)

# statuses chuẩn: không có khoảng trắng
STATUSES: str = "active,blocked,disabled"

# Tham số phân trang mặc định khi gọi one-shot
DEFAULT_PAGE: int = 0
DEFAULT_PAGE_SIZE: int = 1000

def build_params(
    user_id: str | int,
    *,
    fields: str | None = None,
    include_group: bool = True,
    page: int | None = DEFAULT_PAGE,
    page_size: int | None = DEFAULT_PAGE_SIZE,
    statuses: str = STATUSES,
) -> Dict[str, str | int]:
    """Trả về dict params để gọi /api/users.
    - Nếu page/page_size = None → không chèn vào params (dùng khi paginate=True).
    - `fields`: nếu None sẽ dùng FIELDS_DEFAULT.
    - `user_id`: có thể truyền int/str, luôn cast thành str khi trả về.
    """
    f = (fields or FIELDS_DEFAULT).strip()
    s = statuses.replace(" ", "")  # loại bỏ khoảng trắng thừa nếu có

    params: Dict[str, str | int] = {
        "includeGroup": "true" if include_group else "false",
        "usersToInclude": str(user_id),
        "statuses": s,
        "fields": f,
    }
    if page is not None:
        params["page"] = int(page)
    if page_size is not None:
        params["pageSize"] = int(page_size)
    return params

def build_url(base_url: str) -> str:
    """Ghép base_url + endpoint thành URL tuyệt đối."""
    return base_url.rstrip("/") + ENDPOINT

__all__ = [
    "ENDPOINT",
    "FIELDS_DEFAULT",
    "STATUSES",
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "build_params",
    "build_url",
]
