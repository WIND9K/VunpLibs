"""
Test các bug fixes batch 3 (Thread-safety, Double rollback, Session timeout).

Run:
    pytest tests/test_bugfixes_batch3.py -v
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# Mock pymysql trước khi import DB
with patch("onuslibs.db.core.pymysql") as mock_pymysql:
    mock_pymysql.connect = MagicMock()
    mock_pymysql.cursors.DictCursor = MagicMock()
    mock_pymysql.err.OperationalError = Exception
    mock_pymysql.err.InterfaceError = Exception
    
    from onuslibs.db.core import ConnectionPool, DB
    from onuslibs.db.settings import DbSettings


@pytest.fixture
def mock_settings():
    """Mock DbSettings."""
    return DbSettings(
        host="localhost",
        user="test",
        password="test",
        name="test_db",
        port=3306,
        pool_size=2,
        max_overflow=1,
        retry_count=0,
    )


class TestBug1ThreadSafety:
    """Test Bug 1: Thread-safety with Lock."""
    
    def test_pool_has_lock(self, mock_settings):
        """Verify ConnectionPool has _lock attribute."""
        with patch("onuslibs.db.core.pymysql"):
            pool = ConnectionPool(mock_settings, pool_size=2, max_overflow=1)
            
            # Verify lock exists
            assert hasattr(pool, "_lock")
            assert isinstance(pool._lock, threading.Lock)
    
    def test_concurrent_get_connection(self, mock_settings):
        """Test concurrent access to get_connection()."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            # Mock connection
            mock_conn = MagicMock()
            mock_conn.ping = MagicMock()
            mock_conn.close = MagicMock()
            mock_pymysql.connect.return_value = mock_conn
            
            pool = ConnectionPool(mock_settings, pool_size=2, max_overflow=1)
            
            results = []
            errors = []
            
            def get_conn(pool_obj):
                try:
                    conn = pool_obj.get_connection()
                    results.append(conn)
                except Exception as e:
                    errors.append(e)
            
            # Spawn 3 threads (pool_size=2, max_overflow=1 => max 3)
            threads = []
            for _ in range(3):
                t = threading.Thread(target=get_conn, args=(pool,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            # All should succeed
            assert len(results) == 3
            assert len(errors) == 0
            assert pool._created == 3
            assert pool._in_use == 3
    
    def test_concurrent_return_connection(self, mock_settings):
        """Test concurrent return_connection() calls."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_conn.rollback = MagicMock()
            mock_pymysql.connect.return_value = mock_conn
            
            pool = ConnectionPool(mock_settings, pool_size=2, max_overflow=1)
            
            # Get 3 connections
            conns = [pool.get_connection() for _ in range(3)]
            
            # Return them concurrently
            def return_conn(conn):
                pool.return_connection(conn, skip_rollback=False)
            
            threads = []
            for conn in conns:
                t = threading.Thread(target=return_conn, args=(conn,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            # Verify state consistency
            assert pool._in_use == 0
            # Pool should have 2 connections (pool_size=2)
            assert len(pool._pool) == 2
            # Total created should be 3, but 1 was closed (overflow)
            assert pool._created == 2


class TestBug2DoubleRollback:
    """Test Bug 2: Double rollback in transaction()."""
    
    def test_transaction_success_no_double_rollback(self, mock_settings):
        """Verify committed transaction does not rollback."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_conn.commit = MagicMock()
            mock_conn.rollback = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=1, max_overflow=0, retry_count=0)
            
            # Execute transaction successfully
            with db.transaction() as conn:
                pass
            
            # Verify commit called, rollback NOT called
            assert mock_conn.commit.call_count == 1
            assert mock_conn.rollback.call_count == 0
    
    def test_transaction_error_single_rollback(self, mock_settings):
        """Verify failed transaction only rollbacks once."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_conn.commit = MagicMock()
            mock_conn.rollback = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=1, max_overflow=0, retry_count=0)
            
            # Execute transaction with error
            try:
                with db.transaction() as conn:
                    raise ValueError("Test error")
            except ValueError:
                pass
            
            # Verify rollback called exactly ONCE
            assert mock_conn.rollback.call_count == 1
            # Commit should not be called
            assert mock_conn.commit.call_count == 0
    
    def test_transaction_with_actual_db_operations(self, mock_settings):
        """Test transaction with mock cursor operations."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock()
            mock_conn.commit = MagicMock()
            mock_conn.rollback = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=1, max_overflow=0, retry_count=0)
            
            # Simulate error during cursor execution
            mock_cursor.execute.side_effect = Exception("DB error")
            
            try:
                with db.transaction() as conn:
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO test VALUES (1)")
            except Exception:
                pass
            
            # Verify rollback called exactly once
            assert mock_conn.rollback.call_count == 1


