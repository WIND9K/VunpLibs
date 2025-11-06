import sys, pathlib
# Nếu chạy script từ ngoài app, bật dòng dưới để ưu tiên import onuslibs ở repo cha:
# sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from onuslibs.db import healthcheck, query, execute, bulk_insert, transactional

SCHEMA = "onusreport"
TABLE  = f"{SCHEMA}.tmp_onuslibs_smoke"

def main():
    # 1) Kết nối qua Keyring
    assert healthcheck() is True, "Healthcheck FAIL: kiểm tra Keyring & quyền DB"

    # 2) Tạo bảng tạm (nếu chưa có)
    execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
      id INT PRIMARY KEY,
      name VARCHAR(50),
      score INT,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # 3) Xoá dữ liệu cũ của test (nếu có)
    execute(f"DELETE FROM {TABLE} WHERE id BETWEEN %s AND %s", (1001, 1003))

    # 4) Ghi dữ liệu (INSERT IGNORE mặc định để tránh 1062)
    rows = [
        {"id": 1001, "name": "Alice", "score": 10},
        {"id": 1002, "name": "Bob",   "score":  8},
        {"id": 1003, "name": "Cathy", "score":  9},
    ]
    aff = bulk_insert(TABLE, rows, insert_ignore=True)  # insert_ignore=True là mặc định
    print("INSERT affected:", aff)

    # 5) Đọc lại
    print("READ all:", query(f"SELECT * FROM {TABLE} ORDER BY id;"))

    # 6) Update 1 dòng
    execute(f"UPDATE {TABLE} SET score = score + 1 WHERE id = %s", (1001,))
    print("READ id=1001:", query(f"SELECT * FROM {TABLE} WHERE id=1001;"))

    # 7) Delete 1 dòng
    execute(f"DELETE FROM {TABLE} WHERE id = %s", (1003,))
    print("READ after delete:", query(f"SELECT * FROM {TABLE} ORDER BY id;"))

    # 8) Transactional + rollback test (cố tình gây lỗi trùng PK)
    try:
        with transactional() as cur:
            cur.execute(f"INSERT INTO {TABLE} (id,name,score) VALUES (%s,%s,%s)", (1002, "dup", 999))
            cur.execute(f"INSERT INTO {TABLE} (id,name,score) VALUES (%s,%s,%s)", (1002, "dup2", 1000))
            # dòng 2 trùng khoá -> raise -> rollback toàn bộ block
    except Exception as e:
        print("TX rollback ok ->", type(e).__name__, str(e)[:120])

    print("READ final:", query(f"SELECT * FROM {TABLE} ORDER BY id;"))

    # (Tuỳ chọn) Đọc sample bảng thật để xác nhận quyền SELECT trong schema onusreport
    # print("SAMPLE:", query("SELECT * FROM onusreport.buy_sell_diary LIMIT 1;"))

if __name__ == "__main__":
    main()
