from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import field_validator

class SecuritySettings(BaseSettings):
    """Bảo mật OnusLibs: Keyring-first; có thể bật Fernet; ENV fallback khi được phép."""
    ONUS_BASE_URL: str = "https://wallet.vndc.io"

    # DEV có thể bật fallback ENV; PROD nên tắt (false)
    ONUSLIBS_FALLBACK_ENV: bool = True

    # Keyring
    ONUSLIBS_KEYRING_SERVICE: str = "onuslibs"
    ONUSLIBS_KEYRING_TOKEN_ITEM: str = "ACCESS_CLIENT_TOKEN"

    # Chọn backend: 'auto' | 'keyring' | 'fernet' | 'env'
    # auto: keyring → fernet → env(if fallback cho phép)
    ONUSLIBS_SECRETS_BACKEND: str = "auto"

    # Fernet (nếu dùng)
    ONUSLIBS_ENC_FILE: str = ".env.enc"
    ONUSLIBS_FERNET_KEY_FILE: str = "config/security/secret.key"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("ONUS_BASE_URL")
    @classmethod
    def _normalize_base_url(cls, v: str) -> str:
        v = str(v).strip().rstrip('/')
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("ONUS_BASE_URL must start with http:// or https://")
        return v
