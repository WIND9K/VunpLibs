from onuslibs.db import query, healthcheck

assert healthcheck() is True, "Healthcheck FAIL – kiểm tra Keyring/quyền DB"

# Nếu cột date_utc là DATETIME/TIMESTAMP → dùng range để tận dụng index:
SQL = """
SELECT *
FROM onusreport.onchain_diary
WHERE date_utc >= %s AND date_utc < %s
"""
params = ("2025-10-20 00:00:00", "2025-10-31 00:00:00")

# Nếu cột date_utc là DATE, bạn có thể đổi sang:
# SQL = "SELECT * FROM onusreport.onchain_diary WHERE date_utc = %s"
# params = ("2025-10-30",)

rows = query(SQL, params)
print("Tổng dòng:", len(rows))
for r in rows[:5]:
    print(r)
