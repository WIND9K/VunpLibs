# onuslibs/db/settings_db.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

from .credentials_provider import resolve_db_creds, DbCreds
from ..settings import OnusSettings  # dùng chung flags: ONUSLIBS_SECRETS_BACKEND, ONUSLIBS_FALLBACK_ENV

@dataclass(frozen=True)
class DbSettings:
    host: str
    user: str
    password: str
    database: str
    port: int = 3306
    ssl_ca: Optional[str] = None

    @staticmethod
    def _first_env(*keys: str) -> Optional[str]:
        for k in keys:
            v = os.getenv(k)
            if v is not None and str(v).strip() != "":
                return v.strip()
        return None

    @classmethod
    def from_env(cls) -> "DbSettings":
        host = cls._first_env("DB_HOST", "MYSQL_HOST")
        user = cls._first_env("DB_USER", "MYSQL_USER")
        pwd  = cls._first_env("DB_PASSWORD", "MYSQL_PASSWORD", "MYSQL_PASS")
        name = cls._first_env("DB_NAME", "MYSQL_DB")
        port_raw = cls._first_env("DB_PORT", "MYSQL_PORT")
        ssl_ca   = cls._first_env("DB_SSL_CA", "MYSQL_SSL_CA")

        missing = []
        if not host: missing.append("DB_HOST|MYSQL_HOST")
        if not user: missing.append("DB_USER|MYSQL_USER")
        if not pwd:  missing.append("DB_PASSWORD|MYSQL_PASSWORD|MYSQL_PASS")
        if not name: missing.append("DB_NAME|MYSQL_DB")
        if missing:
            details = ", ".join([f"{m}=MISSING" for m in missing])
            raise RuntimeError(f"Missing MySQL ENV. {details}")

        try:
            port = int(port_raw) if port_raw else 3306
        except ValueError:
            port = 3306

        return cls(
            host=host, user=user, password=pwd, database=name,
            port=port, ssl_ca=ssl_ca if (ssl_ca and ssl_ca.strip()) else None
        )
    
    @classmethod
    def from_secure(cls) -> "DbSettings":
        """
        Đọc thông tin DB theo framework bảo mật (giống module API) nhưng
        KHÔNG phụ thuộc OnusSettings để tránh cần BASE_URL khi chỉ dùng DB.

        ENV:
          - ONUSLIBS_SECRETS_BACKEND = auto | keyring | env
          - ONUSLIBS_FALLBACK_ENV    = true|false
        """
        backend = (os.getenv("ONUSLIBS_SECRETS_BACKEND", "auto") or "auto").strip().lower()
        fallback_env = (os.getenv("ONUSLIBS_FALLBACK_ENV", "true") or "true").strip().lower() == "true"

        # dùng provider đã có
        from .credentials_provider import resolve_db_creds
        creds = resolve_db_creds(backend=backend, fallback_env=fallback_env)

        return cls(
            host=creds.host,
            user=creds.user,
            password=creds.password,
            database=creds.name,
            port=creds.port,
            ssl_ca=creds.ssl_ca,
        )


def redact_dsn(s: "DbSettings") -> str:
    """
    Trả về DSN ẩn mật khẩu để log/debug an toàn.
    Ví dụ: mysql://onusreport:***@host:3306/onusreport?ssl_ca=set|none
    """
    ssl_flag = "set" if (getattr(s, "ssl_ca", None) or "").strip() else "none"
    user = getattr(s, "user", "user") or "user"
    host = getattr(s, "host", "host") or "host"
    port = int(getattr(s, "port", 3306) or 3306)
    db   = getattr(s, "database", "db") or "db"
    return f"mysql://{user}:***@{host}:{port}/{db}?ssl_ca={ssl_flag}"
