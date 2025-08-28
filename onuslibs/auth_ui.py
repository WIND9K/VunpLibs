# onuslibs/auth_ui.py
import os, keyring
from typing import Dict

FIELDS = ["WALLET_BASE", "ACCESS_CLIENT_TOKEN"]
SERVICE_FMT = "OnusLibs:{profile}"

def _svc(profile: str) -> str:
    return SERVICE_FMT.format(profile=profile)

def _read_keyring(profile: str) -> Dict[str, str | None]:
    svc = _svc(profile)
    return {k: keyring.get_password(svc, k) for k in FIELDS}

def _save_keyring(profile: str, data: Dict[str, str]):
    svc = _svc(profile)
    for k, v in data.items():
        if v: keyring.set_password(svc, k, v)

def _env(k: str) -> str | None:
    v = os.getenv(k); return v if v else None

def _load_parent_env() -> Dict[str, str]:
    # fallback .env ở thư mục cha dự án (DB & emergency)
    from pathlib import Path
    try:
        from dotenv import dotenv_values
    except Exception:
        return {}
    env_path = Path.cwd().parent / ".env"
    return dotenv_values(str(env_path)) if env_path.exists() else {}

def load_wallet_credentials(profile: str = "default") -> Dict[str, str]:
    data = _read_keyring(profile)
    for k in FIELDS:
        data[k] = data.get(k) or _env(k)
    if not all(data.get(k) for k in FIELDS):
        penv = _load_parent_env()
        for k in FIELDS:
            data[k] = data.get(k) or penv.get(k)
    missing = [k for k in FIELDS if not data.get(k)]
    if missing:
        raise RuntimeError(f"Thiếu thông tin ví: {', '.join(missing)}")
    return {"base": data["WALLET_BASE"], "token": data["ACCESS_CLIENT_TOKEN"]}

def connect_ui(profile: str = "default") -> Dict[str, str]:
    try:
        return load_wallet_credentials(profile)
    except RuntimeError:
        pass  # thiếu -> mở UI

    import streamlit as st
    st.set_page_config(page_title="OnusLibs Login", layout="centered")
    st.title("🔐 OnusLibs — Nhập thông tin ví")

    base = st.text_input("WALLET_BASE", placeholder="https://wallet.vndc.io", value="")
    token = st.text_input("ACCESS_CLIENT_TOKEN", type="password", value="")
    ok = st.button("Save")
    if ok:
        if not base or not token:
            st.error("Thiếu WALLET_BASE hoặc ACCESS_CLIENT_TOKEN"); st.stop()
        _save_keyring(profile, {"WALLET_BASE": base, "ACCESS_CLIENT_TOKEN": token})
        st.success("Saved! Bấm rerun script.")
        return {"base": base, "token": token}

    st.stop()
