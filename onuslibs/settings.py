# -*- coding: utf-8 -*-
import os

class OnusSettings:
    """
    Thiết lập runtime cho OnusLibs (KHÔNG chứa token).
    Token được quản lý hoàn toàn bởi onuslibs.security.build_headers().
    """
    def __init__(self) -> None:
        # Nhận cả tên biến cũ & mới cho base URL
        self.base_url = os.getenv("ONUSLIBS_BASE_URL", os.getenv("ONUS_BASE_URL", "")).strip()

        # Tham số runtime
        self.page_size = int(os.getenv("ONUSLIBS_PAGE_SIZE", "10000"))
        self.req_per_sec = float(os.getenv("ONUSLIBS_REQ_PER_SEC", "3.0"))
        self.http2 = os.getenv("ONUSLIBS_HTTP2", "true").lower() == "true"
        self.request_timeout_s = float(os.getenv("ONUSLIBS_TIMEOUT_S", "30"))

        if not self.base_url:
            raise RuntimeError("Thiếu base URL. Set ONUSLIBS_BASE_URL hoặc ONUS_BASE_URL")

    def __repr__(self) -> str:
        return f"OnusSettings(base_url={self.base_url!r})"
