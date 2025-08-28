# onuslibs/db_config.py
from dotenv import load_dotenv, find_dotenv
import os
from pathlib import Path

dotenv_path = (
    os.getenv("ONUSLIBS_ENV_PATH")
    or find_dotenv(filename=".env", usecwd=True)
    or str(Path.cwd().parent / ".env")
)
load_dotenv(dotenv_path=dotenv_path)

def _env(*keys):
    for k in keys:
        v = os.getenv(k)
        if v: return v
    return None

DB_CONFIG = {
    "host": _env("MYSQL_HOST", "DB_HOST"),
    "user": _env("MYSQL_USER", "DB_USER"),
    "password": _env("MYSQL_PASS", "DB_PASSWORD"),
    "database": _env("MYSQL_DB", "DB_NAME"),
}
