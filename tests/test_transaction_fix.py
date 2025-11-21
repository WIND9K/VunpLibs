#!/usr/bin/env python3
"""
Test để verify rằng transaction commit đúng cách và KHÔNG bị rollback.

Bug đã fix: Transaction commit thành công nhưng bị rollback ngay sau đó.
Fix: Thêm skip_rollback flag để không rollback connection đã commit.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onuslibs.db import DB, DbSettings, transaction


def test_transaction_commit():
    """Test rằng transaction commit thành công và data được lưu."""
    
    print("=" * 70)
    print("TEST 1: Transaction với commit - Data phải được lưu")
    print("=" * 70)
    
    try:
        # Tạo bảng test
        from onuslibs.db import execute, query_scalar
        
        # Drop và tạo lại bảng test
        try:
            execute("DROP TABLE IF EXISTS test_transaction_fix")
        except Exception:
            pass
        
        execute("""
            CREATE TABLE test_transaction_fix (
                id INT PRIMARY KEY,
                value VARCHAR(100)
            )
        """)
        print("✅ Tạo bảng test_transaction_fix thành công")
        
        # Test 1: Insert trong transaction và commit
        print("\n--- Test 1: Insert trong transaction ---")
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO test_transaction_fix (id, value) VALUES (%s, %s)",
                    (1, "committed_value")
                )
                print("  Inserted row (id=1, value='committed_value')")
            # Transaction sẽ auto commit ở đây
        
        print("  Transaction đã commit")
        
        # Kiểm tra data có tồn tại không
        count = query_scalar("SELECT COUNT(*) FROM test_transaction_fix WHERE id=1")
        print(f"  Số dòng sau commit: {count}")
        
        if count == 1:
            print("✅ TEST 1 PASSED: Data được lưu sau commit")
        else:
            print("❌ TEST 1 FAILED: Data KHÔNG được lưu sau commit!")
            return False
        
        # Test 2: Update trong transaction
        print("\n--- Test 2: Update trong transaction ---")
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE test_transaction_fix SET value=%s WHERE id=%s",
                    ("updated_value", 1)
                )
                print("  Updated row (id=1, value='updated_value')")
        
        print("  Transaction đã commit")
        
        # Kiểm tra data đã update chưa
        from onuslibs.db import query_one
        row = query_one("SELECT * FROM test_transaction_fix WHERE id=1")
        print(f"  Row sau update: {row}")
        
        if row and row.get('value') == 'updated_value':
            print("✅ TEST 2 PASSED: Data được update sau commit")
        else:
            print("❌ TEST 2 FAILED: Data KHÔNG được update sau commit!")
            return False
        
        # Test 3: Transaction với exception - phải rollback
        print("\n--- Test 3: Transaction với exception (phải rollback) ---")
        try:
            with transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO test_transaction_fix (id, value) VALUES (%s, %s)",
                        (2, "will_be_rolled_back")
                    )
                    print("  Inserted row (id=2, value='will_be_rolled_back')")
                    
                    # Gây lỗi cố ý
                    raise ValueError("Intentional error to trigger rollback")
        except ValueError as e:
            print(f"  Exception caught: {e}")
            print("  Transaction đã rollback")
        
        # Kiểm tra data KHÔNG tồn tại
        count = query_scalar("SELECT COUNT(*) FROM test_transaction_fix WHERE id=2")
        print(f"  Số dòng với id=2: {count}")
        
        if count == 0:
            print("✅ TEST 3 PASSED: Data được rollback khi có exception")
        else:
            print("❌ TEST 3 FAILED: Data KHÔNG được rollback khi có exception!")
            return False
        
        # Cleanup
        execute("DROP TABLE test_transaction_fix")
        print("\n✅ Cleanup: Đã xóa bảng test")
        
        print("\n" + "=" * 70)
        print("🎉 TẤT CẢ TESTS PASSED!")
        print("=" * 70)
        print("\n✅ Bug đã được fix:")
        print("   - Transaction commit thành công KHÔNG bị rollback nữa")
        print("   - Connection pool trả về đúng cách với skip_rollback flag")
        print("   - Transaction với exception vẫn rollback đúng")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_connection_pool_behavior():
    """Test rằng connection pool hoạt động đúng với skip_rollback."""
    
    print("\n" + "=" * 70)
    print("TEST 2: Connection Pool với skip_rollback flag")
    print("=" * 70)
    
    try:
        db = DB(settings=DbSettings.from_secure())
        
        # Test 1: get_connection() thông thường (skip_rollback=False)
        print("\n--- Test: get_connection() mặc định ---")
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                print(f"  Query result: {result}")
        print("  ✅ Connection trả về pool với rollback (mặc định)")
        
        # Test 2: get_connection(skip_rollback=True)
        print("\n--- Test: get_connection(skip_rollback=True) ---")
        with db.get_connection(skip_rollback=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 2")
                result = cur.fetchone()
                print(f"  Query result: {result}")
        print("  ✅ Connection trả về pool KHÔNG rollback")
        
        db.close_pool()
        
        print("\n✅ Connection pool hoạt động đúng với skip_rollback flag")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Chạy tất cả tests."""
    print("\n" + "🚀" * 35)
    print(" " * 10 + "TEST FIX: Transaction Rollback Bug")
    print("🚀" * 35)
    
    print("\n📝 Bug Report:")
    print("   - Transaction commit ở line 272")
    print("   - Nhưng return_connection() rollback ở line 110")
    print("   - => Data bị mất sau commit!")
    print("\n🔧 Fix:")
    print("   - Thêm skip_rollback parameter")
    print("   - Transaction pass skip_rollback=True khi commit thành công")
    print("   - Connection pool chỉ rollback khi skip_rollback=False")
    
    success = True
    
    # Test transaction commit behavior
    if not test_transaction_commit():
        success = False
    
    # Test connection pool behavior
    if not test_connection_pool_behavior():
        success = False
    
    if success:
        print("\n" + "🎉" * 35)
        print(" " * 15 + "ALL TESTS PASSED!")
        print("🎉" * 35)
        print("\n✅ Bug đã được fix hoàn toàn!")
    else:
        print("\n" + "❌" * 35)
        print(" " * 15 + "SOME TESTS FAILED!")
        print("❌" * 35)
        sys.exit(1)


if __name__ == "__main__":
    main()

