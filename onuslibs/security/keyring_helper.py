from __future__ import annotations

import os
from typing import Optional, Callable

class SecurityError(RuntimeError):
    """Raised when security-related preconditions are not satisfied (e.g., missing token)."""
    pass

# Keyring optional
try:
    import keyring as _keyring  # type: ignore
    KEYRING_AVAILABLE: bool = True
except Exception:  # pragma: no cover
    _keyring = None
    KEYRING_AVAILABLE = False

# Test hooks (monkeypatch trong unit test)
_keyring_getter: Optional[Callable[[str, str], Optional[str]]] = None
_keyring_setter: Optional[Callable[[str, str, str], None]] = None

def _get_from_env(item: str) -> Optional[str]:
    """
    Tìm secret trong ENV theo thứ tự:
      - <ITEM>
      - ONUSLIBS_<ITEM>
      - <ITEM>.upper()
      - ONUSLIBS_<ITEM.upper()>
    """
    candidates = [item, f"ONUSLIBS_{item}", item.upper(), f"ONUSLIBS_{item.upper()}"]
    for key in candidates:
        val = os.environ.get(key)
        if val:
            return val
    return None

def get_token(settings) -> Optional[str]:
    """
    Lấy token theo cấu hình:
      - ENV-first nếu secrets_backend='env' hoặc fall_back_env=True
      - Sau đó (nếu cần) dùng keyring khi secrets_backend='keyring'
    Yêu cầu settings có: secrets_backend, keyring_service, keyring_item, fall_back_env
    """
    item = getattr(settings, "keyring_item", "ACCESS_CLIENT_TOKEN")
    backend = getattr(settings, "secrets_backend", "keyring")
    allow_env = bool(getattr(settings, "fall_back_env", False))
    service = getattr(settings, "keyring_service", "OnusLibs")

    # 1) ENV-first theo chính sách
    if backend == "env" or allow_env:
        token = _get_from_env(item)
        if token:
            return token

    # 2) Keyring (khi backend='keyring')
    if backend == "keyring" and KEYRING_AVAILABLE:
        getter = _keyring_getter or (_keyring.get_password if _keyring else None)  # type: ignore
        if getter:
            try:
                token = getter(service, item)
                if token:
                    return token
            except Exception:
                pass

    # 3) Không có token
    return None

def require_token(settings) -> str:
    """
    Giống get_token nhưng 'bắt buộc' phải có. Không có → raise SecurityError.
    """
    token = get_token(settings)
    if not token:
        hints = []
        if getattr(settings, "secrets_backend", "keyring") == "keyring":
            svc = getattr(settings, "keyring_service", "OnusLibs")
            itm = getattr(settings, "keyring_item", "ACCESS_CLIENT_TOKEN")
            hints.append(f"keyring service='{svc}', item='{itm}'")
        # Luôn gợi ý ENV tên biến đã dò
        itm = getattr(settings, "keyring_item", "ACCESS_CLIENT_TOKEN")
        hints.append(f"ENV {itm} or ONUSLIBS_{itm} (upper-case variants allowed)")
        hint = "; ".join(hints)
        raise SecurityError(f"Missing access token. Configure via {hint}.")
    return token

def set_token(settings, value: str) -> None:
    """
    Ghi token vào keyring khi secrets_backend='keyring' và có keyring.
    """
    item = getattr(settings, "keyring_item", "ACCESS_CLIENT_TOKEN")
    backend = getattr(settings, "secrets_backend", "keyring")
    service = getattr(settings, "keyring_service", "OnusLibs")

    if backend != "keyring":
        raise SecurityError("set_token only supported with secrets_backend='keyring'.")

    if not KEYRING_AVAILABLE:
        raise SecurityError("Python 'keyring' package is not available.")

    setter = _keyring_setter or (_keyring.set_password if _keyring else None)  # type: ignore
    if not setter:
        raise SecurityError("Keyring backend not initialized.")
    setter(service, item, value)

def preview_secret(secret: Optional[str]) -> str:
    """
    Trả về dạng che của secret phục vụ log:
      - rỗng → '∅'
      - ≤8 ký tự → '***'
      - còn lại → 4 đầu + '...' + 4 cuối
    """
    if not secret:
        return "∅"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"