class TestBug3SessionTimeoutPersists:
    """Test Bug 3: Session timeout persists across queries."""
    
    def test_query_always_sets_timeout(self, mock_settings):
        """Verify query() always sets MAX_EXECUTION_TIME."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"id": 1}]
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_conn.rollback = MagicMock()
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=1, max_overflow=0, retry_count=0)
            
            # Query with timeout
            db.query("SELECT * FROM users", timeout=5.0)
            
            # Verify SET SESSION MAX_EXECUTION_TIME was called
            calls = mock_cursor.execute.call_args_list
            assert any("SET SESSION MAX_EXECUTION_TIME" in str(call) for call in calls)
            
            # Verify timeout value = 5000ms
            timeout_call = [call for call in calls if "SET SESSION MAX_EXECUTION_TIME" in str(call)][0]
            assert "5000" in str(timeout_call)
    
    def test_query_resets_timeout_to_zero(self, mock_settings):
        """Verify query() without timeout sets MAX_EXECUTION_TIME=0."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"id": 1}]
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_conn.rollback = MagicMock()
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=1, max_overflow=0, retry_count=0)
            
            # Query without timeout
            db.query("SELECT * FROM users")
            
            # Verify SET SESSION MAX_EXECUTION_TIME=0 was called
            calls = mock_cursor.execute.call_args_list
            timeout_calls = [call for call in calls if "SET SESSION MAX_EXECUTION_TIME" in str(call)]
            assert len(timeout_calls) > 0
            assert "=0" in str(timeout_calls[0])
    
    def test_sequential_queries_with_different_timeouts(self, mock_settings):
        """Test sequential queries with different timeout settings."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"id": 1}]
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_conn.rollback = MagicMock()
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=1, max_overflow=0, retry_count=0)
            
            # Query 1: with timeout=5
            db.query("SELECT * FROM users", timeout=5.0)
            
            # Reset mock to clear call history
            mock_cursor.execute.reset_mock()
            
            # Query 2: without timeout (should reset to 0)
            db.query("SELECT * FROM users")
            
            # Verify second query set timeout=0
            calls = mock_cursor.execute.call_args_list
            timeout_calls = [call for call in calls if "SET SESSION MAX_EXECUTION_TIME" in str(call)]
            assert len(timeout_calls) > 0
            assert "=0" in str(timeout_calls[0])


class TestIntegrationAllBugs:
    """Integration test covering all 3 bugs."""
    
    def test_concurrent_transactions_with_timeout_queries(self, mock_settings):
        """Test concurrent transactions with timeout queries."""
        with patch("onuslibs.db.core.pymysql") as mock_pymysql:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [{"id": 1}]
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock()
            mock_conn.commit = MagicMock()
            mock_conn.rollback = MagicMock()
            mock_conn.ping = MagicMock(return_value=True)
            mock_pymysql.connect.return_value = mock_conn
            
            db = DB(mock_settings, pool_size=2, max_overflow=1, retry_count=0)
            
            results = []
            errors = []
            
            def worker(idx):
                try:
                    # Transaction
                    with db.transaction() as conn:
                        with conn.cursor() as cur:
                            cur.execute(f"INSERT INTO test VALUES ({idx})")
                    
                    # Query with timeout
                    rows = db.query("SELECT * FROM test", timeout=5.0 if idx % 2 == 0 else None)
                    results.append((idx, rows))
                except Exception as e:
                    errors.append((idx, e))
            
            # Spawn multiple threads
            threads = []
            for i in range(5):
                t = threading.Thread(target=worker, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            # All should succeed
            assert len(results) == 5
            assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

