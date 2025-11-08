from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import os

@dataclass(frozen=True)
class DbSettings:
    """
    Thiết lập kết nối MySQL, lấy bí mật từ Keyring + ENV.

    - Nếu `fallback_env=True` → ưu tiên ENV trước.
    - Ngược lại đọc từ keyring trước, cuối cùng ENV là dự phòng.
    """
    host: str
    user: str
    password: str
    name: str
    port: int = 3306
    ssl_ca: Optional[str] = None
    connect_timeout: float = 10.0  # giây

    @classmethod
    def from_secure(
        cls,
        service: Optional[str] = None,       # keyring service, vd "OnusLibs"
        fallback_env: Optional[bool] = None, # True: ưu tiên ENV trước
    ) -> "DbSettings":
        # Lấy mặc định từ OnusSettings (Module 1) nếu thiếu input
        if service is None or fallback_env is None:
            try:
                from onuslibs.config.settings import OnusSettings  # import trễ tránh circular
                os_ = OnusSettings()                               # ✅ đúng: Module 1 tự nạp ENV/.env
                service = service or os_.keyring_service
                if fallback_env is None:
                    fallback_env = os_.fall_back_env              # ✅ đúng tên thuộc tính
            except Exception:
                service = service or os.getenv("ONUSLIBS_KEYRING_SERVICE", "OnusLibs")
                if fallback_env is None:
                    fallback_env = os.getenv("ONUSLIBS_FALLBACK_ENV", "false").strip().lower() in ("1","true","yes","on")

        def get(env_name: str, key_item: str, default: Optional[str] = None) -> Optional[str]:
            """
            Thứ tự: (1) ENV nếu bật fallback_env → (2) Keyring → (3) ENV dự phòng (default).
            """
            val: Optional[str] = None
            if fallback_env:
                val = os.getenv(env_name)
            if val is None:
                try:
                    import keyring  # type: ignore
                    val = keyring.get_password(service, key_item)  # type: ignore
                except Exception:
                    val = None
            if val is None:
                val = os.getenv(env_name, default)
            return val

        # Đọc cấu hình chuẩn
        host = get("ONUSLIBS_DB_HOST", "DB_HOST")
        user = get("ONUSLIBS_DB_USER", "DB_USER")
        password = get("ONUSLIBS_DB_PASSWORD", "DB_PASSWORD")
        name = get("ONUSLIBS_DB_NAME", "DB_NAME")
        port_str = get("ONUSLIBS_DB_PORT", "DB_PORT", "3306")
        ssl_ca = get("ONUSLIBS_DB_SSL_CA", "DB_SSL_CA")
        # NEW: connect_timeout
        ct_str = get("ONUSLIBS_DB_CONNECT_TIMEOUT", "DB_CONNECT_TIMEOUT", "10")

        # Validate trường bắt buộc
        missing = [k for k, v in {"host": host, "user": user, "password": password, "name": name}.items() if v is None]
        if missing:
            raise RuntimeError(
                "DbSettings.from_secure: thiếu " + ", ".join(missing) +
                f". Đặt trong keyring '{service}' (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME) hoặc ENV (ONUSLIBS_DB_*)."
            )

        # Parse số
        try:
            port = int(port_str) if port_str else 3306
        except ValueError as e:
            raise RuntimeError(f"DbSettings.from_secure: cổng DB không hợp lệ: {port_str!r}") from e

        try:
            connect_timeout = float(ct_str) if ct_str else 10.0
            if connect_timeout <= 0:
                raise ValueError
        except ValueError:
            raise RuntimeError(f"DbSettings.from_secure: connect_timeout không hợp lệ: {ct_str!r}")

        # Chuẩn hoá ssl_ca rỗng -> None
        if ssl_ca is not None and not ssl_ca.strip():
            ssl_ca = None

        return cls(
            host=host, user=user, password=password, name=name,
            port=port, ssl_ca=ssl_ca, connect_timeout=connect_timeout
        )

    def safe_dict(self) -> dict:
        def _mask(s: Optional[str]) -> Optional[str]:
            if not s:
                return s
            return (s[:3] + "..." + s[-3:]) if len(s) > 6 else "***"
        return {
            "host": self.host,
            "user": self.user,
            "password": _mask(self.password),
            "name": self.name,
            "port": self.port,
            "ssl_ca": bool(self.ssl_ca),
            "connect_timeout": self.connect_timeout,
        }
