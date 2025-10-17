from __future__ import annotations
import os
from typing import Optional, Dict
from pathlib import Path

_POSSIBLE_KEYS = (
    "ONUSLIBS_TOKEN",
    "ACCESS_CLIENT_TOKEN",
    "ACCESS-CLIENT-TOKEN",  # ít gặp vì key ENV thường không có '-'
    "CLIENT_TOKEN",
    "ONUS_TOKEN",
)

def _load_dotenv_if_available() -> None:
    """Thử nạp .env nếu python-dotenv có; im lặng nếu không."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        pass

def load_parent_env() -> Dict[str, str]:
    """
    Nạp .env ở thư mục cha (nếu có) – phục vụ module cũ (token_manager, v.v.)
    Không gây lỗi nếu thiếu python-dotenv.
    """
    data: Dict[str, str] = {}
    try:
        from dotenv import load_dotenv, find_dotenv  # type: ignore
        p = find_dotenv(filename=".env", usecwd=True)
        if p:
            load_dotenv(dotenv_path=p)
    except Exception:
        # fallback: tự tìm .env ở cha hiện tại
        env_path = Path.cwd().parent / ".env"
        if env_path.exists():
            try:
                from dotenv import dotenv_values  # type: ignore
                data.update(dotenv_values(str(env_path)))
            except Exception:
                pass
    # trả các biến phổ biến
    for k in ("WALLET_BASE", "ACCESS_CLIENT_TOKEN", "ONUSLIBS_TOKEN"):
        v = os.getenv(k)
        if v:
            data[k] = v
    return data

def get_token() -> Optional[str]:
    """
    Lấy Access-Client-Token:
      - Ưu tiên: các key phổ biến trong ENV
      - Thử nạp .env rồi đọc lại
      - Không raise – trả None để caller xử lý thông báo đẹp hơn
    """
    for key in _POSSIBLE_KEYS:
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()

    _load_dotenv_if_available()
    for key in _POSSIBLE_KEYS:
        val = os.getenv(key)
        if val and val.strip():
            return val.strip()
    return None

# Giữ tương thích tên cũ:
def get_env_token(env_var: str = "ONUSLIBS_TOKEN") -> str:
    val = os.getenv(env_var)
    if not val:
        _load_dotenv_if_available()
        val = os.getenv(env_var)
    if not val:
        raise ValueError(f"{env_var} không tồn tại trong môi trường.")
    return val
