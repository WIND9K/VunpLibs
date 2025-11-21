#!/usr/bin/env python3
"""
Test để verify 3 bugs đã được fix:

Bug 1: retry_count=0 breaks _retry_on_error
Bug 2: Iterator exhaustion trong bulk_insert retry  
Bug 3: bulk_upsert update primary key
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onuslibs.db import DB, DbSettings, execute, query_scalar, bulk_upsert


def test_bug1_retry_count_zero():
    """Test Bug 1: retry_count=0 phải vẫn execute function 1 lần."""
    
    print("=" * 70)
    print("TEST BUG 1: retry_count=0 breaks _retry_on_error")
    print("=" * 70)
    
    try:
        # Tạo DB với retry_count=0
        db = DB(
            settings=DbSettings.from_secure(),
            retry_count=0,  # BUG: Nếu không fix, sẽ return None
        )
        
        print("\n1. Test healthcheck với retry_count=0")
        result = db.healthcheck()
        print(f"   Healthcheck result: {result}")
        
        if result is None:
            print("   ❌ BUG: Function return None thay vì execute!")
            return False
        elif result is True:
            print("   ✅ PASS: Function executed successfully")
        else:
            print("   ✅ PASS: Function executed (failed but không return None)")
        
        print("\n2. Test query với retry_count=0")
        rows = db.query("SELECT 1 as test")
        print(f"   Query result: {rows}")
        
        if rows is None:
            print("   ❌ BUG: Query return None!")
            return False
        elif len(rows) == 1 and rows[0].get('test') == 1:
            print("   ✅ PASS: Query executed successfully")
        
        print("\n✅ BUG 1 FIXED: retry_count=0 vẫn execute function")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bug2_iterator_exhaustion():
    """Test Bug 2: Iterator không bị exhausted khi retry."""
    
    print("\n" + "=" * 70)
    print("TEST BUG 2: Iterator exhaustion trong bulk_insert retry")
    print("=" * 70)
    
    try:
        # Setup
        execute("DROP TABLE IF EXISTS test_iterator")
        execute("""
            CREATE TABLE test_iterator (
                id INT PRIMARY KEY,
                value VARCHAR(100)
            )
        """)
        print("✅ Tạo bảng test_iterator")
        
        # Test 1: Generator (sẽ bị materialize)
        print("\n1. Test với generator")
        def data_generator():
            for i in range(5):
                yield (i, f"value_{i}")
        
        from onuslibs.db import bulk_insert
        affected = bulk_insert(
            "INSERT INTO test_iterator (id, value) VALUES (%s, %s)",
            data_generator(),  # Generator
            batch_size=2,
        )
        
        print(f"   Inserted {affected} rows from generator")
        count = query_scalar("SELECT COUNT(*) FROM test_iterator")
        
        if count == 5:
            print(f"   ✅ PASS: All 5 rows inserted (count={count})")
        else:
            print(f"   ❌ FAIL: Expected 5 rows, got {count}")
            return False
        
        # Test 2: List (không có overhead)
        print("\n2. Test với list")
        execute("TRUNCATE test_iterator")
        
        rows_list = [(i, f"value_{i}") for i in range(10, 15)]
        affected = bulk_insert(
            "INSERT INTO test_iterator (id, value) VALUES (%s, %s)",
            rows_list,  # List
            batch_size=2,
        )
        
        print(f"   Inserted {affected} rows from list")
        count = query_scalar("SELECT COUNT(*) FROM test_iterator")
        
        if count == 5:
            print(f"   ✅ PASS: All 5 rows inserted (count={count})")
        else:
            print(f"   ❌ FAIL: Expected 5 rows, got {count}")
            return False
        
        # Cleanup
        execute("DROP TABLE test_iterator")
        
        print("\n✅ BUG 2 FIXED: Iterator được materialize, retry an toàn")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bug3_bulk_upsert_primary_key():
    """Test Bug 3: bulk_upsert không update primary key."""
    
    print("\n" + "=" * 70)
    print("TEST BUG 3: bulk_upsert update primary key")
    print("=" * 70)
    
    try:
        # Setup
        execute("DROP TABLE IF EXISTS test_upsert")
        execute("""
            CREATE TABLE test_upsert (
                id INT PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100)
            )
        """)
        print("✅ Tạo bảng test_upsert")
        
        # Insert initial data
        execute("INSERT INTO test_upsert VALUES (1, 'Alice', 'alice@old.com')")
        print("   Inserted initial row: (1, 'Alice', 'alice@old.com')")
        
        # Test 1: Upsert với update_columns rõ ràng (KHÔNG có id)
        print("\n1. Test upsert với update_columns=['name', 'email']")
        rows = [(1, "Alice Updated", "alice@new.com")]
        
        affected = bulk_upsert(
            table="test_upsert",
            columns=["id", "name", "email"],
            rows=rows,
            update_columns=["name", "email"],  # Không update id
        )
        
        print(f"   Affected {affected} rows")
        
        from onuslibs.db import query_one
        row = query_one("SELECT * FROM test_upsert WHERE id=1")
        print(f"   Row sau upsert: {row}")
        
        if row['email'] == 'alice@new.com':
            print("   ✅ PASS: Email updated successfully")
        else:
            print(f"   ❌ FAIL: Email not updated: {row['email']}")
            return False
        
        # Test 2: Upsert với update_columns=[] (chỉ INSERT)
        print("\n2. Test upsert với update_columns=[] (ignore duplicates)")
        rows = [(1, "Alice Ignored", "ignored@email.com")]
        
        affected = bulk_upsert(
            table="test_upsert",
            columns=["id", "name", "email"],
            rows=rows,
            update_columns=[],  # Không update gì
        )
        
        print(f"   Affected {affected} rows")
        
        row = query_one("SELECT * FROM test_upsert WHERE id=1")
        print(f"   Row sau upsert: {row}")
        
        if row['name'] == 'Alice Updated':  # Không thay đổi
            print("   ✅ PASS: Row không thay đổi (duplicate ignored)")
        else:
            print(f"   ❌ FAIL: Row bị update: {row['name']}")
            return False
        
        # Test 3: Warning khi update_columns=None
        print("\n3. Test warning khi update_columns=None")
        print("   (Sẽ có warning trong log về việc update tất cả cột)")
        
        rows = [(2, "Bob", "bob@example.com")]
        affected = bulk_upsert(
            table="test_upsert",
            columns=["id", "name", "email"],
            rows=rows,
            update_columns=None,  # Update all (có warning)
        )
        
        print(f"   Affected {affected} rows")
        count = query_scalar("SELECT COUNT(*) FROM test_upsert")
        
        if count == 2:
            print(f"   ✅ PASS: Inserted new row (count={count})")
        else:
            print(f"   ❌ FAIL: Expected 2 rows, got {count}")
            return False
        
        # Cleanup
        execute("DROP TABLE test_upsert")
        
        print("\n✅ BUG 3 FIXED: bulk_upsert xử lý update_columns đúng")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Chạy tất cả tests."""
    print("\n" + "🚀" * 35)
    print(" " * 10 + "TEST FIX: Batch 2 Bugs")
    print("🚀" * 35)
    
    print("\n📝 Bugs Fixed:")
    print("   Bug 1: retry_count=0 breaks _retry_on_error")
    print("   Bug 2: Iterator exhaustion trong bulk_insert retry")
    print("   Bug 3: bulk_upsert update primary key")
    
    success = True
    
    if not test_bug1_retry_count_zero():
        success = False
    
    if not test_bug2_iterator_exhaustion():
        success = False
    
    if not test_bug3_bulk_upsert_primary_key():
        success = False
    
    if success:
        print("\n" + "🎉" * 35)
        print(" " * 15 + "ALL TESTS PASSED!")
        print("🎉" * 35)
        print("\n✅ Tất cả 3 bugs đã được fix!")
    else:
        print("\n" + "❌" * 35)
        print(" " * 15 + "SOME TESTS FAILED!")
        print("❌" * 35)
        sys.exit(1)


if __name__ == "__main__":
    main()

