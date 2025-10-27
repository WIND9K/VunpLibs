from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, Iterable, Iterator, Optional

import os
import httpx
import keyring
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from .settings import LibSettings

PAGE_SIZE_DEFAULT = 20_000
EPSILON_S_DEFAULT = 1

def _get_token(profile: str = "default") -> str:
    # ENV/.env (pydantic-settings) trước, không hỗ trợ tên cũ
    s = LibSettings()
    if s.ACCESS_CLIENT_TOKEN:
        return s.ACCESS_CLIENT_TOKEN
    # Keyring fallback
    tk = keyring.get_password(f"onuslibs:{profile}", "ACCESS_CLIENT_TOKEN")
    if not tk:
        raise RuntimeError("Thiếu ACCESS_CLIENT_TOKEN (Keyring hoặc ONUSLIBS_ACCESS_CLIENT_TOKEN trong .env/ENV).")
    return tk

def _get_base() -> str:
    s = LibSettings()
    return s.WALLET_BASE

@retry(stop=stop_after_attempt(5), wait=wait_exponential_jitter(2, 8))
def _get(client: httpx.Client, path: str, params: dict, token: str):
    r = client.get(
        path if path.startswith("/") else f"/{path}",
        params=params,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Access-Client-Token": token,
            "User-Agent": "OnusLibs/2.0",
        },
        follow_redirects=False,
    )
    r.raise_for_status()
    return r.json(), r.headers

def fetch(
    start: datetime,
    end: datetime,
    endpoint: str,
    filters: Optional[Dict[str, str]] = None,
    page_size: int = PAGE_SIZE_DEFAULT,
    epsilon_seconds: int = EPSILON_S_DEFAULT,
    profile: str = "default",
    date_field: str = "date",
) -> Iterator[dict]:
    """
    Phân trang kiểu datePeriod (page=0) theo ngày; nếu trả về đủ page_size,
    tiếp tục từ max(date) + epsilon cho tới hết khoảng.
    """
    base_url = _get_base()
    token = _get_token(profile)

    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(30, connect=10)) as client:
        cursor = start
        while cursor < end:
            day_start = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = min(day_start + timedelta(days=1), end)
            while cursor < day_end:
                params = {
                    **(filters or {}),
                    "page": 0,
                    "pageSize": page_size,
                    "datePeriod": f"{cursor.isoformat()},{day_end.isoformat()}",
                }
                data, _hdr = _get(client, endpoint, params, token)
                items = data if isinstance(data, list) else data.get("items", [])
                for it in items:
                    yield it
                if len(items) < page_size:
                    break
                last_ts = max(
                    datetime.fromisoformat(i[date_field])
                    for i in items
                    if i.get(date_field)
                )
                nxt = last_ts + timedelta(seconds=epsilon_seconds)
                cursor = max(cursor + timedelta(seconds=epsilon_seconds), nxt)
            cursor = day_end

def to_csv(items: Iterable[dict], path: str) -> None:
    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError("Cần cài pandas để dùng to_csv") from e
    rows = [{
        "date": (it.get("date","")[:10]),
        "user_id": it.get("relatedAccount",{}).get("user",{}).get("id"),
        "user_display": it.get("relatedAccount",{}).get("user",{}).get("display"),
        "amount": it.get("amount"),
    } for it in items]
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")

def to_db(items: Iterable[dict], table: str) -> None:
    # Yêu cầu DB_* theo môi trường dự án v2; không tự đọc tên cũ
    host = os.getenv("DB_HOST")
    if not host:
        raise RuntimeError("Thiếu cấu hình DB_* trong ENV (.env).")
    try:
        from sqlalchemy import create_engine, text
    except ImportError as e:
        raise RuntimeError("Cần cài SQLAlchemy+pymysql để ghi DB.") from e
    dsn = (
        f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
        f"{host}:{int(os.getenv('DB_PORT','3306'))}/{os.getenv('DB_NAME')}?charset=utf8mb4"
    )
    engine = create_engine(dsn, pool_pre_ping=True)
    rows = [{
        "date": (it.get("date","")[:10]),
        "uid":  it.get("relatedAccount",{}).get("user",{}).get("id"),
        "name": it.get("relatedAccount",{}).get("user",{}).get("display"),
        "amount": it.get("amount"),
        "payload": None,
    } for it in items]
    with engine.begin() as conn:
        conn.execute(text(f"""            INSERT INTO {table} (date, user_id, user_display, amount, payload_json)
            VALUES (:date, :uid, :name, :amount, :payload)
        """), rows)
