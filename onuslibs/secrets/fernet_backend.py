# -*- coding: utf-8 -*-
"""
Fernet backend — đọc token từ file .env.enc (JSON đã mã hoá). 
Yêu cầu file khoá riêng (secret.key). 
LƯU Ý: cryptography.fernet là AES-128-CBC + HMAC-SHA256 (đã đủ mạnh cho use-case).
"""

import json
from typing import Optional
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

def get_access_client_token_from_fernet(enc_path: str, key_path: str, key_name: str) -> Optional[str]:
    enc_file = Path(enc_path)
    key_file = Path(key_path)
    if not enc_file.is_file() or not key_file.is_file():
        return None
    key = key_file.read_bytes()
    data = enc_file.read_bytes()
    try:
        payload = Fernet(key).decrypt(data)
        obj = json.loads(payload.decode("utf-8"))
        tok = obj.get(key_name)
        return tok.strip() if isinstance(tok, str) else None
    except (InvalidToken, ValueError):
        return None
