from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import os, json

@dataclass
class Paging:
    """
    Tất cả tham số phân trang đều do ỨNG DỤNG truyền vào qua ConfigLoader.load(overrides=...).
    Các giá trị dưới đây chỉ là default an toàn.
    """
    # Các khoá tên param để truyền lên server (nếu server dùng tên khác, app override ở đây)
    page_param: str = "page"
    per_page_param: str = "pageSize"

    # Kích thước mỗi lần lấy dữ liệu (app phải set theo giới hạn backend, vd: 20000)
    page_size: int = 20000

    # Trang bắt đầu nếu backend có ý nghĩa cho field 'page' (Cyclos + datePeriod thường luôn page=0)
    start_page: int = 0

@dataclass
class Limits:
    """
    Giới hạn tốc độ gọi; app có thể truyền giá trị mong muốn.
    """
    req_per_sec: float = 3.0
    max_items: Optional[int] = None
    max_pages: Optional[int] = None

@dataclass
class Config:
    """
    Cấu hình gọi API. Ứng dụng nên override:
      - endpoint, method, params
      - paging.page_size (vd 20000)
      - limits.req_per_sec (vd 3)
      - strategy.epsilon_seconds (vd 1)
      - strategy.probe_page_size (vd 1)
      - strategy.autosplit_overflow (True/False)
    """
    endpoint: str = ""
    method: str = "GET"
    params: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    paging: Paging = field(default_factory=Paging)
    limits: Limits = field(default_factory=Limits)

    # Strategy giữ dạng dict để app truyền tuỳ ý:
    #  - epsilon_seconds: int (default 1)
    #  - probe_page_size: int (default 1) — chỉ dùng cho PROBE
    #  - autosplit_overflow: bool (default False) — nếu True có thể phát sinh thêm req khi 1 cửa sổ > pageSize
    #  - num_windows: Optional[int] — nếu app muốn ép số cửa sổ (sẽ bỏ qua ceil(total/pageSize))
    strategy: Dict[str, Any] = field(default_factory=dict)

class ConfigLoader:
    @staticmethod
    def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(a or {})
        for k, v in (b or {}).items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = ConfigLoader._merge(out[k], v)
            else:
                out[k] = v
        return out

    @staticmethod
    def _load_file(path: Optional[str]) -> Dict[str, Any]:
        if not path:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _load_env(prefix: str = "ONUSLIBS_") -> Dict[str, Any]:
        """Cho phép override đơn giản bằng ENV (tuỳ chọn)."""
        out: Dict[str, Any] = {}
        ps = os.getenv(prefix + "PAGE_SIZE")
        if ps and ps.isdigit():
            out.setdefault("paging", {})["page_size"] = int(ps)
        rps = os.getenv(prefix + "RPS")
        if rps:
            try:
                out.setdefault("limits", {})["req_per_sec"] = float(rps)
            except ValueError:
                pass
        eps = os.getenv(prefix + "EPSILON")
        if eps and eps.isdigit():
            out.setdefault("strategy", {})["epsilon_seconds"] = int(eps)
        return out

    @staticmethod
    def _to_dc(cfg: Dict[str, Any]) -> Config:
        # paging
        pg = cfg.get("paging", {}) or {}
        paging = Paging(
            page_param=str(pg.get("page_param", "page")),
            per_page_param=str(pg.get("per_page_param", "pageSize")),
            page_size=int(pg.get("page_size", 20000)),
            start_page=int(pg.get("start_page", 0)),
        )
        # limits
        lm = cfg.get("limits", {}) or {}
        limits = Limits(
            req_per_sec=float(lm.get("req_per_sec", 3.0)),
            max_items=lm.get("max_items"),
            max_pages=lm.get("max_pages"),
        )
        # strategy (dict tự do)
        strategy = dict(cfg.get("strategy", {}) or {})
        return Config(
            endpoint=str(cfg.get("endpoint", "")),
            method=str(cfg.get("method", "GET")),
            params=dict(cfg.get("params", {}) or {}),
            headers=dict(cfg.get("headers", {}) or {}),
            paging=paging,
            limits=limits,
            strategy=strategy,
        )

    @staticmethod
    def load(*, file_path: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None, env_prefix: str = "ONUSLIBS_") -> Config:
        base = ConfigLoader._load_file(file_path)
        env = ConfigLoader._load_env(env_prefix)
        merged = ConfigLoader._merge(base, env)
        if overrides:
            merged = ConfigLoader._merge(merged, overrides)
        return ConfigLoader._to_dc(merged)
