from onuslibs.db import execute, bulk_insert, query

execute("""
CREATE TABLE IF NOT EXISTS tmp_demo (
  id INT PRIMARY KEY,
  name VARCHAR(50),
  score INT,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""")

bulk_insert("tmp_demo", [
  {"id": 1, "name": "Alice", "score": 10},
  {"id": 2, "name": "Bob",   "score":  8},
  {"id": 1, "name": "Alice", "score": 10},  # trùng khóa → INSERT IGNORE mặc định sẽ bỏ qua
])

execute("UPDATE tmp_demo SET score=score+1 WHERE id=%s", (1,))
print(query("SELECT * FROM tmp_demo ORDER BY id;"))
