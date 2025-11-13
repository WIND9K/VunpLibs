from __future__ import annotations
import os
import platform
from dataclasses import dataclass

# ====== Auto .env loader (an toàn, tuỳ chọn) ======
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:  # python-dotenv có thể không được cài
    load_dotenv = None
    find_dotenv = None

_ENV_LOADED = False  # đảm bảo chỉ load .env một lần / process


def _auto_load_env_once() -> None:
    """
    Tự nạp .env nếu:
      - python-dotenv có sẵn, VÀ
      - ONUSLIBS_AUTO_DOTENV=true (mặc định), VÀ
      - tìm thấy file .env (hoặc có ONUSLIBS_DOTENV_PATH)
    Không cài python-dotenv -> bỏ qua yên lặng (không raise).
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    # Bật/tắt auto dotenv
    auto = os.getenv("ONUSLIBS_AUTO_DOTENV", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not auto or load_dotenv is None:
        return

    # Cho phép chỉ định file .env
    path = os.getenv("ONUSLIBS_DOTENV_PATH", "").strip() or None
    override = (
        os.getenv("ONUSLIBS_DOTENV_OVERRIDE", "false").strip().lower()
        in ("1", "true", "yes", "on")
    )

    if path and os.path.exists(path):
        load_dotenv(path, override=override)
        return

    # Không chỉ định => tìm .env gần nhất theo project root
    env_path = find_dotenv() if find_dotenv else ""
    if env_path:
        load_dotenv(env_path, override=override)


# ====== Helpers chuyển kiểu ======
def _b(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _i(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _f(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


class ConfigError(ValueError):
    """Lỗi cấu hình OnusLibs (thiếu/sai ENV, base_url...)."""

    pass


@dataclass
class OnusSettings:
    # ====== Runtime chính (ENV-first) ======
    base_url: str | None = None
    page_size: int | None = None  # <- default từ ENV; app không cần truyền
    req_per_sec: float | None = None
    max_inflight: int | None = None
    timeout_s: float | None = None
    http2: bool | None = None

    # NEW: chia nhỏ datePeriod theo ENV (giờ)
    # 0 hoặc None => không segment, dùng 1 datePeriod như cũ
    date_segment_hours: int | None = None

    # ====== Secrets backend (Module 2) ======
    secrets_backend: str | None = None  # "keyring" | "env"
    keyring_service: str | None = None
    keyring_item: str | None = None
    fall_back_env: bool | None = None  # true => cho phép đọc token từ ENV
    token_header: str | None = None  # tên header chứa token

    # (tuỳ chọn hiển thị/log, client sẽ getattr nếu thiếu)
    log_level: str | None = None
    user_agent: str | None = None
    proxy: str | None = None
    verify_ssl: bool | None = None

    def __post_init__(self):
        # Tự nạp .env (nếu có python-dotenv)
        _auto_load_env_once()

        # ==== Đọc ENV ====
        self.base_url = self.base_url or os.getenv("ONUSLIBS_BASE_URL", "").strip()
        self.page_size = self.page_size or _i("ONUSLIBS_PAGE_SIZE", 20000)  # ENV-first
        self.req_per_sec = self.req_per_sec or _f("ONUSLIBS_REQ_PER_SEC", 2.0)
        self.max_inflight = self.max_inflight or _i("ONUSLIBS_MAX_INFLIGHT", 4)
        self.timeout_s = self.timeout_s or _f("ONUSLIBS_TIMEOUT_S", 60.0)

        # NEW: số giờ tối đa cho mỗi segment datePeriod
        # 0 => tắt segment, dùng nguyên khoảng datePeriod
        self.date_segment_hours = self.date_segment_hours or _i(
            "ONUSLIBS_DATE_SEGMENT_HOURS", 0
        )

        # http2 mặc định True; cho phép override bằng ENV
        self.http2 = True if self.http2 is None else bool(self.http2)
        self.http2 = _b("ONUSLIBS_HTTP2", self.http2)

        self.secrets_backend = (
            self.secrets_backend or os.getenv("ONUSLIBS_SECRETS_BACKEND", "keyring")
        ).lower()
        if self.secrets_backend not in ("keyring", "env"):
            self.secrets_backend = "keyring"

        self.keyring_service = (
            self.keyring_service or os.getenv("ONUSLIBS_KEYRING_SERVICE", "OnusLibs")
        )
        self.keyring_item = (
            self.keyring_item or os.getenv("ONUSLIBS_KEYRING_ITEM", "ACCESS_CLIENT_TOKEN")
        )
        self.fall_back_env = _b(
            "ONUSLIBS_FALLBACK_ENV",
            self.fall_back_env if self.fall_back_env is not None else False,
        )
        self.token_header = (
            self.token_header
            or os.getenv("ONUSLIBS_TOKEN_HEADER", "Access-Client-Token")
        )

        # Optional hiển thị/log
        self.log_level = self.log_level or os.getenv("ONUSLIBS_LOG_LEVEL", "INFO")
        # giữ UA tổng quát (tránh hardcode platform)
        self.user_agent = self.user_agent or f"OnusLibs/3 (Python {os.sys.version.split()[0]})"
        self.proxy = self.proxy or os.getenv("ONUSLIBS_PROXY") or None
        self.verify_ssl = _b(
            "ONUSLIBS_VERIFY_SSL",
            True if self.verify_ssl is None else bool(self.verify_ssl),
        )

        self._validate()

    # ==== Validate rõ ràng ====
    def _validate(self) -> None:
        if not self.base_url:
            raise ConfigError("ONUSLIBS_BASE_URL is empty.")
        bu = self.base_url.strip().lower()
        if not (bu.startswith("http://") or bu.startswith("https://")):
            raise ConfigError("ONUSLIBS_BASE_URL must start with http:// or https://")
        if not isinstance(self.page_size, int) or self.page_size < 1:
            raise ConfigError("ONUSLIBS_PAGE_SIZE must be >= 1")
        if not isinstance(self.req_per_sec, (int, float)) or self.req_per_sec <= 0:
            raise ConfigError("ONUSLIBS_REQ_PER_SEC must be > 0")
        if not isinstance(self.timeout_s, (int, float)) or self.timeout_s <= 0:
            raise ConfigError("ONUSLIBS_TIMEOUT_S must be > 0")
        if not isinstance(self.max_inflight, int) or self.max_inflight < 1:
            raise ConfigError("ONUSLIBS_MAX_INFLIGHT must be >= 1")
        if not isinstance(self.token_header, str) or not self.token_header.strip():
            raise ConfigError("ONUSLIBS_TOKEN_HEADER is empty.")
        # NEW: kiểm tra date_segment_hours >= 0
        if not isinstance(self.date_segment_hours, int) or self.date_segment_hours < 0:
            raise ConfigError("ONUSLIBS_DATE_SEGMENT_HOURS must be >= 0")

    def to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "page_size": self.page_size,
            "req_per_sec": self.req_per_sec,
            "max_inflight": self.max_inflight,
            "timeout_s": self.timeout_s,
            "http2": self.http2,
            "date_segment_hours": self.date_segment_hours,  # NEW
            "secrets_backend": self.secrets_backend,
            "keyring_service": self.keyring_service,
            "keyring_item": self.keyring_item,
            "fall_back_env": self.fall_back_env,
            "token_header": self.token_header,
            "log_level": self.log_level,
            "user_agent": self.user_agent,
            "proxy": self.proxy,
            "verify_ssl": self.verify_ssl,
        }


__all__ = ["OnusSettings", "ConfigError"]
