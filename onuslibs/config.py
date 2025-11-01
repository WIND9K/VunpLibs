# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List

try:
    import tomllib  # Python 3.11+
except Exception:
    import tomli as tomllib  # Python <=3.10


# -------------------------
# Đường dẫn cấu hình mặc định (v2)
# -------------------------
DEFAULT_CFG_PATHS: List[Path] = [
    Path(os.getenv("ONUSLIBS_CONFIG")) if os.getenv("ONUSLIBS_CONFIG") else None,
    Path("onuslibs/config/onuslibs.toml"),
    Path("config/onuslibs.toml"),
    Path("onuslibs/config/onuslibs.json"),
    Path("config/onuslibs.json"),
]
DEFAULT_CFG_PATHS = [p for p in DEFAULT_CFG_PATHS if p]


# -------------------------
# Tiện ích đọc file & merge
# -------------------------
def _read_cfg_file(path: Path) -> Dict[str, Any]:
    """Đọc TOML/JSON và trả về dict."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {path}")
    ext = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if ext == ".toml":
        return tomllib.loads(text)
    if ext == ".json":
        return json.loads(text)
    raise ValueError(f"Không hỗ trợ định dạng: {ext}")

def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Gộp 2 dict đệ quy, src ghi đè dst."""
    for k, v in (src or {}).items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


# -------------------------
# ENV secrets (v2: chỉ BASE_URL/TOKEN)
# -------------------------
@dataclass
class OnusSettings:
    """Thiết lập cốt lõi cho onuslibs v2. ENV chỉ dùng cho secrets."""
    base_url: str = field(default_factory=lambda: os.getenv("ONUSLIBS_BASE_URL", ""))
    access_client_token: str = field(default="", repr=False, compare=False)  # deprecated: use onuslibs.security.build_headers()

    # Các limit/tuỳ chọn runtime (có thể dùng khi build client trực tiếp)
    http2: bool = True
    page_size: int = 10000
    request_timeout_s: float = 20.0
    req_per_sec: float = 3.0
    combine_dateperiod: bool = True  # khi endpoint có datePeriod

    def __post_init__(self):
        if not self.base_url or not self.access_client_token:
            raise RuntimeError("Thiếu ENV: ONUSLIBS_BASE_URL / ONUSLIBS_ACCESS_CLIENT_TOKEN")


def build_headers(s: OnusSettings) -> Dict[str, str]:
    """Headers chuẩn cho các request API."""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Access-Client-Token": s.access_client_token,
    }


def merge_settings(settings: Optional[OnusSettings], **kwargs) -> OnusSettings:
    """
    Tạo OnusSettings từ:
      - settings (nếu có) hoặc ENV (nếu None)
      - rồi ghi đè bằng kwargs (vd: base_url=..., access_client_token=...)
    """
    base = settings if settings is not None else OnusSettings()
    # copy nông, rồi ghi đè các khóa hợp lệ (nếu truyền vào)
    s = OnusSettings(
        base_url=kwargs.get("base_url", base.base_url),
        access_client_token=kwargs.get("access_client_token", base.access_client_token),
        http2=kwargs.get("http2", base.http2),
        page_size=kwargs.get("page_size", base.page_size),
        request_timeout_s=kwargs.get("request_timeout_s", base.request_timeout_s),
        req_per_sec=kwargs.get("req_per_sec", base.req_per_sec),
        combine_dateperiod=kwargs.get("combine_dateperiod", base.combine_dateperiod),
    )
    return s


# -------------------------
# Loader nhận cấu hình TỪ DỰ ÁN + cho phép GHI ĐÈ
# -------------------------
def load_project_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Đọc file cấu hình dự án (TOML/JSON) theo chuẩn v2:
      - Ưu tiên đường dẫn truyền vào.
      - Nếu không có, tìm ở các vị trí mặc định (onuslibs/config/onuslibs.toml, ...).
    Trả về dict (thường gồm 2 khối: 'run' và 'limits').
    """
    cfg: Dict[str, Any] = {}
    candidates = [Path(path)] if path else DEFAULT_CFG_PATHS
    for p in candidates:
        if p and p.is_file():
            cfg = _read_cfg_file(p)
            break
    if not cfg:
        raise FileNotFoundError("Không tìm thấy file cấu hình onuslibs (TOML/JSON).")
    return cfg


def apply_overrides(cfg: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ghi đè cấu hình bằng dict overrides do dự án truyền lên.
    - Chỉ merge đệ quy, không động chạm ENV (ENV chỉ cho BASE_URL/TOKEN).
    - override ví dụ:
        {"run": {"endpoint": "/api/users", "fields": ["id","username"]},
         "limits": {"page_size": 20000, "req_per_sec": 2.0}}
    """
    if not overrides:
        return cfg
    return _deep_merge(cfg, overrides)


# -------------------------
# Tiện ích chuẩn hoá dữ liệu đầu vào
# -------------------------
def parse_filters(qs: Optional[str]) -> Dict[str, str]:
    """Chuyển chuỗi query 'a=b&c=d' thành dict; giữ nguyên giá trị để gửi lên API."""
    out: Dict[str, str] = {}
    if not qs:
        return out
    for pair in qs.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    # dọn trường phổ biến
    if "statuses" in out and isinstance(out["statuses"], str):
        out["statuses"] = out["statuses"].replace("\n", "").replace(" ", "")
    return out


def fields_to_csv(fields: Any) -> Optional[str]:
    """fields có thể là list hoặc string CSV; trả về CSV chuẩn hoá hoặc None nếu trống."""
    if isinstance(fields, list) and fields:
        return ",".join(str(x).strip() for x in fields if str(x).strip())
    if isinstance(fields, str) and fields.strip():
        return fields.strip()
    return None


# -------------------------
# API chính cho dự án gọi
# -------------------------
def resolve_config(cfg_path: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Đọc cấu hình từ file (TOML/JSON) và cho phép ghi đè bằng 'overrides'.
    Trả về dict hợp nhất, không đụng tới ENV (ENV chỉ xử lý ở OnusSettings).
    """
    base = load_project_config(cfg_path)
    merged = apply_overrides(base, overrides)
    return merged
