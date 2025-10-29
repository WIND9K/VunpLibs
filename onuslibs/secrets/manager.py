# -*- coding: utf-8 -*-
"""
Secret Manager cho OnusLibs v2.
Backends:
  - keyring  (khuyên dùng prod)
  - fernet   (file .env.enc mã hoá; khoá tách riêng)
  - env      (dev/local)
Chọn qua ENV: ONUSLIBS_SECRETS_BACKEND = keyring|fernet|env (mặc định: keyring)
"""

import os
from typing import Optional

def _str_bool(v: Optional[str], default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def get_access_client_token() -> str:
    backend = os.getenv("ONUSLIBS_SECRETS_BACKEND", "keyring").strip().lower()

    if backend == "keyring":
        from .keyring_backend import get_access_client_token_from_keyring
        service = os.getenv("ONUSLIBS_KEYRING_SERVICE", "OnusLibs")
        item    = os.getenv("ONUSLIBS_KEYRING_ITEM",    "ACCESS_CLIENT_TOKEN")
        tok = get_access_client_token_from_keyring(service, item)
        if tok:
            return tok

        # fallback (an toàn: chỉ dev)
        if _str_bool(os.getenv("ONUSLIBS_FALLBACK_ENV", "true"), True):
            from .env_backend import get_access_client_token_from_env
            return get_access_client_token_from_env()
        raise RuntimeError("Không tìm thấy token trong Keyring. Hãy set vào Keyring hoặc bật fallback ENV.")

    elif backend == "fernet":
        from .fernet_backend import get_access_client_token_from_fernet
        enc_file = os.getenv("ONUSLIBS_ENC_FILE", ".env.enc")
        key_file = os.getenv("ONUSLIBS_FERNET_KEY_FILE", "config/security/secret.key")
        key_name = os.getenv("ONUSLIBS_FERNET_KEY_NAME", "ONUSLIBS_ACCESS_CLIENT_TOKEN")
        tok = get_access_client_token_from_fernet(enc_file, key_file, key_name)
        if tok:
            return tok

        if _str_bool(os.getenv("ONUSLIBS_FALLBACK_ENV", "true"), True):
            from .env_backend import get_access_client_token_from_env
            return get_access_client_token_from_env()
        raise RuntimeError("Không giải mã được token từ Fernet file và fallback ENV bị tắt.")

    # backend == env
    from .env_backend import get_access_client_token_from_env
    return get_access_client_token_from_env()
