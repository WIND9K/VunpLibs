from __future__ import annotations
from typing import Dict, Optional
import os

from ..config.settings import OnusSettings

try:
    import keyring
except Exception:
    keyring = None

__all__ = ["build_headers", "preview_headers"]

def _scrub(token: str) -> str:
    return (token[:4] + "..." + token[-4:]) if token else ""

def _read_env_token(settings: OnusSettings) -> Optional[str]:
    """
    Đọc token từ ENV theo thứ tự ứng viên:
      - <ITEM> (vd ACCESS_CLIENT_TOKEN)
      - ONUSLIBS_<ITEM>
      - <ITEM>.upper()
      - ONUSLIBS_<ITEM.upper()>
    """
    item = (settings.keyring_item or "ACCESS_CLIENT_TOKEN").strip()
    candidates = [item, f"ONUSLIBS_{item}", item.upper(), f"ONUSLIBS_{item.upper()}"]
    for key in candidates:
        val = os.getenv(key)
        if val:
            return val
    return None

def build_headers(settings: Optional[OnusSettings] = None,
                  extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Ưu tiên ENV khi:
      - ONUSLIBS_SECRETS_BACKEND=env
      - HOẶC ONUSLIBS_FALLBACK_ENV=true
    Ngược lại, dùng keyring (nếu có).
    """
    s = settings or OnusSettings()
    token: Optional[str] = None

    # 1) ENV-first theo chính sách
    if s.secrets_backend == "env":
        token = _read_env_token(s)

    if not token and s.fall_back_env:
        token = _read_env_token(s)

    # 2) Keyring khi cần
    if not token and s.secrets_backend == "keyring" and keyring is not None:
        try:
            token = keyring.get_password(s.keyring_service, s.keyring_item)
        except Exception:
            token = None

    if not token:
        raise RuntimeError("Missing API token. Provide via ENV (ACCESS_CLIENT_TOKEN) or keyring.")

    headers: Dict[str, str] = {
        s.token_header: token,
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers

def preview_headers(headers: Dict[str, str], settings: Optional[OnusSettings] = None) -> Dict[str, str]:
    s = settings or OnusSettings()
    out: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in (s.token_header.lower(), "authorization"):
            out[k] = _scrub(v)
        else:
            out[k] = v
    return out
