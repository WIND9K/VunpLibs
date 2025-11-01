from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable, Optional
from cryptography.fernet import Fernet

def load_token_from_fernet(enc_file: str, key_file: str,
                           keys: Iterable[str] = ("ACCESS_CLIENT_TOKEN","ONUS_ACCESS_CLIENT_TOKEN","ONUSLIBS_ACCESS_CLIENT_TOKEN")) -> Optional[str]:
    enc = Path(enc_file)
    key = Path(key_file)
    if not (enc.exists() and key.exists()):
        return None
    f = Fernet(key.read_bytes())
    data = json.loads(f.decrypt(enc.read_bytes()).decode("utf-8"))
    for k in keys:
        v = data.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return None
