# -*- coding: utf-8 -*-
"""Keyring backend — dùng Credential Manager/Keychain/Secret Service."""

from typing import Optional
import keyring

def get_access_client_token_from_keyring(service: str, item: str) -> Optional[str]:
    tok = keyring.get_password(service, item)
    return tok.strip() if tok else None

# (tuỳ chọn) các hàm tiện ích để set/xoá token trong keyring:
def set_access_client_token_to_keyring(service: str, item: str, token: str) -> None:
    keyring.set_password(service, item, token)

def delete_access_client_token_in_keyring(service: str, item: str) -> None:
    try:
        keyring.delete_password(service, item)
    except Exception:
        pass
