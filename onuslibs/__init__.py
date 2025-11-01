# onuslibs/__init__.py  (thêm ở đầu file)
# --- Legacy import shim: map onuslibs.secrets.* -> onuslibs.security ---
import sys as _sys


# Re-export API ngắn gọn
from .security import build_headers, get_access_client_token  # noqa: F401
__all__ = ["build_headers", "get_access_client_token"]
# ----------------------------------------------------------------------

# -*- coding: utf-8 -*-

# Public Security API
from .security import build_headers, get_access_client_token

# Public Paging v2 API
from .pagination.segmented import fetch_all

__all__ = ["build_headers", "get_access_client_token", "fetch_all"]
