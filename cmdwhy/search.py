"""按关键词、错误、状态、时间、项目和会话搜索历史命令。"""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SearchResult:
    seq: int
    uid: str
    hist_id: int
    ts: float
    cmd: str
    status: str
    intent: str
    task: str
    error: str
    project: str
    cwd: str
    score: float = 0.0

    def to_dict(self):
        return {
            "seq": self.seq,
            "uid": self.uid,
            "hist_id": self.hist_id,
            "ts": self.ts,
            "cmd": self.cmd,
            "status": self.status,
            "intent": self.intent,
            "task": self.task,
            "error": self.error,
            "project": self.project,
            "cwd": self.cwd,
            "score": self.score,
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


TOKEN_RE = re.compile(r"[A-Za-z0-9_./:@+-]+|[\u4e00-\u9fff]")


def _tokens(text):
    raw = TOKEN_RE.findall((text or "").lower())
    out = []
    cjk = []
    for token in raw:
        if len(token) == 1 and "\u4e00" <= token <= "\u9fff":
            cjk.append(token)
        else:
            out.append(token)
    # 中文用二元组，避免单字匹配过宽
    out.extend("".join(cjk[index : index + 2]) for index in range(len(cjk) - 1))
    if len(cjk) == 1:
        out.append(cjk[0])
    return out


def _bm25(results, terms):
    if not terms:
        return
    docs = []
    for result in results:
        tokens = []
        tokens.extend(_tokens(result.cmd) * 2)
        tokens.extend(_tokens(result.error))
        tokens.extend(_tokens(result.task))
        tokens.extend(_tokens(result.intent))
        tokens.extend(_tokens(result.project))
        tokens.extend(_tokens(result.cwd))
        docs.append(tokens)
    if not docs:
        return
    avgdl = sum(len(doc) for doc in docs) / float(len(docs))
    df = Counter()
    for doc in docs:
        for token in set(doc):
            df[token] += 1
    total = len(docs)
    k1 = 1.2
    b = 0.75
    for result, doc in zip(results, docs):
        tf = Counter(doc)
        dl = len(doc) or 1
        score = 0.0
        for term in terms:
            term_tokens = _tokens(term)
            if not term_tokens:
                continue
            for token in term_tokens:
                freq = tf.get(token, 0)
                if not freq:
                    continue
                idf = math.log(1.0 + (total - df[token] + 0.5) / (df[token] + 0.5))
                score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / max(avgdl, 1e-9)))
        result.score = score

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
    regex=False,
    any_term=False,
    sort="time",
):
    raw_query = (query or "").strip()
    if regex:
        try:
            pattern = re.compile(raw_query, re.I) if raw_query else None
        except re.error as exc:
            raise ValueError("正则表达式无效：%s" % exc)
        terms = []
    else:
        pattern = None
        terms = [term.lower() for term in raw_query.split() if term]
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
        if pattern is not None:
            if not pattern.search(haystack):
                continue
            score = 2.0 + len(pattern.findall(event.cmd)) * 2.0
        else:
            matched = [term for term in terms if term in haystack]
            if terms and ((any_term and not matched) or (not any_term and len(matched) != len(terms))):
                continue
            score = 0.0
        result = SearchResult(
            seq=event.seq,
            uid=event.uid,
            hist_id=event.hist_id,
            ts=event.ts,
            cmd=event.cmd,
            status=ann.status,
            intent=ann.intent or "",
            task=context.label if context is not None else (ann.task or ""),
            error=error_signature,
            project=env.project if env is not None and env.project else "",
            cwd=event.cwd or "",
            score=score,
        )
        if project and not _matches_project(result, project):
            continue
        results.append(result)
        total += 1
    if pattern is None:
        _bm25(results, terms)
    if sort == "relevance":
        results.sort(key=lambda item: (-item.score, -item.ts, -item.seq))
    else:
        results.sort(key=lambda item: item.seq, reverse=not oldest)
    if limit is not None and limit > 0:
        results = results[:limit]
    return results, total
