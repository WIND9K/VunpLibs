# -*- coding: utf-8 -*-
import os

def get_access_client_token_from_env() -> str:
    tok = os.getenv("ONUSLIBS_ACCESS_CLIENT_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("Thiếu ENV ONUSLIBS_ACCESS_CLIENT_TOKEN")
    return tok
