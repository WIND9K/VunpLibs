from datetime import date
from typing import Union

DateLike = Union[str, date]

def build_date_period(start_date: DateLike, end_date: DateLike) -> str:
    """
    Ghép 2 ngày (YYYY-MM-DD hoặc datetime.date) thành datePeriod full-day
    dạng chuẩn Cyclos, ví dụ:

      build_date_period("2025-10-11", "2025-10-13")
      -> '2025-10-11T00:00:00.000,2025-10-13T23:59:59.999'
    """
    if isinstance(start_date, date):
        start_str = start_date.strftime("%Y-%m-%d")
    else:
        start_str = start_date

    if isinstance(end_date, date):
        end_str = end_date.strftime("%Y-%m-%d")
    else:
        end_str = end_date

    return f"{start_str}T00:00:00.000,{end_str}T23:59:59.999"
