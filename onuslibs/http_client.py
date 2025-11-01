# -*- coding: utf-8 -*-
from typing import Dict, Optional
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt
from onuslibs.security import build_headers

def make_sync_client(http2: bool = True, timeout_s: float = 30.0) -> httpx.Client:
    return httpx.Client(http2=http2, timeout=timeout_s)

def make_async_client(http2: bool = True, timeout_s: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(http2=http2, timeout=timeout_s)

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(5))
def get_json(url: str, params: Optional[dict] = None, timeout: float = 30.0):
    with httpx.Client(http2=True, timeout=timeout) as client:
        r = client.get(url, headers=build_headers(), params=params)
        r.raise_for_status()
        return r.json(), r.headers

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(5))
def post_json(url: str, json_body: dict, timeout: float = 30.0):
    with httpx.Client(http2=True, timeout=timeout) as client:
        r = client.post(url, headers=build_headers(), json=json_body)
        r.raise_for_status()
        return r.json(), r.headers
