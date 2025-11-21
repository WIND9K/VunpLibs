from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Sequence

try:
    import pymysql
    from pymysql.cursors import DictCursor
    from pymysql.err import OperationalError, InterfaceError
except Exception:  # pragma: no cover
    pymysql = None
    DictCursor = None
    OperationalError = None
    InterfaceError = None

from .settings import DbSettings

log = logging.getLogger(__name__)


class ConnectionPool:
    """Connection pool đơn giản cho pymysql.
    
    - Giữ các connection sẵn sàng, tránh overhead tạo mới
    - Tự động kiểm tra connection còn sống không
    - Thread-safe với threading.Lock
    """
    
    def __init__(self, settings: DbSettings, pool_size: int = 5, max_overflow: int = 10):
        self.settings = settings
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self._pool: List[Any] = []
        self._in_use: int = 0
        self._created: int = 0
        self._lock = threading.Lock()  # Thread-safety lock
        
    def _create_connection(self):
        """Tạo connection mới từ settings."""
        if pymysql is None or DictCursor is None:
            raise RuntimeError(
                "pymysql chưa được cài đặt. "
                "Hãy `pip install pymysql` để sử dụng onuslibs.db."
            )
        
        kwargs: Dict[str, Any] = {
            "host": self.settings.host,
            "user": self.settings.user,
            "password": self.settings.password,
            "database": self.settings.name,
            "port": self.settings.port,
            "charset": getattr(self.settings, "charset", "utf8mb4"),
            "connect_timeout": self.settings.connect_timeout,
            "cursorclass": DictCursor,
            "autocommit": False,  # Tắt autocommit để kiểm soát transaction tốt hơn
        }
        
        if self.settings.ssl_ca:
            kwargs["ssl"] = {"ca": self.settings.ssl_ca}
        
        return pymysql.connect(**kwargs)
    
    def _is_connection_alive(self, conn) -> bool:
        """Kiểm tra connection còn sống."""
        try:
            conn.ping(reconnect=False)
            return True
        except Exception:
            return False
    
    def get_connection(self):
        """Lấy connection từ pool (hoặc tạo mới nếu cần)."""
        with self._lock:
            # Thử lấy từ pool trước
            while self._pool:
                conn = self._pool.pop(0)
                if self._is_connection_alive(conn):
                    self._in_use += 1
                    return conn
                else:
                    # Connection chết, bỏ qua và thử cái khác
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self._created -= 1
            
            # Pool rỗng, tạo mới nếu chưa vượt giới hạn
            if self._created < (self.pool_size + self.max_overflow):
                conn = self._create_connection()
                self._created += 1
                self._in_use += 1
                return conn
            
            # Đã đạt giới hạn, phải đợi (tạm thời raise, có thể implement queue sau)
            raise RuntimeError(
                f"Connection pool đã đạt giới hạn: {self.pool_size + self.max_overflow} connections"
            )
    
    def return_connection(self, conn, skip_rollback: bool = False):
        """Trả connection về pool.
        
        Args:
            conn: Connection object
            skip_rollback: Nếu True, không rollback (dùng khi đã commit)
        """
        if conn is None:
            return
        
        # Reset connection state (rollback uncommitted transactions)
        # CHỈ rollback nếu chưa commit (skip_rollback=False)
        if not skip_rollback:
            try:
                conn.rollback()
            except Exception:
                pass
        
        with self._lock:
            self._in_use -= 1
            
            # Kiểm tra connection còn sống
            if self._is_connection_alive(conn):
                # Chỉ giữ tối đa pool_size connections
                if len(self._pool) < self.pool_size:
                    self._pool.append(conn)
                else:
                    # Đóng connection thừa
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self._created -= 1
            else:
                # Connection chết, đóng và giảm counter
                try:
                    conn.close()
                except Exception:
                    pass
                self._created -= 1
    
    def close_all(self):
        """Đóng tất cả connections trong pool."""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()
            self._created = 0
            self._in_use = 0


