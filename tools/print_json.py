# tools/print_json.py
from __future__ import annotations

import json
import sys
from typing import Any, Optional
from datetime import date, datetime
from decimal import Decimal

# ===== encoder mặc định để dump được nhiều kiểu dữ liệu phổ biến =====
def _default_encoder(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    # Thử có __dict__ (vd: dataclass, object đơn giản)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    # fallback
    return str(obj)

def print_json(
    data: Any,
    *,
    sort_keys: bool = False,
    indent: int = 2,
    ensure_ascii: bool = False,
    to_file: Optional[str] = None,
    color: bool = True,
) -> None:
    """
    In đối tượng Python ra JSON “đẹp” (pretty print).

    Args:
      data: dict/list/... cần in ra.
      sort_keys: sắp xếp key (mặc định False).
      indent: số khoảng trắng thụt lề (mặc định 2).
      ensure_ascii: True → escape Unicode; False → in tiếng Việt đẹp (mặc định False).
      to_file: nếu truyền đường dẫn, ghi JSON ra file thay vì stdout.
      color: nếu True và có pygments → in có màu.

    Ví dụ:
      print_json({"a": 1, "tên": "Tiên"}, sort_keys=True)
      print_json(rows, to_file="out.json")
    """
    # ưu tiên orjson nếu có (nhanh), rồi json tiêu chuẩn
    try:
        import orjson  # type: ignore
        # orjson không có ensure_ascii; nó luôn xuất bytes UTF-8
        opts = 0
        if sort_keys:
            opts |= orjson.OPT_SORT_KEYS
        if indent:
            opts |= orjson.OPT_INDENT_2 if indent == 2 else 0  # orjson chỉ có INDENT_2
        raw = orjson.dumps(data, option=opts, default=_default_encoder)
        text = raw.decode("utf-8")
    except Exception:
        text = json.dumps(
            data,
            default=_default_encoder,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
            indent=indent,
        )

    if to_file:
        with open(to_file, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if color:
        try:
            from pygments import highlight  # type: ignore
            from pygments.lexers import JsonLexer  # type: ignore
            from pygments.formatters import TerminalFormatter  # type: ignore
            text = highlight(text, JsonLexer(), TerminalFormatter())
        except Exception:
            pass

    # đảm bảo stdout là UTF-8 trên Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    print(text)

# ===== CLI tiện dụng: hỗ trợ đọc từ stdin hay file =====
def _load_input(path: Optional[str]) -> Any:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # nếu không có path mà có pipe → đọc stdin
    if not sys.stdin.isatty():
        try:
            return json.load(sys.stdin)
        except Exception:
            sys.stdin.seek(0)  # type: ignore
            return sys.stdin.read()
    return {"hint": "Provide --file path/to.json or pipe JSON via stdin."}

def main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Pretty print JSON for easy reading.")
    p.add_argument("--file", "-f", help="Đường dẫn file JSON để in.", default=None)
    p.add_argument("--sort", action="store_true", help="Sắp xếp key.")
    p.add_argument("--indent", type=int, default=2, help="Số khoảng trắng thụt lề (mặc định 2).")
    p.add_argument("--no-color", action="store_true", help="Tắt màu trong terminal.")
    p.add_argument("--out", help="Ghi ra file thay vì stdout.", default=None)
    args = p.parse_args(argv)

    data = _load_input(args.file)
    print_json(
        data,
        sort_keys=args.sort,
        indent=args.indent,
        ensure_ascii=False,
        to_file=args.out,
        color=not args.no_color,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
