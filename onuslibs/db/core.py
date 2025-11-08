from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Dict

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:  # pragma: no cover
    pymysql = None
    DictCursor = None

from .settings import DbSettings

@dataclass
class DB:
    settings: DbSettings

    def connection(self):
        """
        Trả về kết nối PyMySQL. Yêu cầu đã cài 'pymysql'.
        - Dùng DictCursor nếu có để trả dict; nếu không, fallback con trỏ mặc định.
        - Truyền connect_timeout từ settings (float).
        """
        if pymysql is None:
            raise RuntimeError("pymysql chưa được cài. `pip install pymysql`")

        kwargs = dict(
            host=self.settings.host,
            user=self.settings.user,
            password=self.settings.password,
            database=self.settings.name,
            port=self.settings.port,
            charset="utf8mb4",
            connect_timeout=float(self.settings.connect_timeout),  # dùng float, PyMySQL chấp nhận số
            cursorclass=DictCursor if DictCursor is not None else None,
            autocommit=False,
        )
        # Bỏ key None để tránh cảnh báo
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        # SSL nếu có CA
        if self.settings.ssl_ca:
            kwargs["ssl"] = {"ca": self.settings.ssl_ca}

        return pymysql.connect(**kwargs)

    # Các hàm tiện ích
    def healthcheck(self) -> bool:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    row = cur.fetchone()
                    return bool(row)
        except Exception:
            return False

    def query(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                rows = cur.fetchall()
                if isinstance(rows, list):
                    return rows
                # Fallback: nếu không dùng DictCursor
                cols = [d[0] for d in cur.description] if cur.description else []
                return [dict(zip(cols, r)) for r in rows]  # type: ignore

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> int:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount  # type: ignore

    def bulk_insert(self, sql: str, rows: Iterable[Sequence[Any]], batch_size: int = 1000) -> int:
        total = 0
        batch: List[Sequence[Any]] = []
        with self.connection() as conn:
            with conn.cursor() as cur:
                for r in rows:
                    batch.append(r)
                    if len(batch) >= batch_size:
                        cur.executemany(sql, batch)
                        total += cur.rowcount  # type: ignore
                        batch.clear()
                if batch:
                    cur.executemany(sql, batch)
                    total += cur.rowcount  # type: ignore
            conn.commit()
        return int(total)