@dataclass
class DB:
    """
    Wrapper nâng cao quanh pymysql với connection pooling, retry, transaction support.

    Tính năng:
    - Connection pooling (giảm overhead tạo connection)
    - Retry logic cho transient errors
    - Transaction context manager
    - DB.healthcheck()  -> True/False
    - DB.query()        -> SELECT, trả list[dict]
    - DB.execute()      -> INSERT/UPDATE/DELETE 1 câu lệnh
    - DB.bulk_insert()  -> INSERT nhiều dòng bằng executemany
    - DB.bulk_upsert()  -> INSERT ... ON DUPLICATE KEY UPDATE
    - DB.transaction()  -> Context manager cho transaction
    """

    settings: DbSettings
    pool_size: int = 5
    max_overflow: int = 10
    retry_count: int = 3
    retry_delay: float = 0.5
    _pool: ConnectionPool = field(init=False, repr=False)
    
    def __post_init__(self):
        """Khởi tạo connection pool."""
        self._pool = ConnectionPool(
            self.settings,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow
        )

    # =========================
    # Nội bộ
    # =========================

    def _is_transient_error(self, err: Exception) -> bool:
        """Kiểm tra có phải lỗi tạm thời (có thể retry)."""
        if OperationalError and isinstance(err, OperationalError):
            # MySQL error codes có thể retry
            err_code = getattr(err, "args", [None])[0]
            # 1205: Lock wait timeout, 1213: Deadlock, 2006: Server gone away, 2013: Lost connection
            return err_code in (1205, 1213, 2006, 2013, 2003)
        if InterfaceError and isinstance(err, InterfaceError):
            return True
        return False
    
    def _retry_on_error(self, func: Callable, *args, **kwargs):
        """Thực thi function với retry logic cho transient errors.
        
        Note: Nếu retry_count=0, chỉ execute 1 lần (không retry).
        """
        # Đảm bảo ít nhất 1 lần execution
        max_attempts = max(1, self.retry_count)
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                
                if not self._is_transient_error(e):
                    # Không phải transient error, raise ngay
                    raise
                
                # Nếu retry_count=0, không retry
                if self.retry_count == 0:
                    raise
                
                if attempt < max_attempts - 1:
                    # Còn lần retry, log và sleep
                    log.warning(
                        f"DB transient error (attempt {attempt + 1}/{max_attempts}): {e}. "
                        f"Retry sau {self.retry_delay}s..."
                    )
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    # Hết lần retry, raise
                    log.error(
                        f"DB error sau {max_attempts} lần thử: {e}"
                    )
                    raise
        
        # Không nên tới đây, nhưng để safe
        if last_error:
            raise last_error

    @contextmanager
    def get_connection(self, skip_rollback: bool = False) -> Generator:
        """Context manager để lấy connection từ pool.
        
        Tự động trả connection về pool sau khi dùng xong.
        
        Args:
            skip_rollback: Nếu True, không rollback khi return (dùng cho transaction)
        
        Ví dụ:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        """
        conn = self._pool.get_connection()
        try:
            yield conn
        finally:
            self._pool.return_connection(conn, skip_rollback=skip_rollback)
    
    def connection(self):
        """
        Trả về context manager cho connection (backward compatible).
        
        DEPRECATED: Dùng get_connection() thay thế.

            db = DB(DbSettings.from_secure())
            with db.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    print(cur.fetchone())
        """
        return self.get_connection()
    
    @contextmanager
    def transaction(self) -> Generator:
        """Context manager cho transaction.
        
        Tự động commit khi thành công, rollback khi có lỗi.
        
        Ví dụ:
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT ...")
                    cur.execute("UPDATE ...")
                # Auto commit ở đây
        """
        conn = self._pool.get_connection()
        skip_rollback = False
        try:
            yield conn
            conn.commit()
            skip_rollback = True  # Đã commit, không rollback nữa
            log.debug("Transaction committed successfully")
        except Exception as e:
            conn.rollback()
            skip_rollback = True  # Đã rollback rồi, không rollback lại
            log.warning(f"Transaction rolled back due to error: {e}")
            raise
        finally:
            # skip_rollback=True trong cả 2 trường hợp:
            # 1. Commit thành công
            # 2. Đã rollback trong except block
            self._pool.return_connection(conn, skip_rollback=skip_rollback)
    
    def close_pool(self):
        """Đóng tất cả connections trong pool."""
        self._pool.close_all()

    # =========================
    # Các hàm tiện ích instance
    # =========================

    def healthcheck(self) -> bool:
        """
        Chạy SELECT 1, trả về True nếu thành công.

        Không raise exception, chỉ trả False nếu có lỗi.
        """
        try:
            def _check():
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        row = cur.fetchone()
                        return bool(row)
            
            return self._retry_on_error(_check)
        except Exception as e:
            log.debug(f"Healthcheck failed: {e}")
            return False

    def query(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Thực thi SELECT, trả về list[dict].

        SQL bắt buộc phải là SELECT.
        
        Args:
            sql: Câu lệnh SQL SELECT
            params: Parameters cho query
            timeout: Timeout cho query (giây), None = không giới hạn
        """
        sql_stripped = sql.lstrip().upper()
        if not sql_stripped.startswith("SELECT"):
            raise ValueError("DB.query chỉ dùng cho câu lệnh SELECT.")

        def _execute_query():
            start_time = time.time()
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Luôn set query timeout (0 = không giới hạn)
                    # Điều này đảm bảo reset timeout từ query trước
                    timeout_ms = int(timeout * 1000) if timeout else 0
                    cur.execute(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}")
                    
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                    
                    elapsed = time.time() - start_time
                    if elapsed > 1.0:  # Log slow queries (> 1s)
                        log.warning(f"Slow query ({elapsed:.2f}s): {sql[:100]}...")
                    
                    return list(rows)  # type: ignore[return-value]
        
        return self._retry_on_error(_execute_query)

    def execute(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
    ) -> int:
        """
        Thực thi 1 câu lệnh write (INSERT/UPDATE/DELETE).

        Trả về số dòng ảnh hưởng (rowcount).
        """
        def _execute():
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    affected = cur.rowcount
                conn.commit()
                return int(affected)
        
        return self._retry_on_error(_execute)

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
        
        IMPORTANT: Nếu rows là generator/iterator, nó sẽ được materialize
        thành list để hỗ trợ retry. Nếu dataset quá lớn, xem xét tắt retry
        bằng cách set retry_count=0.
        """
        if batch_size <= 0:
            raise ValueError("batch_size phải > 0")

        # Materialize iterator thành list để hỗ trợ retry
        # Nếu đã là list/tuple, không tốn overhead
        if not isinstance(rows, (list, tuple)):
            rows = list(rows)
        
        def _bulk_insert():
            total = 0
            batch: List[Sequence[Any]] = []

            with self.get_connection() as conn:
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
        
        return self._retry_on_error(_bulk_insert)
    
    def bulk_upsert(
        self,
        table: str,
        columns: List[str],
        rows: Iterable[Sequence[Any]],
        update_columns: Optional[List[str]] = None,
        batch_size: int = 1000,
    ) -> int:
        """
        Bulk INSERT ... ON DUPLICATE KEY UPDATE.
        
        Args:
            table: Tên bảng
            columns: Danh sách tên cột
            rows: Iterable[tuple] dữ liệu
            update_columns: Cột cần update khi duplicate.
                           - None = update tất cả cột (bao gồm cả key)
                           - [] = không update gì (chỉ INSERT nếu chưa có)
                           - ["col1", "col2"] = chỉ update các cột này
            batch_size: Số dòng mỗi batch
        
        Warning:
            Nếu update_columns bao gồm primary key hoặc unique key,
            MySQL sẽ báo lỗi. Đảm bảo chỉ update non-key columns.
        
        Ví dụ:
            # Update tất cả non-key columns
            db.bulk_upsert(
                table="users",
                columns=["id", "name", "email"],
                rows=[(1, "Alice", "alice@example.com")],
                update_columns=["name", "email"],  # Không update "id"
            )
            
            # Chỉ INSERT, không UPDATE (ignore duplicates)
            db.bulk_upsert(
                table="users",
                columns=["id", "name"],
                rows=[(1, "Alice")],
                update_columns=[],  # Không update gì
            )
        """
        if not columns:
            raise ValueError("columns không được rỗng")
        
        # Build SQL
        cols_str = ", ".join(f"`{c}`" for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        
        # Columns để update
        if update_columns is None:
            # Mặc định: update tất cả
            # WARNING: Có thể gây lỗi nếu bao gồm primary key
            update_columns = columns
            log.warning(
                f"bulk_upsert: update_columns=None sẽ update TẤT CẢ cột bao gồm key. "
                f"Nếu gặp lỗi MySQL, hãy chỉ định update_columns rõ ràng."
            )
        
        if not update_columns:
            # update_columns=[] => không update gì, chỉ INSERT IGNORE
            # Dùng id=id (dummy update) để MySQL không báo lỗi syntax
            # Nhưng giá trị không thay đổi
            first_col = columns[0]
            update_str = f"`{first_col}` = `{first_col}`"
        else:
            update_str = ", ".join(
                f"`{c}` = VALUES(`{c}`)" for c in update_columns
            )
        
        sql = (
            f"INSERT INTO `{table}` ({cols_str}) "
            f"VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_str}"
        )
        
        return self.bulk_insert(sql, rows, batch_size=batch_size)
    
    def query_one(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Thực thi SELECT và trả về 1 dòng duy nhất (hoặc None).
        
        Nếu có nhiều dòng, chỉ lấy dòng đầu tiên.
        """
        rows = self.query(sql, params)
        return rows[0] if rows else None
    
    def query_scalar(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        default: Any = None,
    ) -> Any:
        """
        Thực thi SELECT và trả về giá trị scalar (cột đầu tiên của dòng đầu tiên).
        
        Args:
            sql: Câu lệnh SQL
            params: Parameters
            default: Giá trị mặc định nếu không có kết quả
        
        Ví dụ:
            count = db.query_scalar("SELECT COUNT(*) as cnt FROM users")
        """
        row = self.query_one(sql, params)
        if row is None:
            return default
        # Lấy giá trị đầu tiên trong dict
        return next(iter(row.values())) if row else default


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
        return DB(
            settings=settings,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            retry_count=settings.retry_count,
        )
    if _default_db is None:
        db_settings = DbSettings.from_secure()
        _default_db = DB(
            settings=db_settings,
            pool_size=db_settings.pool_size,
            max_overflow=db_settings.max_overflow,
            retry_count=db_settings.retry_count,
        )
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


def bulk_upsert(
    table: str,
    columns: List[str],
    rows: Iterable[Sequence[Any]],
    update_columns: Optional[List[str]] = None,
    batch_size: int = 1000,
    settings: Optional[DbSettings] = None,
) -> int:
    """
    Bulk INSERT ... ON DUPLICATE KEY UPDATE.
    
    Ví dụ:
    
        from onuslibs.db import bulk_upsert
        
        rows = [
            (1, "Alice", "alice@example.com"),
            (2, "Bob", "bob@example.com"),
        ]
        bulk_upsert(
            table="users",
            columns=["id", "name", "email"],
            rows=rows,
            update_columns=["name", "email"],
        )
    """
    db = _get_default_db(settings)
    return db.bulk_upsert(table, columns, rows, update_columns, batch_size)


def query_one(
    sql: str,
    params: Optional[Sequence[Any]] = None,
    settings: Optional[DbSettings] = None,
) -> Optional[Dict[str, Any]]:
    """
    Thực thi SELECT và trả về 1 dòng duy nhất.
    
    Ví dụ:
    
        from onuslibs.db import query_one
        user = query_one("SELECT * FROM users WHERE id=%s", (123,))
    """
    db = _get_default_db(settings)
    return db.query_one(sql, params)


def query_scalar(
    sql: str,
    params: Optional[Sequence[Any]] = None,
    default: Any = None,
    settings: Optional[DbSettings] = None,
) -> Any:
    """
    Thực thi SELECT và trả về giá trị scalar.
    
    Ví dụ:
    
        from onuslibs.db import query_scalar
        count = query_scalar("SELECT COUNT(*) as cnt FROM users")
    """
    db = _get_default_db(settings)
    return db.query_scalar(sql, params, default)


def transaction(settings: Optional[DbSettings] = None):
    """
    Context manager cho transaction.
    
    Ví dụ:
    
        from onuslibs.db import transaction
        
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users ...")
                cur.execute("UPDATE accounts ...")
            # Auto commit
    """
    db = _get_default_db(settings)
    return db.transaction()
