# 📝 Hướng dẫn cấu hình Database Module v3.1

## 🎯 Tổng quan

Module DB v3.1 có **3 cấu hình mới** để tối ưu hiệu suất:

1. **`ONUSLIBS_DB_POOL_SIZE`** - Số connections trong pool
2. **`ONUSLIBS_DB_MAX_OVERFLOW`** - Số connections tối đa thêm
3. **`ONUSLIBS_DB_RETRY_COUNT`** - Số lần retry khi lỗi

---

## ⚙️ Cấu hình cơ bản

### File `.env` (Khuyến nghị)

Thêm các dòng sau vào file `.env` của bạn:

```bash
# Database connection (CŨ - vẫn cần)
ONUSLIBS_DB_HOST=127.0.0.1
ONUSLIBS_DB_PORT=3306
ONUSLIBS_DB_USER=onusreport
ONUSLIBS_DB_PASSWORD=your_password
ONUSLIBS_DB_NAME=onusreport
ONUSLIBS_DB_CONNECT_TIMEOUT=10
ONUSLIBS_DB_SSL_CA=

# Connection Pool (MỚI v3.1) ⚡
ONUSLIBS_DB_POOL_SIZE=5
ONUSLIBS_DB_MAX_OVERFLOW=10
ONUSLIBS_DB_RETRY_COUNT=3
```

### Hoặc dùng Keyring

```powershell
# PowerShell (Windows)
$svc="OnusLibs"
python -c "import keyring; keyring.set_password('$svc', 'DB_HOST', '127.0.0.1')"
python -c "import keyring; keyring.set_password('$svc', 'DB_PORT', '3306')"
python -c "import keyring; keyring.set_password('$svc', 'DB_USER', 'onusreport')"
python -c "import keyring; keyring.set_password('$svc', 'DB_PASSWORD', 'xxx')"
python -c "import keyring; keyring.set_password('$svc', 'DB_NAME', 'onusreport')"
python -c "import keyring; keyring.set_password('$svc', 'DB_POOL_SIZE', '5')"
python -c "import keyring; keyring.set_password('$svc', 'DB_MAX_OVERFLOW', '10')"
python -c "import keyring; keyring.set_password('$svc', 'DB_RETRY_COUNT', '3')"
```

```bash
# Bash (Linux/Mac)
svc="OnusLibs"
python -c "import keyring; keyring.set_password('$svc', 'DB_HOST', '127.0.0.1')"
python -c "import keyring; keyring.set_password('$svc', 'DB_PORT', '3306')"
python -c "import keyring; keyring.set_password('$svc', 'DB_USER', 'onusreport')"
python -c "import keyring; keyring.set_password('$svc', 'DB_PASSWORD', 'xxx')"
python -c "import keyring; keyring.set_password('$svc', 'DB_NAME', 'onusreport')"
python -c "import keyring; keyring.set_password('$svc', 'DB_POOL_SIZE', '5')"
python -c "import keyring; keyring.set_password('$svc', 'DB_MAX_OVERFLOW', '10')"
python -c "import keyring; keyring.set_password('$svc', 'DB_RETRY_COUNT', '3')"
```

---

## 🎨 Giá trị khuyến nghị theo môi trường

### 🔧 Development

```bash
# Ít connections, dễ debug
ONUSLIBS_DB_POOL_SIZE=3
ONUSLIBS_DB_MAX_OVERFLOW=5
ONUSLIBS_DB_RETRY_COUNT=2
```

**Lý do:**
- Pool nhỏ tiết kiệm tài nguyên
- Dễ debug connection issues
- Ít overhead

### 🧪 Staging

```bash
# Cân bằng giữa dev và prod
ONUSLIBS_DB_POOL_SIZE=8
ONUSLIBS_DB_MAX_OVERFLOW=15
ONUSLIBS_DB_RETRY_COUNT=3
```

**Lý do:**
- Giống production nhưng nhẹ hơn
- Test performance trước khi lên prod
- Đủ mạnh cho load testing

### 🚀 Production

```bash
# Pool lớn cho high-load
ONUSLIBS_DB_POOL_SIZE=20
ONUSLIBS_DB_MAX_OVERFLOW=50
ONUSLIBS_DB_RETRY_COUNT=5
```

**Lý do:**
- Handle traffic cao
- Nhiều retry cho độ tin cậy
- Tối ưu cho concurrent requests

### ⚡ High-Performance Production

