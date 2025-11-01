# onuslibs/db/credentials_provider.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

try:
    import keyring
except Exception:
    keyring = None

SERVICE_DEFAULT = "OnusLibs"  # 1 service duy nhất cho API & DB

@dataclass(frozen=True)
class DbCreds:
    host: str
    user: str
    password: str
    name: str
    port: int = 3306
    ssl_ca: Optional[str] = None

def _read_env(k: str) -> Optional[str]:
    v = os.getenv(k)
    return v.strip() if v and str(v).strip() else None

def _service_name() -> str:
    """
    Chỉ dùng 1 biến môi trường duy nhất:
      - ONUSLIBS_KEYRING_SERVICE
      - nếu không có -> dùng SERVICE_DEFAULT = 'OnusLibs'
    """
    return _read_env("ONUSLIBS_KEYRING_SERVICE") or SERVICE_DEFAULT

def _read_keyring(service: str, key: str) -> Optional[str]:
    if keyring is None:
        return None
    try:
        v = keyring.get_password(service, key)
        return v.strip() if v and str(v).strip() else None
    except Exception:
        return None

def _kr_first(service: str, *keys: str) -> Optional[str]:
    for k in keys:
        v = _read_keyring(service, k)
        if v:
            return v
    return None

def load_from_keyring() -> Optional[DbCreds]:
    svc = _service_name()
    host = _kr_first(svc, "DB_HOST", "host")
    user = _kr_first(svc, "DB_USER", "user")
    pwd  = _kr_first(svc, "DB_PASSWORD", "password")
    name = _kr_first(svc, "DB_NAME", "name")
    if not all([host, user, pwd, name]):
        return None

    port_raw = _kr_first(svc, "DB_PORT", "port")
    ssl_ca   = _kr_first(svc, "DB_SSL_CA", "ssl_ca")

    try:
        port = int(port_raw) if port_raw else 3306
    except ValueError:
        port = 3306

    return DbCreds(host=host, user=user, password=pwd, name=name, port=port, ssl_ca=ssl_ca)

def _read_env_first(*keys: str) -> Optional[str]:
    for k in keys:
        v = _read_env(k)
        if v:
            return v
    return None

def load_from_env() -> Optional[DbCreds]:
    host = _read_env_first("DB_HOST", "MYSQL_HOST")
    user = _read_env_first("DB_USER", "MYSQL_USER")
    pwd  = _read_env_first("DB_PASSWORD", "MYSQL_PASSWORD", "MYSQL_PASS")
    name = _read_env_first("DB_NAME", "MYSQL_DB")
    if not all([host, user, pwd, name]):
        return None

    port_raw = _read_env_first("DB_PORT", "MYSQL_PORT")
    ssl_ca   = _read_env_first("DB_SSL_CA", "MYSQL_SSL_CA")
    try:
        port = int(port_raw) if port_raw else 3306
    except ValueError:
        port = 3306
    return DbCreds(host=host, user=user, password=pwd, name=name, port=port, ssl_ca=ssl_ca)

def resolve_db_creds(backend: str = "auto", fallback_env: bool = True) -> DbCreds:
    b = (_read_env("ONUSLIBS_SECRETS_BACKEND") or backend or "auto").strip().lower()
    fb = (_read_env("ONUSLIBS_FALLBACK_ENV") or str(fallback_env)).strip().lower() == "true"

    if b == "env":
        env = load_from_env()
        if env: return env
        raise RuntimeError("DB credentials not found in ENV.")

    if b in ("keyring", "auto"):
        kr = load_from_keyring()
        if kr: return kr
        if b == "keyring" and not fb:
            raise RuntimeError("DB credentials not found in Keyring.")
        env = load_from_env() if fb else None
        if env: return env
        raise RuntimeError("DB credentials not found (Keyring/ENV).")

    # default auto
    kr = load_from_keyring()
    if kr: return kr
    env = load_from_env() if fb else None
    if env: return env
    raise RuntimeError("DB credentials not found (auto).")
