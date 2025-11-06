import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone
from onuslibs import fetch_all
from onuslibs.settings import OnusSettings  # chỉ để validate ENV
from dotenv import load_dotenv
load_dotenv()  # tự động đọc .env

def main():
    # Validate ENV (tự động raise nếu thiếu)
    _ = OnusSettings()

    start = datetime(2025, 10, 10, 0, 0, 0, tzinfo=timezone.utc)
    end   = datetime(2025, 10, 11, 23, 59, 59, tzinfo=timezone.utc)

    rows = fetch_all(
        endpoint="/api/vndc_commission/accounts/vndc_commission_acc/history",
        start=start, end=end,
        filters={"chargedBack":"false","transferFilters":"vndc_commission_acc.commission_buysell"},
        fields=["date","transactionNumber","relatedAccount.user.id","relatedAccount.user.display","amount"],
        page_size=10000, day_workers=2, req_per_sec=3.0, http2=True, timeout_s=30.0,
        force_segmented_paging=True, segment_safety_ratio=0.95, segment_min_seconds=1.0,
    )
    print(len(rows))

if __name__ == "__main__":
    main()
