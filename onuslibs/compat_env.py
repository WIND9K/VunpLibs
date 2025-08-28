from pathlib import Path
from typing import Dict

def load_parent_env() -> Dict[str, str]:
    """
    Fallback: nạp file .env ở THƯ MỤC CHA của dự án nếu có.
    Dùng cho các cấu hình còn lại (DB, logger...), hoặc emergency cho WALLET_*.
    """
    try:
        from dotenv import dotenv_values
    except Exception:
        return {}
    env_path = Path.cwd().parent / ".env"
    return dotenv_values(str(env_path)) if env_path.exists() else {}
