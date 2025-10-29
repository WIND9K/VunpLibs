# -*- coding: utf-8 -*-
from typing import Dict
import httpx
from .settings import OnusSettings
from .secrets.manager import get_access_client_token 

def build_headers(settings: OnusSettings) -> Dict[str, str]:
    token = get_access_client_token() 
    return {
        "Accept": "application/json",
        "Access-Client-Token": token,
        # thêm header khác nếu API yêu cầu
    }

def make_async_client(http2: bool, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(http2=http2, timeout=timeout_s)
