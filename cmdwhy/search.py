"""按关键词、错误、状态、时间、项目和会话搜索历史命令。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SearchResult:
    seq: int
    hist_id: int
    ts: float
    cmd: str
    status: str
    intent: str
    task: str
    error: str
    project: str
    cwd: str

    def to_dict(self):
        return {
            "seq": self.seq,
            "hist_id": self.hist_id,
            "ts": self.ts,
            "cmd": self.cmd,
            "status": self.status,
            "intent": self.intent,
            "task": self.task,
            "error": self.error,
            "project": self.project,
            "cwd": self.cwd,
        }


def parse_time(value, now=None):
    """解析 7d / 24h / 30m / today / yesterday / 2026-11-17 [HH:MM[:SS]]。"""
    if not value:
        return None
    text = str(value).strip().lower()
    now = now if now is not None else time.time()
    if text in ("today", "今天"):
        return datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if text in ("yesterday", "昨天"):
        midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
        return (midnight - timedelta(days=1)).timestamp()
    match = re.fullmatch(r"(\d+)\s*([mhdw])", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
        return now - amount * seconds
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    raise ValueError("无法识别的时间：%s（支持 7d / 24h / 30m / today / 2026-11-17）" % value)


def _matches_project(result, project):
    needle = project.lower()
    return needle in (result.project or "").lower() or needle in (result.cwd or "").lower()


def search_events(
    analysis,
    query=None,
    status=None,
    error=None,
    since_ts=None,
    until_ts=None,
    session=None,
    project=None,
    limit=30,
    oldest=False,
):
    terms = [term.lower() for term in (query or "").split() if term]
    error_needle = (error or "").lower()
    results = []
    total = 0
    for event in analysis.events:
        ann = analysis.ann(event.seq)
        context = analysis.contexts.get(event.seq)
        env = analysis.envs.get(event.seq)
        if session and event.sid != session:
            continue
        if since_ts is not None and (not event.ts or event.ts < since_ts):
            continue
        if until_ts is not None and (not event.ts or event.ts > until_ts):
            continue
        if status:
            if status == "fail" and ann.status not in ("fail", "suspected"):
                continue
            if status == "ok" and ann.status != "ok":
                continue
            if status == "unknown" and ann.status != "unknown":
                continue
        error_signature = ann.error.signature if ann.error is not None else ""
        error_detail = ann.error.detail if ann.error is not None else ""
        haystack = " ".join(
            [
                event.cmd,
                ann.intent or "",
                ann.task or "",
                ann.purpose or "",
                error_signature,
                error_detail,
                (env.project if env is not None and env.project else ""),
                event.cwd or "",
            ]
        ).lower()
        if error_needle and error_needle not in (error_signature + " " + error_detail).lower():
            continue
        if terms and any(term not in haystack for term in terms):
            continue
        result = SearchResult(
            seq=event.seq,
            hist_id=event.hist_id,
            ts=event.ts,
            cmd=event.cmd,
            status=ann.status,
            intent=ann.intent or "",
            task=context.label if context is not None else (ann.task or ""),
            error=error_signature,
            project=env.project if env is not None and env.project else "",
            cwd=event.cwd or "",
        )
        if project and not _matches_project(result, project):
            continue
        results.append(result)
        total += 1
    results.sort(key=lambda item: item.seq, reverse=not oldest)
    if limit is not None and limit > 0:
        results = results[:limit]
    return results, total
