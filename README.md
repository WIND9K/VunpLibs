# OnusLibs v2 (CLEAN)

- **Thay thế hoàn toàn** code cũ. Không còn alias ENV cũ (`ONUSLIBS_TOKEN`, `ONUSLIBS_BASE_URL`, ...).
- Giao diện **1 hàm** `fetch(...)` cho phân trang `datePeriod` (page=0) theo ngày + `max(date)+epsilon`.
- Bảo mật: token qua **ONUSLIBS_ACCESS_CLIENT_TOKEN** (ENV/.env) hoặc **Keyring**; log có **redaction**.

## Cài đặt
```bash
pip install httpx tenacity pydantic pydantic-settings structlog keyring
# nếu dùng CSV/DB:
pip install pandas SQLAlchemy pymysql
```

## .env mẫu (chỉ khóa mới v2)
```dotenv
ONUSLIBS_ACCESS_CLIENT_TOKEN=your-access-client-token
ONUSLIBS_WALLET_BASE=https://wallet.vndc.io

# DB (nếu dùng to_db)
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=onus
DB_PASSWORD=secret
DB_NAME=onusdb
```

## Quick Start
```python
from datetime import datetime
from onuslibs import fetch

items = list(fetch(
    start=datetime(2025,10,10),
    end=datetime(2025,10,11,23,59,59),
    endpoint="/api/vndc_commission/accounts/vndc_commission_acc/history",
    filters={"chargedBack":"false","transferFilters":"vndc_commission_acc.commission_buysell"},
))
print(len(items))
```
