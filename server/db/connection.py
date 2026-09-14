# -*- coding: utf-8 -*-
"""数据库连接工厂：默认 SQLite，配了 COMIC_MYSQL_HOST 走 MySQL。

comic-generator 原来是纯文件项目（projects/ 目录 + JSON），本地开发不依赖 MySQL。
账户域引入用户/积分表后仍保持这个体验：
- 本地：未配置 COMIC_MYSQL_HOST → 落 output/comic.db（gitignore），零依赖可跑
- 生产：配置 COMIC_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE → 连真 MySQL

两种模式对上层暴露同一个接口：
    with get_db().get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ... WHERE x = %s", (v,))
        row = cur.fetchone()  # dict

SQLite 模式靠 _strip_mysql_syntax 把 %s→?、NOW()→CURRENT_TIMESTAMP 等翻译过去；
repositories 里写的 SQL 两边都能跑。FOR UPDATE 在 SQLite 下被剥掉——
单文件 SQLite serialized 写本来就不需要行锁。
"""

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from server.config import ROOT_DIR

_DATETIME_COLS = {
    "people_datetime", "frozen_datetime", "create_time", "update_time",
    "login_time",
}


def _parse_dt(s: str):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return s


def _strip_mysql_syntax(sql: str) -> str:
    sql = re.sub(r"\s*for\s+update", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*on\s+update\s+current_timestamp", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bNOW\s*\(\s*\)", "CURRENT_TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"FROM_UNIXTIME\s*\(\s*\?\s*\)", "datetime(?, 'unixepoch')", sql, flags=re.IGNORECASE
    )
    return sql


class _FakeCursor:
    """模拟 pymysql DictCursor 的最小实现（dict 行 + lastrowid + rowcount）。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self.lastrowid: int | None = None
        self.rowcount: int = -1

    def execute(self, sql: str, args: tuple = ()) -> None:
        translated = _strip_mysql_syntax(sql.strip().replace("%s", "?"))
        cur = self._conn.execute(translated, tuple(args))
        self.lastrowid = cur.lastrowid
        self.rowcount = cur.rowcount
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            for k, v in list(d.items()):
                if k in _DATETIME_COLS and isinstance(v, str):
                    d[k] = _parse_dt(v)
            rows.append(d)
        self._rows = rows
        self._row = rows[0] if rows else None

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    """模拟 pymysql connection（cursor + commit/rollback）。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def cursor(self):
        return _FakeCursor(self._conn)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        pass  # SQLite 连接由工厂持有复用，单连接 close 无操作


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS comic_people (
  people_id INTEGER PRIMARY KEY AUTOINCREMENT,
  people_name TEXT NOT NULL,
  people_phone TEXT NOT NULL UNIQUE,
  people_password TEXT NOT NULL,
  points REAL NOT NULL DEFAULT 0,
  people_status TEXT NOT NULL DEFAULT 'PASS',
  frozen_datetime TEXT,
  people_reason TEXT,
  people_ip TEXT,
  people_datetime TEXT DEFAULT CURRENT_TIMESTAMP,
  invitation_code TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS comic_points (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  people_id INTEGER NOT NULL,
  old_num REAL NOT NULL,
  update_num REAL NOT NULL,
  points_num REAL NOT NULL,
  receipts TEXT NOT NULL,
  consumption TEXT NOT NULL,
  remarks TEXT,
  delete_flag INTEGER NOT NULL DEFAULT 0,
  create_time TEXT DEFAULT CURRENT_TIMESTAMP,
  update_time TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS comic_invitation_code (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  people_id INTEGER NOT NULL DEFAULT 0,
  invitation_code TEXT NOT NULL UNIQUE,
  invalid INTEGER NOT NULL DEFAULT 1,
  create_time TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS comic_login_errorlog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  "user" TEXT NOT NULL,
  login_time TEXT,
  ip TEXT,
  disable TEXT NOT NULL DEFAULT 'N'
);
CREATE TABLE IF NOT EXISTS comic_project (
  project_id TEXT PRIMARY KEY,
  people_id INTEGER NOT NULL,
  title TEXT,
  create_time TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS comic_app_config (
  id INTEGER PRIMARY KEY DEFAULT 1,
  register_points REAL NOT NULL DEFAULT 100,
  recommend_points REAL NOT NULL DEFAULT 0,
  story_cost_per_1k_token REAL NOT NULL DEFAULT 1.0,
  image_cost_per_unit REAL NOT NULL DEFAULT 1.0
);
INSERT OR IGNORE INTO comic_app_config (id) VALUES (1);
"""


class _SQLiteFactory:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SQLITE_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    @contextmanager
    def get_connection(self):
        # serialized 写：同一时刻一个线程持库，commit/rollback 在锁内
        with self._lock:
            yield _FakeConnection(self._conn)


class _MySQLFactory:
    def __init__(self, mysql_config: dict):
        self._mysql_config = mysql_config

    @contextmanager
    def get_connection(self):
        import pymysql
        from pymysql.cursors import DictCursor

        conn = pymysql.connect(cursorclass=DictCursor, **self._mysql_config)
        try:
            yield conn
        finally:
            conn.close()


_factory = None


def get_db():
    """单例连接工厂。调用方用 `with get_db().get_connection() as c:`。

    选库逻辑：COMIC_MYSQL_HOST 已配置 → MySQL；否则 → output/comic.db SQLite。
    """
    global _factory
    if _factory is not None:
        return _factory

    host = (os.environ.get("COMIC_MYSQL_HOST") or "").strip()
    if host:
        _factory = _MySQLFactory({
            "host": host,
            "port": int(os.environ.get("COMIC_MYSQL_PORT", "3306")),
            "user": os.environ.get("COMIC_MYSQL_USER", "root"),
            "password": os.environ.get("COMIC_MYSQL_PASSWORD", ""),
            "database": os.environ.get("COMIC_MYSQL_DATABASE", "comic"),
            "charset": "utf8mb4",
            "autocommit": False,
        })
    else:
        db_path = Path(
            os.environ.get("COMIC_DB_PATH", str(ROOT_DIR / "output" / "comic.db"))
        )
        _factory = _SQLiteFactory(db_path)
    return _factory
