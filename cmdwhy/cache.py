"""解析缓存：用 SQLite 缓存历史文件的解析结果，避免每条命令都重读大文件。"""

from __future__ import annotations

import json
import os
import sqlite3

from .model import Event
from .redact import redact_command, redact_error

SCHEMA = """
CREATE TABLE IF NOT EXISTS parse_cache (
    path TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    redact INTEGER NOT NULL,
    fmt TEXT NOT NULL,
    events TEXT NOT NULL,
    PRIMARY KEY (path, mtime_ns, size, redact)
)
"""


def enabled():
    return os.environ.get("CMDWHY_NO_CACHE", "").lower() not in ("1", "true", "yes", "on")


def _connect(path):
    con = sqlite3.connect(path, timeout=2)
    try:
        con.execute(SCHEMA)
        return con
    except sqlite3.DatabaseError:
        try:
            con.close()
        except Exception:
            pass
        _reset(path)
        con = sqlite3.connect(path, timeout=2)
        con.execute(SCHEMA)
        return con


def _reset(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def clear(cfg):
    _reset(cfg.cache_path)


def get(cfg, path, redact):
    if not enabled():
        return None
    try:
        stat = os.stat(path)
        con = _connect(cfg.cache_path)
        try:
            row = con.execute(
                "SELECT fmt, events FROM parse_cache WHERE path=? AND mtime_ns=? AND size=? AND redact=?",
                (os.path.abspath(path), stat.st_mtime_ns, stat.st_size, 1 if redact else 0),
            ).fetchone()
        finally:
            con.close()
        if not row:
            return None
        fmt, payload = row
        items = json.loads(payload)
        return [Event.from_dict(item) for item in items], fmt
    except sqlite3.DatabaseError:
        _reset(cfg.cache_path)
        return None
    except (OSError, sqlite3.Error, ValueError):
        return None


def put(cfg, path, fmt, events, redact):
    if not enabled():
        return
    try:
        stat = os.stat(path)
        payload = []
        for event in events:
            item = event.to_dict()
            if redact:
                item["cmd"] = redact_command(item.get("cmd") or "")
                if item.get("stderr"):
                    item["stderr"] = redact_error(item["stderr"])
            payload.append(item)
        con = _connect(cfg.cache_path)
        try:
            con.execute(
                "INSERT OR REPLACE INTO parse_cache(path, mtime_ns, size, redact, fmt, events) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    os.path.abspath(path),
                    stat.st_mtime_ns,
                    stat.st_size,
                    1 if redact else 0,
                    fmt,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            con.commit()
        finally:
            con.close()
    except sqlite3.DatabaseError:
        _reset(cfg.cache_path)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return
