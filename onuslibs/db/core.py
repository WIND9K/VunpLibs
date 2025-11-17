from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    import pymysql
    from pymysql.cursors import DictCursor
except Exception:  # pragma: no cover
    pymysql = None
    DictCursor = None

from .settings import DbSettings


@dataclass
class DB:
    """
    Wrapper đơn giản quanh pymysql, dùng DbSettings để kết nối.

    - DB.healthcheck()  -> True/False
    - DB.query()        -> SELECT, trả list[dict]
    - DB.execute()      -> INSERT/UPDATE/DELETE 1 câu lệnh
    - DB.bulk_insert()  -> INSERT nhiều dòng bằng executemany
    """

    settings: DbSettings

    # =========================
    # Nội bộ
    # =========================

    def _ensure_driver(self) -> None:
        if pymysql is None or DictCursor is None:
            raise RuntimeError(
                "pymysql chưa được cài đặt. "
                "Hãy `pip install pymysql` để sử dụng onuslibs.db."
            )

    def connection(self):
        """
        Trả về kết nối pymysql.

        Caller có thể dùng trực tiếp:

            db = DB(DbSettings.from_secure())
            with db.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    print(cur.fetchone())
        """
        self._ensure_driver()

        host = getattr(self.settings, "host", None)
        user = getattr(self.settings, "user", None)
        password = getattr(self.settings, "password", None)
        database = getattr(self.settings, "name", None)
        port = int(getattr(self.settings, "port", 3306))
        charset = getattr(self.settings, "charset", "utf8mb4")
        connect_timeout = float(getattr(self.settings, "connect_timeout", 10.0))
        ssl_ca = getattr(self.settings, "ssl_ca", None)

        kwargs: Dict[str, Any] = {
            "host": host,
            "user": user,
            "password": password,
            "database": database,
            "port": port,
            "charset": charset,
            "connect_timeout": connect_timeout,
            "cursorclass": DictCursor,
        }

        if ssl_ca:
            # Xem thêm: https://pymysql.readthedocs.io/en/latest/modules/connections.html
            kwargs["ssl"] = {"ca": ssl_ca}

        return pymysql.connect(**kwargs)

    # =========================
    # Các hàm tiện ích instance
    # =========================

    def healthcheck(self) -> bool:
        """
        Chạy SELECT 1, trả về True nếu thành công.

        Không raise exception, chỉ trả False nếu có lỗi.
        """
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    row = cur.fetchone()
                    return bool(row)
        except Exception:
            return False

    def query(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Thực thi SELECT, trả về list[dict].

        SQL bắt buộc phải là SELECT.
        """
        sql_stripped = sql.lstrip().upper()
        if not sql_stripped.startswith("SELECT"):
            raise ValueError("DB.query chỉ dùng cho câu lệnh SELECT.")

        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        # rows đã là dict nếu dùng DictCursor
        return list(rows)  # type: ignore[return-value]

    def execute(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
    ) -> int:
        """
        Thực thi 1 câu lệnh write (INSERT/UPDATE/DELETE).

        Trả về số dòng ảnh hưởng (rowcount).
        """
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                affected = cur.rowcount
            conn.commit()
        return int(affected)

    def bulk_insert(
        self,
        sql: str,
        rows: Iterable[Sequence[Any]],
        batch_size: int = 1000,
    ) -> int:
        """
        Bulk insert bằng executemany theo batch_size.

        sql:  "INSERT INTO table(col1, col2, ...) VALUES (%s, %s, ...)"
        rows: Iterable[tuple] tương ứng với placeholder trong sql.
        """
        if batch_size <= 0:
            raise ValueError("batch_size phải > 0")

        total = 0
        batch: List[Sequence[Any]] = []

        with self.connection() as conn:
            with conn.cursor() as cur:
                for r in rows:
                    batch.append(r)
                    if len(batch) >= batch_size:
                        cur.executemany(sql, batch)
                        total += int(cur.rowcount)
                        batch.clear()
                if batch:
                    cur.executemany(sql, batch)
                    total += int(cur.rowcount)
            conn.commit()

        return int(total)


# =========================
# Facade hàm cấp module
# =========================

_default_db: Optional[DB] = None


def _get_default_db(settings: Optional[DbSettings] = None) -> DB:
    """
    Trả về DB mặc định dùng DbSettings.from_secure().

    - Nếu truyền settings: tạo DB mới với settings đó (không cache).
    - Nếu không: dùng 1 instance DB duy nhất lưu trong _default_db.
    """
    global _default_db
    if settings is not None:
        return DB(settings=settings)
    if _default_db is None:
        _default_db = DB(settings=DbSettings.from_secure())
    return _default_db


def connect(settings: Optional[DbSettings] = None):
    """
    Trả về 1 kết nối pymysql.

    Ví dụ:

        from onuslibs.db import connect
        conn = connect()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            print(cur.fetchone())
    """
    db = _get_default_db(settings)
    return db.connection()


def healthcheck(settings: Optional[DbSettings] = None) -> bool:
    """
    Kiểm tra DB bằng SELECT 1.

    Ví dụ:

        from onuslibs.db import healthcheck
        print(healthcheck())
    """
    db = _get_default_db(settings)
    return db.healthcheck()


def query(
    sql: str,
    params: Optional[Sequence[Any]] = None,
    settings: Optional[DbSettings] = None,
) -> List[Dict[str, Any]]:
    """
    Thực thi SELECT, trả về list[dict].

    Ví dụ:

        from onuslibs.db import query
        rows = query("SELECT * FROM onchain_diary LIMIT %s", (10,))
    """
    db = _get_default_db(settings)
    return db.query(sql, params)


def execute(
    sql: str,
    params: Optional[Sequence[Any]] = None,
    settings: Optional[DbSettings] = None,
) -> int:
    """
    Thực thi 1 câu lệnh write (INSERT/UPDATE/DELETE).

    Ví dụ:

        from onuslibs.db import execute
        execute(
            "INSERT INTO tmp_onuslibs_smoke(id, name, score) VALUES (%s,%s,%s)",
            (1, "smoke", 100),
        )
    """
    db = _get_default_db(settings)
    return db.execute(sql, params)


def bulk_insert(
    sql: str,
    rows: Iterable[Sequence[Any]],
    batch_size: int = 1000,
    settings: Optional[DbSettings] = None,
) -> int:
    """
    Bulk insert nhiều dòng theo batch_size.

    Ví dụ:

        from onuslibs.db import bulk_insert

        rows = [
            (1, "Alice", 90),
            (2, "Bob", 85),
        ]
        bulk_insert(
            "INSERT INTO tmp_onuslibs_smoke(id, name, score) VALUES (%s,%s,%s)",
            rows,
            batch_size=1000,
        )
    """
    db = _get_default_db(settings)
    return db.bulk_insert(sql, rows, batch_size=batch_size)
