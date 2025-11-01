# onuslibs/db/mysql_client.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from .settings_db import DbSettings

def _connect(settings: DbSettings | None = None) -> pymysql.connections.Connection:
    # Ưu tiên bảo mật giống module API
    s = settings or DbSettings.from_secure()
    kwargs = dict(
        host=s.host,
        user=s.user,
        password=s.password,
        database=s.database,
        port=s.port,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )
    if s.ssl_ca:
        kwargs["ssl"] = {"ca": s.ssl_ca}
    return pymysql.connect(**kwargs)

def get_connection(settings: DbSettings | None = None) -> pymysql.connections.Connection:
    return _connect(settings)

def healthcheck() -> bool:
    conn = None
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok;")
            row = cur.fetchone() or {}
            return bool(row.get("ok", 0) == 1 or list(row.values())[0] == 1)
    finally:
        if conn:
            conn.close()

def query(sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())
    finally:
        if conn:
            conn.close()

def execute(sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> int:
    conn = None
    try:
        conn = _connect()
        with conn.cursor() as cur:
            affected = cur.execute(sql, params or ())
            return int(affected)
    finally:
        if conn:
            conn.close()

def _quote_ident(name: str) -> str:
    return f"`{name.replace('`','``')}`"

def _quote_table(name: str) -> str:
    parts = [p for p in name.split(".") if p]
    return ".".join(_quote_ident(p) for p in parts) if parts else _quote_ident(name)

def _rows_to_matrix(
    rows: Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]],
    columns: Sequence[str] | None
) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    if not rows:
        return (list(columns or []), [])

    if isinstance(rows[0], Mapping):
        if columns is None:
            columns = list(rows[0].keys())
        matrix = []
        cols = list(columns)
        for r in rows:
            matrix.append(tuple(r.get(c) for c in cols))
        return (cols, matrix)
    else:
        if columns is None:
            raise ValueError("Must provide 'columns' when rows are sequences (not dicts).")
        cols = list(columns)
        matrix = [tuple(r) for r in rows]
        return (cols, matrix)

def bulk_insert(
    table: str,
    rows: Sequence[Mapping[str, Any]] | Sequence[Sequence[Any]],
    *,
    columns: Sequence[str] | None = None,
    on_duplicate_update: Sequence[str] | None = None,
    chunk_size: int = 1000,
    insert_ignore: bool = True,
) -> int:
    if not rows:
        return 0

    cols, matrix = _rows_to_matrix(rows, columns)
    col_list = ", ".join(_quote_ident(c) for c in cols)
    table_sql = _quote_table(table)

    insert_head = f"INSERT INTO {table_sql} ({col_list}) VALUES "
    if insert_ignore and not on_duplicate_update:
        insert_head = f"INSERT IGNORE INTO {table_sql} ({col_list}) VALUES "

    if on_duplicate_update:
        upd_cols = list(on_duplicate_update)
        upd_clause = ", ".join(f"{_quote_ident(c)}=VALUES({ _quote_ident(c) })" for c in upd_cols)
    else:
        upd_clause = ""

    placeholders = "(" + ", ".join(["%s"] * len(cols)) + ")"

    total_affected = 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for i in range(0, len(matrix), max(1, chunk_size)):
                chunk = matrix[i:i+chunk_size]
                values_sql = ", ".join([placeholders] * len(chunk))
                sql = insert_head + values_sql
                if upd_clause:
                    sql += f" ON DUPLICATE KEY UPDATE {upd_clause}"
                flat_params: List[Any] = []
                for row in chunk:
                    flat_params.extend(row)
                affected = cur.execute(sql, flat_params)
                total_affected += int(affected)
        conn.commit()
        return total_affected
    finally:
        conn.close()

from contextlib import contextmanager

@contextmanager
def transactional(settings: DbSettings | None = None):
    conn = _connect(settings)
    try:
        conn.autocommit(False)
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()
