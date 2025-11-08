# tools/write_csv.py
from __future__ import annotations

import csv
import json
from typing import Any, Iterable, List, Dict, Optional
from datetime import date, datetime
from decimal import Decimal

__all__ = ["write_csv", "collect_fields", "flatten_record"]

# ==== encoder để chuẩn hoá giá trị trước khi ghi CSV ====
def _default_encoder(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)

# ==== flatten 1 bản ghi (dict) theo dot-path, list => json ====
def flatten_record(record: Dict[str, Any], *, sep: str = ".") -> Dict[str, Any]:
    """
    Chuyển dict lồng nhau thành dict phẳng theo dot-path.
    - dict lồng → dồn key kiểu "a.b.c"
    - list/tuple/set → json.dumps để giữ nguyên cấu trúc
    """
    flat: Dict[str, Any] = {}

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                key = k if not prefix else f"{prefix}{sep}{k}"
                _walk(key, v)
        elif isinstance(value, (list, tuple, set)):
            flat[prefix] = json.dumps(_default_encoder(value), ensure_ascii=False)
        else:
            flat[prefix] = _default_encoder(value)

    _walk("", record or {})
    return flat

def collect_fields(rows: Iterable[Dict[str, Any]]) -> List[str]:
    """
    Dò toàn bộ cột (dot-path) có trong tập dữ liệu sau khi flatten.
    Dùng khi bạn muốn auto lấy tất cả cột.
    """
    cols: set[str] = set()
    for r in rows:
        for k in flatten_record(r).keys():
            cols.add(k)
    return sorted(cols)

def _normalize_fields(fields: Optional[Iterable[str] | str], rows: List[Dict[str, Any]]) -> List[str]:
    if not fields:
        return collect_fields(rows)
    if isinstance(fields, str):
        f = [p.strip() for p in fields.split(",") if p.strip()]
        return f
    return [str(x).strip() for x in fields if str(x).strip()]

def write_csv(
    rows: Iterable[Dict[str, Any]],
    path: str,
    *,
    fields: Optional[Iterable[str] | str] = None,
    include_header: bool = True,
    newline: str = "",
    encoding: str = "utf-8-sig",  # Excel-friendly BOM
) -> int:
    """
    Ghi toàn bộ kết quả API (list[dict]) ra CSV, tự flatten nested dict bằng dot-path.

    Args:
      rows: Iterable[dict] kết quả (ví dụ từ fetch_json).
      path: đường dẫn file CSV cần ghi.
      fields: danh sách cột (dot-path) muốn ghi; nếu None → tự dò toàn bộ cột.
      include_header: ghi dòng header hay không.
      newline, encoding: tuỳ chỉnh ghi file.

    Returns:
      Số dòng dữ liệu đã ghi.
    """
    # Materialize rows để có thể duyệt 2 lần (collect fields & write)
    data: List[Dict[str, Any]] = list(rows or [])
    if not data:
        # tạo file rỗng với header nếu có fields truyền vào
        cols = _normalize_fields(fields, [])
        with open(path, "w", newline=newline, encoding=encoding) as f:
            if cols and include_header:
                writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                writer.writeheader()
        return 0

    cols = _normalize_fields(fields, data)

    # Flatten toàn bộ trước khi ghi
    flat_rows = [flatten_record(r) for r in data]

    # Nếu người dùng không chỉ định fields, dùng union keys từ dữ liệu để đảm bảo đủ cột
    if not fields:
        # tái thu thập sau flatten, tránh thiếu key mới sinh
        cols = sorted({k for fr in flat_rows for k in fr.keys()})

    with open(path, "w", newline=newline, encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if include_header:
            writer.writeheader()
        count = 0
        for fr in flat_rows:
            # điền None cho cột thiếu
            row = {c: fr.get(c, None) for c in cols}
            writer.writerow(row)
            count += 1
    return count
