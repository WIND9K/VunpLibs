# onuslibs/token_manager.py
"""
Quản lý token ví ở OS Keyring.
- Ưu tiên: Keyring
- Fallback: biến môi trường (dev)
- Fallback 2: .env thư mục cha (emergency), thông qua compat_env
"""

from __future__ import annotations
import os, keyring, time
from typing import Dict, Optional
from .compat_env import load_parent_env

def _default_profile() -> str:
    return os.getenv("ONUSLIBS_PROFILE", "default")
# rồi cho các API dùng profile or _default_profile() nếu không truyền.


WALLET_FIELDS = ["WALLET_BASE", "ACCESS_CLIENT_TOKEN"]
SERVICE_FMT = "OnusLibs:{profile}"

def _svc(profile: str) -> str:
    return SERVICE_FMT.format(profile=profile)

def get_wallet_credentials(profile: str = "default",
                           allow_env_fallback: bool = True,
                           allow_parent_env_fallback: bool = True) -> Dict[str, str]:
    """Trả về {"base":..., "token":...} hoặc raise RuntimeError nếu thiếu."""
    svc = _svc(profile)
    data: Dict[str, Optional[str]] = {k: keyring.get_password(svc, k) for k in WALLET_FIELDS}

    if allow_env_fallback:
        for k in WALLET_FIELDS:
            data[k] = data.get(k) or os.getenv(k)

    if allow_parent_env_fallback and not all(data.get(k) for k in WALLET_FIELDS):
        penv = load_parent_env()
        for k in WALLET_FIELDS:
            data[k] = data.get(k) or penv.get(k)

    missing = [k for k in WALLET_FIELDS if not data.get(k)]
    if missing:
        raise RuntimeError(f"Thiếu thông tin ví: {', '.join(missing)}")

    return {"base": data["WALLET_BASE"], "token": data["ACCESS_CLIENT_TOKEN"]}

def set_wallet_credentials(profile: str, base: str, token: str) -> None:
    """Lưu token vào Keyring (ghi đè nếu đã có)."""
    svc = _svc(profile)
    keyring.set_password(svc, "WALLET_BASE", base)
    keyring.set_password(svc, "ACCESS_CLIENT_TOKEN", token)
    # (tuỳ chọn) lưu metadata
    keyring.set_password(svc, "META_UPDATED_AT", str(int(time.time())))

def rotate_access_token(profile: str, new_token: str) -> None:
    """Chỉ cập nhật token (giữ nguyên base)."""
    svc = _svc(profile)
    if not keyring.get_password(svc, "WALLET_BASE"):
        raise RuntimeError("Chưa có WALLET_BASE trong profile — hãy chạy set_wallet_credentials trước.")
    keyring.set_password(svc, "ACCESS_CLIENT_TOKEN", new_token)
    keyring.set_password(svc, "META_UPDATED_AT", str(int(time.time())))

def clear_wallet_credentials(profile: str) -> None:
    """Xoá token/base khỏi Keyring."""
    svc = _svc(profile)
    for k in WALLET_FIELDS + ["META_UPDATED_AT"]:
        try:
            # xóa bằng cách ghi giá trị rỗng, do keyring không luôn có API delete nhất quán
            keyring.set_password(svc, k, "")
        except Exception:
            pass
