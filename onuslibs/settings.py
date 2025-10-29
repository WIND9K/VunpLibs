# -*- coding: utf-8 -*-
import os

class OnusSettings:
    """Đọc ENV mặc định cho OnusLibs (không mã hoá token ở v2)."""
    def __init__(self) -> None:
        self.base_url = os.getenv("ONUSLIBS_BASE_URL", "").strip()
        self.access_client_token = os.getenv("ONUSLIBS_ACCESS_CLIENT_TOKEN", "").strip()

        # Defaults (có thể bị override bởi TOML hoặc tham số hàm)
        self.page_size = int(os.getenv("ONUSLIBS_PAGE_SIZE", "10000"))
        self.req_per_sec = float(os.getenv("ONUSLIBS_REQ_PER_SEC", "3.0"))
        self.http2 = os.getenv("ONUSLIBS_HTTP2", "true").lower() == "true"
        self.request_timeout_s = float(os.getenv("ONUSLIBS_TIMEOUT_S", "30"))

        if not self.base_url:
            raise RuntimeError("Thiếu ENV ONUSLIBS_BASE_URL")
        if not self.access_client_token:
            raise RuntimeError("Thiếu ENV ONUSLIBS_ACCESS_CLIENT_TOKEN")

    def __repr__(self) -> str:
        return f"OnusSettings(base_url={self.base_url!r}, token='******')"
