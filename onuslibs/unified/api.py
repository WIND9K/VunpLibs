# onuslibs/unified/api.py
from __future__ import annotations
from typing import Any, Dict, List, Callable, Optional, Sequence, Iterable
import logging

from ..config.settings import OnusSettings
from ..security.headers import build_headers
from ..pagination.header_pager import HeaderPager
from ..http.client import HttpClient

__all__ = ["fetch_json"]

log = logging.getLogger(__name__)

# ---------- helpers ----------
def _normalize_fields(fields: Optional[Sequence[str] | str]) -> Optional[str]:
    """Chấp nhận list/tuple hoặc CSV string -> trả về CSV sạch (hoặc None)."""
    if not fields:
        return None
    if isinstance(fields, str):
        parts = [p.strip() for p in fields.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in fields if str(p).strip()]
    return ",".join(parts) if parts else None

def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    """Ưu tiên: list -> pageItems -> items -> []."""
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        if isinstance(payload.get("pageItems"), list):
            return list(payload["pageItems"])
        if isinstance(payload.get("items"), list):
            return list(payload["items"])
    return []

def _soft_check_fields(items: List[Dict[str, Any]], fields_csv: Optional[str]) -> None:
    """Cảnh báo mềm nếu field top-level thiếu; không raise để an toàn runtime."""
    if not items or not fields_csv:
        return
    want = [p.strip() for p in fields_csv.split(",") if p.strip()]
    if not want:
        return
    sample = items[0]
    missing = [f for f in want if "." not in f and f not in sample]
    if missing:
        log.warning("Thiếu một số field trong payload: %s", ", ".join(missing))

# ---------- facade ----------
def fetch_json(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    fields: Optional[Sequence[str] | str] = None,
    page_size: Optional[int] = None,
    paginate: bool = True,
    order_by: Optional[str] = None,
    strict_fields: bool = False,
    unique_key: Optional[str] = None,
    settings: Optional[OnusSettings] = None,
    on_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    # DI / mở rộng
    client: Optional[HttpClient] = None,
    pager_func: Optional[Callable[..., Iterable[List[Dict[str, Any]]]]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    # Parallel (opt-in)
    parallel: bool = False,
    workers: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch JSON hợp nhất (REST-first, Facade duy nhất).
    Mặc định: giữ hành vi bản cũ (HeaderPager tuần tự).
    Bật song song: parallel=True hoặc tự tiêm pager_func.

    - Dedupe theo unique_key nếu cung cấp
    - strict_fields: cảnh báo thiếu field (không raise)
    - extra_headers: chèn/ghi đè header
    """
    st = settings or OnusSettings()

    # 1) headers
    hdrs: Dict[str, str] = build_headers(st)
    if extra_headers:
        hdrs.update(extra_headers)

    # 2) params
    final_params: Dict[str, Any] = dict(params or {})
    fields_csv = _normalize_fields(fields)
    if fields_csv:
        final_params["fields"] = fields_csv
    if order_by:
        final_params["orderBy"] = order_by
    if paginate:
        final_params.setdefault("pageSize", page_size or getattr(st, "page_size", None))

    # 3) HttpClient (tương thích 2 kiểu khởi tạo)
    cli = client
    if cli is None:
        try:
            cli = HttpClient(st)  # kiểu cũ
        except TypeError:
            cli = HttpClient(getattr(st, "base_url", ""))  # kiểu mới: base_url str

    results: List[Dict[str, Any]] = []
    seen: set = set() if unique_key else set()

    def _maybe_dedupe(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not unique_key:
            return batch
        out: List[Dict[str, Any]] = []
        for it in batch:
            k = it.get(unique_key)
            if k in seen:
                continue
            if k is not None:
                seen.add(k)
            out.append(it)
        return out

    # 4) phân trang
    if paginate:
        pager = pager_func
        if pager is None:
            if parallel:
                try:
                    # Dùng pager song song nếu có; nếu thiếu -> fallback tuần tự
                    from ..pagination.parallel_pager import header_fetch_all_parallel as _parallel
                    def pager(cli2, ep, params=None, headers=None, page_size=None):
                        return _parallel(
                            cli2, ep,
                            params=params or {},
                            headers=headers or {},
                            page_size=(page_size or getattr(st, "page_size", None)),
                            max_workers=workers,
                        )
                except Exception:
                    pager = None
        if pager is None:
            # tuần tự như bản cũ
            def pager(cli2, ep, params=None, headers=None, page_size=None):
                pg = HeaderPager(
                    cli2,
                    ep,
                    params=params or {},
                    headers=headers or {},
                    page_size=(page_size or getattr(st, "page_size", None)),
                )
                return pg.fetch_all()

        for batch in pager(cli, endpoint, params=final_params, headers=hdrs,
                           page_size=(page_size or getattr(st, "page_size", None))):
            items = _extract_items(batch)
            if strict_fields:
                _soft_check_fields(items, fields_csv)
            items = _maybe_dedupe(items)
            if not items:
                continue
            if on_batch:
                try:
                    on_batch(items)
                except Exception as e:
                    log.warning("on_batch raise: %s", e)
            results.extend(items)
        return results

    # 4') single GET
    resp = cli.get(endpoint, params=final_params, headers=hdrs)
    resp.raise_for_status()
    items = _extract_items(resp.json())
    if strict_fields:
        _soft_check_fields(items, fields_csv)
    items = _maybe_dedupe(items)
    if on_batch and items:
        try:
            on_batch(items)
        except Exception as e:
            log.warning("on_batch raise: %s", e)
    results.extend(items)
    return results
