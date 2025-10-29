# -*- coding: utf-8 -*-
__all__ = [
    "OnusSettings", "build_headers",
    "source",              # DLT-facing
    "users_by_ids", "list_users",  # no-datePeriod helpers
    "fetch_all"            # core fetch (không DLT)
]

__version__ = "2.0.0"

from .settings import OnusSettings
from .http_client import build_headers
from .dlt_source import source
from .simple import users_by_ids, list_users
from .pagination.segmented import fetch_all
