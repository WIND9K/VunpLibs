from cryptography.fernet import Fernet
import json, os
from pathlib import Path
from typing import Optional

def _secure_dir_from_env() -> Optional[Path]:
    p = os.getenv("ONUSLIBS_SECURE_DIR")
    return Path(p) if p else None

def _key_path(secure_dir: Path) -> Path:
    return secure_dir / "secret.key"

def _enc_path(secure_dir: Path) -> Path:
    return secure_dir / "encrypted_data.json"

def load_key(secure_dir: Path) -> bytes:
    kp = _key_path(secure_dir)
    if not kp.exists():
        raise FileNotFoundError(f"Missing secret.key in {kp.parent}")
    return kp.read_bytes()

def save_key(secure_dir: Path, key: bytes|None=None) -> Path:
    kp = _key_path(secure_dir)
    kp.parent.mkdir(parents=True, exist_ok=True)
    key = key or Fernet.generate_key()
    kp.write_bytes(key)
    return kp

def encrypt_env_to_file(env: dict, secure_dir: Path) -> Path:
    key = load_key(secure_dir)
    f = Fernet(key)
    enc = {k: f.encrypt(str(v).encode()).decode() for k, v in env.items() if v is not None}
    ep = _enc_path(secure_dir)
    ep.write_text(json.dumps(enc), encoding="utf-8")
    return ep

def load_encrypted_data(secure_dir: Optional[Path]=None) -> dict:
    secure_dir = secure_dir or _secure_dir_from_env()
    if not secure_dir:
        raise RuntimeError("Chưa cấu hình ONUSLIBS_SECURE_DIR")
    key = load_key(secure_dir)
    f = Fernet(key)
    ep = _enc_path(secure_dir)
    if not ep.exists():
        raise FileNotFoundError(f"Missing encrypted_data.json in {ep.parent}")
    enc = json.loads(ep.read_text(encoding="utf-8"))
    return {k: f.decrypt(v.encode()).decode() for k, v in enc.items()}
