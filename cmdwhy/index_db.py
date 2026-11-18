"""SQLite 查询索引：保存事件 + 注解字段，用 FTS5/BM25 直接检索。"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3

from .search import SearchResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    uid TEXT PRIMARY KEY,
    seq INTEGER,
    ts REAL,
    cmd TEXT,
    hist_id INTEGER,
    exit_code INTEGER,
    status TEXT,
    cwd TEXT,
    shell TEXT,
    distro TEXT,
    source TEXT,
    sid TEXT,
    intent TEXT,
    task TEXT,
    error TEXT,
    error_detail TEXT,
    project TEXT,
    host TEXT,
    user TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    uid UNINDEXED, cmd, error, task, intent, project, tokenize='unicode61'
);
"""

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def path(cfg):
    return cfg.index_path


def _connect(cfg):
    os.makedirs(cfg.home, exist_ok=True)
    con = sqlite3.connect(path(cfg), timeout=3)
    con.executescript(SCHEMA)
    try:
        con.executescript(FTS_SCHEMA)
    except sqlite3.OperationalError:
        pass
    return con


def _fts_ready(con):
    try:
        con.execute("SELECT count(*) FROM events_fts").fetchone()
        return True
    except sqlite3.Error:
        return False


def signature(cfg, rich=False):
    digest = hashlib.sha256()
    for source in cfg.expand_sources():
        digest.update(os.path.abspath(source).encode("utf-8", "replace"))
        try:
            stat = os.stat(source)
            digest.update(("%s:%s" % (stat.st_mtime_ns, stat.st_size)).encode())
        except OSError:
            digest.update(b"missing")
    try:
        stat = os.stat(cfg.store_path)
        digest.update(("store:%s:%s" % (stat.st_mtime_ns, stat.st_size)).encode())
    except OSError:
        digest.update(b"store:missing")
    digest.update(("%s:%s:%s:%s" % (cfg.redact, cfg.max_events, cfg.context_window, 1 if rich else 0)).encode())
    return digest.hexdigest()


def is_current(cfg):
    try:
        con = _connect(cfg)
        try:
            row = con.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
            count = con.execute("SELECT count(*) FROM events").fetchone()[0]
        finally:
            con.close()
        return bool(row and row[0] == signature(cfg, True) and count >= 0)
    except (OSError, sqlite3.Error):
        return False


def update(cfg, analysis, rich=True):
    """把一次分析结果写入索引；同签名时跳过。rich 表示包含任务上下文。"""
    try:
        con = _connect(cfg)
        try:
            current = con.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
            if current and current[0] == signature(cfg, rich):
                return
            if not rich and current and current[0] == signature(cfg, True):
                return
            con.execute("DELETE FROM events")
            fts = _fts_ready(con)
            if fts:
                con.execute("DELETE FROM events_fts")
            for event in analysis.events:
                ann = analysis.ann(event.seq)
                context = analysis.contexts.get(event.seq) if getattr(analysis, "contexts", None) else None
                env = analysis.envs.get(event.seq) if getattr(analysis, "envs", None) else None
                task = context.label if context is not None else (ann.task or "")
                error = ann.error.signature if ann.error is not None else ""
                detail = ann.error.detail if ann.error is not None else ""
                row = (
                    event.uid or ("seq%d" % event.seq),
                    event.seq,
                    event.ts,
                    event.cmd,
                    event.hist_id,
                    event.exit_code,
                    ann.status,
                    event.cwd or "",
                    event.shell or "",
                    event.distro or "",
                    event.source or "",
                    event.sid or "",
                    ann.intent or "",
                    task or "",
                    error,
                    detail,
                    (env.project if env is not None and env.project else "") or "",
                    event.host or "",
                    event.user or "",
                )
                con.execute(
                    "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    row,
                )
                if fts:
                    con.execute(
                        "INSERT INTO events_fts(uid, cmd, error, task, intent, project) VALUES (?,?,?,?,?,?)",
                        (row[0], event.cmd, error, task or "", ann.intent or "", row[16]),
                    )
            con.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES ('signature', ?)",
                (signature(cfg, rich),),
            )
            con.commit()
        finally:
            con.close()
    except (OSError, sqlite3.Error, TypeError):
        return


