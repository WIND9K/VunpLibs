# -*- coding: utf-8 -*-
from typing import Dict, List, Any
from urllib.parse import parse_qsl, urlparse, urljoin
from datetime import datetime, timezone

def parse_filters(qs: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not qs:
        return out
    for k, v in parse_qsl(qs, keep_blank_values=True):
        k = (k or "").strip()
        v = (v or "").strip()
        if k:
            out[k] = v
    if "statuses" in out and isinstance(out["statuses"], str):
        out["statuses"] = out["statuses"].replace("\n", "").replace(" ", "")
    return out

def extract_items(obj: Any) -> List[dict]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        it = obj.get("items") or obj.get("data") or obj.get("rows") or obj.get("results") or []
        return it if isinstance(it, list) else []
    return []

def get_in(d: dict, path: str, default=None):
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur

def iso_ms(dt: datetime) -> str:
    s = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return s.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

def url_join_safe(base_url: str, endpoint: str) -> str:
    base = (base_url or "").strip()
    ep = (endpoint or "").strip()
    if not base:
        raise ValueError("Base URL trống")
    if ep.lower().startswith("http://") or ep.lower().startswith("https://"):
        url = ep
    else:
        url = urljoin(base.rstrip("/") + "/", ep.lstrip("/"))
    pu = urlparse(url)
    if not pu.scheme or not pu.netloc:
        raise ValueError(f"URL không hợp lệ: {url}")
    return url
