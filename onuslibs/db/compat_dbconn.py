# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Tuple, Optional, Sequence, Iterable
import pymysql
from .mysql_client import get_connection, query as _query, execute as _execute, bulk_insert as _bulk_insert, transactional as _tx

def _quote_table(name: str) -> str:
    parts = [p for p in name.split(".") if p]
    return ".".join(f"`{p.replace('`','``')}`" for p in parts)

def connect_db() -> pymysql.Connection:
    return get_connection()

def get_data(sql: str, params: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
    return _query(sql, params=params, stream=False)  # type: ignore[return-value]

def insert_data(table: str, data: List[Dict[str, Any]]) -> int:
    if not data:
        return 0
    cols = list(data[0].keys())
    return _bulk_insert(table=table, rows=data, columns=cols, on_duplicate_update=None, chunk_size=1000)

def update_data(table: str, data: List[Dict[str, Any]], key_columns: List[str]) -> int:
    if not data:
        return 0
    total = 0
    with _tx() as cur:
        for row in data:
            where = " AND ".join(f"`{k}`=%s" for k in key_columns)
            set_cols = [c for c in row.keys() if c not in key_columns]
            if not set_cols:
                continue
            set_clause = ", ".join(f"`{c}`=%s" for c in set_cols)
            sql = f"UPDATE {_quote_table(table)} SET {set_clause} WHERE {where}"
            params = [row[c] for c in set_cols] + [row[k] for k in key_columns]
            cur.execute(sql, params)
            total += cur.rowcount
    return total

def check_duplicate_data(table: str, key_columns: List[str], key_values: Iterable[Tuple[Any, ...]]) -> List[Tuple[Any, ...]]:
    key_values = list(key_values)
    if not key_values:
        return []
    cols = ", ".join(f"`{c}`" for c in key_columns)
    placeholders = "(" + ",".join(["%s"] * len(key_columns)) + ")"
    in_list = ", ".join([placeholders] * len(key_values))
    sql = f"SELECT {cols} FROM {_quote_table(table)} WHERE ({cols}) IN ({in_list})"
    flat_params = [v for kv in key_values for v in kv]
    rows = _query(sql, params=flat_params, stream=False)  # type: ignore[assignment]
    out: List[Tuple[Any, ...]] = []
    for r in rows:  # type: ignore[assignment]
        out.append(tuple(r[c] for c in key_columns))
    return out