def _fts_query(text, any_term):
    terms = [term for term in re.split(r"\s+", (text or "").strip()) if term]
    quoted = ['"%s"' % term.replace('"', '""') for term in terms]
    return (" OR " if any_term else " AND ").join(quoted)


def _row_to_result(row, score=0.0):
    return SearchResult(
        seq=row[1],
        uid=row[0],
        hist_id=row[4],
        ts=row[2] or 0.0,
        cmd=row[3] or "",
        status=row[6] or "unknown",
        intent=row[12] or "",
        task=row[13] or "",
        error=row[14] or "",
        project=row[16] or "",
        cwd=row[7] or "",
        score=score,
    )


def query(cfg, query_text="", status=None, error=None, since_ts=None, until_ts=None,
          session=None, project=None, limit=30, oldest=False, any_term=False,
          sort="time", regex=False):
    """返回 (results, total)；不支持的正则/中文查询返回 (None, 0) 让调用方回退。"""
    if regex or (query_text and CJK_RE.search(query_text)):
        return None, 0
    try:
        con = _connect(cfg)
        try:
            fts = _fts_ready(con) and bool(query_text)
            if query_text and not fts:
                return None, 0
            where = []
            params = []
            if fts:
                where.append("events_fts MATCH ?")
                params.append(_fts_query(query_text, any_term))
                from_sql = "FROM events_fts f JOIN events e ON e.uid=f.uid"
                rank_sql = ", bm25(events_fts) AS rank"
            else:
                from_sql = "FROM events e"
                rank_sql = ""
            if status:
                if status == "fail":
                    where.append("e.status IN ('fail','suspected')")
                else:
                    where.append("e.status = ?")
                    params.append(status)
            if error:
                where.append("(e.error LIKE ? OR e.error_detail LIKE ?)")
                params.extend(["%" + error + "%", "%" + error + "%"])
            if since_ts is not None:
                where.append("e.ts >= ?")
                params.append(since_ts)
            if until_ts is not None:
                where.append("e.ts <= ?")
                params.append(until_ts)
            if session:
                where.append("e.sid = ?")
                params.append(session)
            if project:
                where.append("(e.project LIKE ? OR e.cwd LIKE ?)")
                params.extend(["%" + project + "%", "%" + project + "%"])
            sql = "SELECT e.*%s %s" % (rank_sql, from_sql)
            if where:
                sql += " WHERE " + " AND ".join(where)
            if sort == "relevance" and fts:
                sql += " ORDER BY rank ASC, e.ts DESC"
            elif oldest:
                sql += " ORDER BY e.seq ASC"
            else:
                sql += " ORDER BY e.seq DESC"
            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()
        total = len(rows)
        if limit is not None and limit > 0:
            rows = rows[:limit]
        results = [_row_to_result(row, -row[-1] if fts and sort == "relevance" else 0.0) for row in rows]
        return results, total
    except (OSError, sqlite3.Error):
        return None, 0


def status(cfg):
    try:
        con = _connect(cfg)
        try:
            events = con.execute("SELECT count(*) FROM events").fetchone()[0]
            current = con.execute("SELECT value FROM meta WHERE key='signature'").fetchone()
        finally:
            con.close()
        return {
            "path": path(cfg),
            "events": events,
            "current": bool(current and current[0] == signature(cfg, True)),
            "size": os.path.getsize(path(cfg)) if os.path.exists(path(cfg)) else 0,
        }
    except (OSError, sqlite3.Error):
        return {"path": path(cfg), "events": 0, "current": False, "size": 0}


def clear(cfg):
    try:
        con = _connect(cfg)
        try:
            con.execute("DELETE FROM events")
            if _fts_ready(con):
                con.execute("DELETE FROM events_fts")
            con.execute("DELETE FROM meta")
            con.commit()
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        pass