```bash
# Cực kỳ high-load (e.g., ETL pipeline 24/7)
ONUSLIBS_DB_POOL_SIZE=50
ONUSLIBS_DB_MAX_OVERFLOW=100
ONUSLIBS_DB_RETRY_COUNT=5
ONUSLIBS_DB_CONNECT_TIMEOUT=30
```

**Lý do:**
- ETL jobs xử lý hàng triệu dòng
- Nhiều concurrent workers
- Cần connection pool lớn

---

## 📊 Chi tiết các tham số

### 1. `ONUSLIBS_DB_POOL_SIZE`

**Mô tả:** Số connections **tối thiểu** luôn sẵn sàng trong pool

**Mặc định:** `5`

**Hoạt động:**
- Khi khởi động, tạo sẵn N connections
- Connections này được giữ sống và reuse
- Không đóng khi idle

**Chọn giá trị:**
```
Công thức: pool_size = số_workers_concurrent × 1.5

Ví dụ:
- 2 workers → pool_size = 3
- 5 workers → pool_size = 8
- 10 workers → pool_size = 15
- 20 workers → pool_size = 30
```

**Ví dụ:**
```python
# Application với 8 concurrent workers
ONUSLIBS_DB_POOL_SIZE=12  # 8 × 1.5
```

---

### 2. `ONUSLIBS_DB_MAX_OVERFLOW`

**Mô tả:** Số connections **tối đa** có thể tạo **thêm** khi pool đầy

**Mặc định:** `10`

**Hoạt động:**
- Khi pool đầy (đã dùng hết `POOL_SIZE` connections)
- Cho phép tạo thêm tối đa `MAX_OVERFLOW` connections
- Connections này sẽ được đóng sau khi dùng xong (không giữ lại)

**Tổng connections tối đa:**
```
max_connections = POOL_SIZE + MAX_OVERFLOW

Ví dụ:
POOL_SIZE=10 + MAX_OVERFLOW=20 = 30 connections tối đa
```

**Chọn giá trị:**
```
Công thức: max_overflow = pool_size × 2

Ví dụ:
- pool_size=5  → max_overflow=10
- pool_size=10 → max_overflow=20
- pool_size=20 → max_overflow=40
```

**Ví dụ:**
```python
# Normal load: 10 connections
# Peak load: có thể lên 30 connections
ONUSLIBS_DB_POOL_SIZE=10
ONUSLIBS_DB_MAX_OVERFLOW=20
```

---

### 3. `ONUSLIBS_DB_RETRY_COUNT`

**Mô tả:** Số lần retry khi gặp lỗi **tạm thời**

**Mặc định:** `3`

**Tự động retry khi gặp:**
- **1205**: Lock wait timeout exceeded
- **1213**: Deadlock found when trying to get lock
- **2006**: MySQL server has gone away
- **2013**: Lost connection to MySQL server during query
- **InterfaceError**: Connection interface errors

**Hoạt động:**
- Retry với exponential backoff
- Lần 1: sleep 0.5s
- Lần 2: sleep 1.0s
- Lần 3: sleep 1.5s
- ...

**Chọn giá trị:**
```
Development: 2    (fail fast để debug)
Staging:     3    (cân bằng)
Production:  5    (độ tin cậy cao)
Critical:    7    (cực kỳ quan trọng)
```

**Ví dụ:**
```python
# ETL pipeline không được phép fail
ONUSLIBS_DB_RETRY_COUNT=7
```

---

## 🎯 Tình huống cụ thể

### Tình huống 1: Web API với traffic thấp

```bash
# 100-500 requests/phút
ONUSLIBS_DB_POOL_SIZE=3
ONUSLIBS_DB_MAX_OVERFLOW=7
ONUSLIBS_DB_RETRY_COUNT=3
```

### Tình huống 2: Web API với traffic cao

```bash
# 1000+ requests/phút
ONUSLIBS_DB_POOL_SIZE=20
ONUSLIBS_DB_MAX_OVERFLOW=40
ONUSLIBS_DB_RETRY_COUNT=5
```

### Tình huống 3: ETL Job chạy hàng đêm

```bash
# Xử lý hàng triệu records
ONUSLIBS_DB_POOL_SIZE=15
ONUSLIBS_DB_MAX_OVERFLOW=30
ONUSLIBS_DB_RETRY_COUNT=5
ONUSLIBS_DB_CONNECT_TIMEOUT=30
```

### Tình huống 4: Real-time Analytics

```bash
# Nhiều concurrent queries
ONUSLIBS_DB_POOL_SIZE=30
ONUSLIBS_DB_MAX_OVERFLOW=50
ONUSLIBS_DB_RETRY_COUNT=3
```

