#!/usr/bin/env python3
"""
Demo các tính năng cải tiến của module DB v3.1

Tính năng mới:
- Connection pooling (giảm overhead tạo connection)
- Retry logic cho transient errors
- Transaction context manager
- bulk_upsert (INSERT ... ON DUPLICATE KEY UPDATE)
- query_one, query_scalar helpers
- Slow query logging
"""

from onuslibs.db import (
    DB,
    DbSettings,
    healthcheck,
    query,
    query_one,
    query_scalar,
    execute,
    bulk_insert,
    bulk_upsert,
    transaction,
)


def demo_basic_operations():
    """Demo các thao tác cơ bản."""
    print("=" * 60)
    print("1. HEALTHCHECK")
    print("=" * 60)
    
    if healthcheck():
        print("✅ Database connection OK!")
    else:
        print("❌ Database connection failed!")
        return
    
    print("\n" + "=" * 60)
    print("2. QUERY - Lấy danh sách")
    print("=" * 60)
    
    # Query trả về list[dict]
    rows = query("SELECT * FROM onchain_diary LIMIT 5")
    print(f"Tìm thấy {len(rows)} dòng")
    for row in rows:
        print(f"  - {row}")
    
    print("\n" + "=" * 60)
    print("3. QUERY_ONE - Lấy 1 dòng")
    print("=" * 60)
    
    # query_one trả về dict hoặc None
    row = query_one("SELECT * FROM onchain_diary LIMIT 1")
    if row:
        print(f"Row đầu tiên: {row}")
    
    print("\n" + "=" * 60)
    print("4. QUERY_SCALAR - Lấy giá trị đơn")
    print("=" * 60)
    
    # query_scalar trả về giá trị đầu tiên của dòng đầu tiên
    count = query_scalar("SELECT COUNT(*) as cnt FROM onchain_diary")
    print(f"Tổng số dòng: {count}")


def demo_transaction():
    """Demo transaction context manager."""
    print("\n" + "=" * 60)
    print("5. TRANSACTION - Context Manager")
    print("=" * 60)
    
    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                # Thực hiện nhiều câu lệnh trong 1 transaction
                cur.execute(
                    "INSERT INTO tmp_test(id, name) VALUES (%s, %s)",
                    (1, "Alice")
                )
                cur.execute(
                    "UPDATE tmp_test SET name=%s WHERE id=%s",
                    ("Alice Updated", 1)
                )
                # Transaction sẽ tự động commit khi thoát context
        print("✅ Transaction committed successfully")
    except Exception as e:
        print(f"❌ Transaction failed: {e}")


def demo_bulk_operations():
    """Demo bulk insert và upsert."""
    print("\n" + "=" * 60)
    print("6. BULK_INSERT - Insert nhiều dòng")
    print("=" * 60)
    
    rows = [
        (1, "User 1", "user1@example.com"),
        (2, "User 2", "user2@example.com"),
        (3, "User 3", "user3@example.com"),
    ]
    
    try:
        affected = bulk_insert(
            sql="INSERT INTO tmp_users(id, name, email) VALUES (%s, %s, %s)",
            rows=rows,
            batch_size=1000,
        )
        print(f"✅ Inserted {affected} rows")
    except Exception as e:
        print(f"❌ Bulk insert failed: {e}")
    
    print("\n" + "=" * 60)
    print("7. BULK_UPSERT - Insert hoặc Update")
    print("=" * 60)
    
    # Upsert: insert nếu chưa có, update nếu đã tồn tại
    upsert_rows = [
        (1, "User 1 Updated", "user1_new@example.com"),
        (4, "User 4", "user4@example.com"),
    ]
    
    try:
        affected = bulk_upsert(
            table="tmp_users",
            columns=["id", "name", "email"],
            rows=upsert_rows,
            update_columns=["name", "email"],  # Update các cột này khi duplicate
            batch_size=1000,
        )
        print(f"✅ Upserted {affected} rows")
    except Exception as e:
        print(f"❌ Bulk upsert failed: {e}")


def demo_connection_pool():
    """Demo connection pooling."""
    print("\n" + "=" * 60)
    print("8. CONNECTION POOL - Hiệu suất cao")
    print("=" * 60)
    
    # Tạo DB instance với custom pool settings
    settings = DbSettings.from_secure()
    db = DB(
        settings=settings,
        pool_size=10,        # 10 connections trong pool
        max_overflow=20,     # Tối đa 20 connections thêm
        retry_count=3,       # Retry 3 lần khi lỗi
    )
    
    print(f"Pool settings: size={db.pool_size}, "
          f"max_overflow={db.max_overflow}")
    
    # Thực hiện nhiều queries - connections sẽ được reuse
    import time
    start = time.time()
    
    for i in range(10):
        result = db.query_scalar("SELECT 1")
    
    elapsed = time.time() - start
    print(f"✅ Completed 10 queries in {elapsed:.3f}s")
    print("   (Connection pooling giúp giảm overhead tạo connection)")
    
    # Đóng pool khi không dùng nữa
    db.close_pool()


def demo_retry_logic():
    """Demo retry logic cho transient errors."""
    print("\n" + "=" * 60)
    print("9. RETRY LOGIC - Tự động retry khi lỗi tạm thời")
    print("=" * 60)
    
    print("Module DB sẽ tự động retry khi gặp các lỗi:")
    print("  - 1205: Lock wait timeout")
    print("  - 1213: Deadlock")
    print("  - 2006: MySQL server has gone away")
    print("  - 2013: Lost connection during query")
    print("\n✅ Retry logic được bật tự động (mặc định 3 lần)")


def demo_env_config():
    """Demo cấu hình qua ENV."""
    print("\n" + "=" * 60)
    print("10. CẤU HÌNH QUA ENV")
    print("=" * 60)
    
    print("""
Các biến ENV mới (v3.1):

# Connection pool
ONUSLIBS_DB_POOL_SIZE=5          # Số connections trong pool
ONUSLIBS_DB_MAX_OVERFLOW=10      # Số connections tối đa thêm
ONUSLIBS_DB_RETRY_COUNT=3        # Số lần retry

# Existing
ONUSLIBS_DB_HOST=127.0.0.1
ONUSLIBS_DB_PORT=3306
ONUSLIBS_DB_USER=onusreport
ONUSLIBS_DB_PASSWORD=xxx
ONUSLIBS_DB_NAME=onusreport
ONUSLIBS_DB_CONNECT_TIMEOUT=10
ONUSLIBS_DB_SSL_CA=              # SSL certificate path (nếu cần)
    """)


def main():
    """Chạy tất cả demos."""
    print("\n" + "🚀" * 30)
    print(" " * 10 + "OnusLibs DB Module v3.1 - Enhanced Demo")
    print("🚀" * 30 + "\n")
    
    try:
        demo_basic_operations()
        demo_transaction()
        demo_bulk_operations()
        demo_connection_pool()
        demo_retry_logic()
        demo_env_config()
        
        print("\n" + "=" * 60)
        print("✅ ALL DEMOS COMPLETED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

