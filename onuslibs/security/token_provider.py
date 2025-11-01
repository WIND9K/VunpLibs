# onuslibs/security/token_provider.py
from __future__ import annotations
import os
import keyring
from typing import Any
from .settings import SecuritySettings
from .fernet_loader import load_token_from_fernet

_ENV_KEYS = ("ACCESS_CLIENT_TOKEN","ONUS_ACCESS_CLIENT_TOKEN","ONUSLIBS_ACCESS_CLIENT_TOKEN")

def _env_first(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return None

def _coerce_sec_settings(settings: Any | None) -> SecuritySettings:
    """Nhận mọi kiểu settings (kể cả OnusSettings của core) và trả về SecuritySettings hợp lệ."""
    if isinstance(settings, SecuritySettings):
        return settings
    # Không “mượn” field từ OnusSettings; security lấy config từ ENV theo policy.
    return SecuritySettings()

def get_access_client_token(settings: Any | None = None) -> str:
    """Token theo policy: auto → keyring → fernet → env(if fallback)."""
    s = _coerce_sec_settings(settings)
    backend = (s.ONUSLIBS_SECRETS_BACKEND or "auto").lower().strip()

    def try_keyring() -> str | None:
        try:
            tok = keyring.get_password(s.ONUSLIBS_KEYRING_SERVICE, s.ONUSLIBS_KEYRING_TOKEN_ITEM)
            if tok and tok.strip():
                return tok.strip()
        except Exception:
            pass
        return None

    def try_fernet() -> str | None:
        return load_token_from_fernet(s.ONUSLIBS_ENC_FILE, s.ONUSLIBS_FERNET_KEY_FILE)

    def try_env() -> str | None:
        if s.ONUSLIBS_FALLBACK_ENV:
            return _env_first(*_ENV_KEYS)
        return None

    if backend == "keyring":
        tok = try_keyring() or try_env()
    elif backend == "fernet":
        tok = try_fernet()
    elif backend == "env":
        tok = try_env()
    else:  # auto
        tok = try_keyring() or try_fernet() or try_env()

    if not tok:
        raise RuntimeError(
            "Missing API token. Cấu hình một trong: "
            f"Keyring(service='{s.ONUSLIBS_KEYRING_SERVICE}', item='{s.ONUSLIBS_KEYRING_TOKEN_ITEM}'), "
            f"Fernet(enc='{s.ONUSLIBS_ENC_FILE}', key='{s.ONUSLIBS_FERNET_KEY_FILE}'), "
            f"hoặc ENV {', '.join(_ENV_KEYS)} với ONUSLIBS_FALLBACK_ENV=true (DEV)."
        )
    return tok

def build_headers(settings: Any | None = None) -> dict[str, str]:
    s = _coerce_sec_settings(settings)
    return {"Access-Client-Token": get_access_client_token(s)}