### Tình huống 5: Background Workers (Celery, RQ)

```bash
# 10 workers, mỗi worker có thể dùng 2 connections
ONUSLIBS_DB_POOL_SIZE=20
ONUSLIBS_DB_MAX_OVERFLOW=40
ONUSLIBS_DB_RETRY_COUNT=5
```

---

## ⚠️ Cảnh báo & Lưu ý

### 1. Không đặt pool quá lớn

**❌ Không tốt:**
```bash
ONUSLIBS_DB_POOL_SIZE=1000  # Quá lớn!
```

**Vấn đề:**
- Tốn RAM (mỗi connection ~1-2MB)
- MySQL có giới hạn `max_connections` (thường 150-500)
- Hầu hết connections idle, lãng phí

**✅ Tốt:**
```bash
# Chỉ giữ số connections cần thiết
ONUSLIBS_DB_POOL_SIZE=20
```

---

### 2. Kiểm tra `max_connections` của MySQL

```sql
-- Xem giới hạn hiện tại
SHOW VARIABLES LIKE 'max_connections';

-- Xem số connections đang dùng
SHOW STATUS LIKE 'Threads_connected';
```

**Quy tắc:**
```
pool_size + max_overflow < mysql_max_connections × 0.8

Ví dụ:
MySQL max_connections = 200
OnusLibs max = 200 × 0.8 = 160
→ POOL_SIZE=50 + MAX_OVERFLOW=100 = 150 ✅
```

---

### 3. Monitor pool usage

```python
from onuslibs.db import DB, DbSettings

db = DB(settings=DbSettings.from_secure())

# Check pool stats (future feature)
# print(f"Pool size: {db._pool._created}")
# print(f"In use: {db._pool._in_use}")
```

---

## 🧪 Test cấu hình

### Script test pool

```python
#!/usr/bin/env python3
"""Test DB pool configuration."""

from onuslibs.db import DB, DbSettings
import time
import concurrent.futures

def test_query(i):
    """Thực hiện 1 query."""
    db = DB(settings=DbSettings.from_secure())
    start = time.time()
    result = db.query_scalar("SELECT 1")
    elapsed = time.time() - start
    print(f"Query {i}: {elapsed:.3f}s")
    return result

def main():
    print("Testing DB pool with 20 concurrent queries...")
    
    start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(test_query, i) for i in range(20)]
        results = [f.result() for f in futures]
    
    elapsed = time.time() - start
    
    print(f"\n✅ Completed {len(results)} queries in {elapsed:.2f}s")
    print(f"   Average: {elapsed/len(results):.3f}s per query")

if __name__ == "__main__":
    main()
```

**Chạy test:**
```bash
python test_pool.py
```

**Kết quả mong đợi:**
```
Testing DB pool with 20 concurrent queries...
Query 0: 0.052s
Query 1: 0.048s
...
✅ Completed 20 queries in 0.5s
   Average: 0.025s per query
```

---

## 📋 Checklist nâng cấp

- [ ] Thêm 3 biến mới vào `.env`:
  - `ONUSLIBS_DB_POOL_SIZE`
  - `ONUSLIBS_DB_MAX_OVERFLOW`
  - `ONUSLIBS_DB_RETRY_COUNT`

- [ ] Chọn giá trị phù hợp với môi trường (dev/staging/prod)

- [ ] Kiểm tra `max_connections` của MySQL

- [ ] Test với script benchmark

- [ ] Monitor performance sau khi deploy

- [ ] Document cấu hình cho team

---

## 🎓 Tóm tắt

### Cấu hình tối thiểu (đã có sẵn giá trị mặc định):

Bạn **KHÔNG CẦN** thêm gì nếu muốn dùng mặc định:
- `POOL_SIZE=5`
- `MAX_OVERFLOW=10`
- `RETRY_COUNT=3`

### Cấu hình cho Production (khuyến nghị):

```bash
ONUSLIBS_DB_POOL_SIZE=20
ONUSLIBS_DB_MAX_OVERFLOW=50
ONUSLIBS_DB_RETRY_COUNT=5
```

### File template đầy đủ:

Xem file `ENV_CONFIG_TEMPLATE.env` để copy vào `.env` của bạn.

---

**Có thắc mắc?** Xem thêm:
- `DB_MODULE_QUICK_START.md` - Hướng dẫn nhanh
- `DB_MODULE_V3.1_SUMMARY_VI.md` - Tổng hợp đầy đủ
- `examples/db_enhanced_demo.py` - Demo code

