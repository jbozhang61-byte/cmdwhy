"""解析各类 shell 历史：bash / zsh / fish / history 输出，以及 cmdwhy hook 写入的 JSONL。"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime

from . import cache
from .model import Event
from .redact import redact_command, redact_error
from .util import append_line, new_uid, stable_uid

ZSH_RE = re.compile(r"^: (\d{9,12}):(\d+);(.*)$")
HISTORY_RE = re.compile(r"^\s*(\d{1,7})\s+(.*)$")
HISTORY_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s+(.*)$")


def detect_format(path, text="") -> str:
    name = os.path.basename(str(path)).lower()
    if name.endswith((".jsonl", ".json", ".ndjson")):
        return "jsonl"
    if "fish" in name:
        return "fish"
    if "zsh" in name:
        return "zsh"
    if "bash" in name:
        return "bash"
    sample = (text or "")[:8000]
    if re.search(r"^: \d{9,12}:\d*;", sample, re.M):
        return "zsh"
    if re.search(r"^- cmd: ", sample, re.M):
        return "fish"
    if re.search(r"^#\d{9,12}\s*$", sample, re.M):
        return "bash"
    if looks_like_history(sample):
        return "history"
    stripped = sample.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "jsonl"
    return "bash"


def looks_like_history(text) -> bool:
    """判断一段文本是不是 shell 内建 history 的输出（行首是历史编号）。"""
    lines = [line for line in (text or "").splitlines() if line.strip()][:200]
    if len(lines) < 2:
        return False
    hits = 0
    for line in lines:
        match = HISTORY_RE.match(line)
        if not match:
            continue
        rest = match.group(2)
        if HISTORY_TIME_RE.match(rest) or rest.strip():
            hits += 1
    return hits >= max(2, int(len(lines) * 0.6))


def parse_history_output(text, source="history"):
    """解析 history / history 20 的输出：编号、可选时间戳、命令。

    兼容：
        512  git status
        512  2026-11-17 09:12:00 git status
    """
    events = []
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        match = HISTORY_RE.match(line)
        if not match:
            continue
        hist_id = int(match.group(1))
        rest = match.group(2).strip()
        if not rest:
            continue
        ts = 0.0
        time_match = HISTORY_TIME_RE.match(rest)
        if time_match:
            try:
                ts = datetime.strptime(
                    time_match.group(1) + " " + time_match.group(2), "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except ValueError:
                ts = 0.0
            rest = time_match.group(3).strip()
        if not rest:
            continue
        events.append(Event(cmd=rest, ts=ts, hist_id=hist_id, source=source))
    return events


def parse_bash(text, source="bash_history"):
    events = []
    ts = 0.0
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        match = re.match(r"^#(\d{9,12})$", line.strip())
        if match:
            ts = float(match.group(1))
            continue
        events.append(Event(cmd=line.strip(), ts=ts, source=source))
    return events


def parse_zsh(text, source="zsh_history"):
    events = []
    current = None
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        match = ZSH_RE.match(line)
        if match:
            if current is not None:
                events.append(current)
            current = Event(
                cmd=match.group(3),
                ts=float(match.group(1)),
                duration_ms=int(match.group(2)) * 1000,
                source=source,
            )
            continue
        if not line.strip():
            continue
        if current is None:
            current = Event(cmd=line.strip(), source=source)
        else:
            current.cmd += "\n" + line
    if current is not None:
        events.append(current)
    return [ev for ev in events if ev.cmd.strip()]


def parse_fish(text, source="fish_history"):
    events = []
    current = None
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if line.startswith("- cmd: "):
            if current is not None:
                events.append(current)
            current = Event(cmd=line[7:].replace("\\n", "\n"), source=source)
        elif line.startswith("  when: ") and current is not None:
            try:
                current.ts = float(int(line[8:].strip()))
            except ValueError:
                pass
        elif line.startswith("- ") and current is not None:
            events.append(current)
            current = None
    if current is not None:
        events.append(current)
    return [ev for ev in events if ev.cmd.strip()]


def parse_jsonl(text, source="hook"):
    items = []
    stripped = (text or "").strip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
        except ValueError:
            items = []
    if not items:
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            items.append(obj)
    events = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("event"), dict):
            obj = obj["event"]
        if not (obj.get("cmd") or obj.get("command")):
            continue
        event = Event.from_dict(obj)
        event.source = str(obj.get("source") or source)
        events.append(event)
    return events


PARSERS = {
    "bash": parse_bash,
    "zsh": parse_zsh,
    "fish": parse_fish,
    "history": parse_history_output,
    "jsonl": parse_jsonl,
}


def parse_file(path, fmt=None):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    fmt = fmt or detect_format(path, text)
    parser = PARSERS.get(fmt, parse_bash)
    events = parser(text, source=os.path.basename(path))
    absolute = os.path.abspath(path)
    for index, event in enumerate(events):
        if not event.uid:
            if event.hist_id is not None:
                # history 编号 + 命令文本：历史文件被重写/截断后仍尽量稳定
                event.uid = stable_uid("hist", absolute, event.hist_id, event.cmd)
            else:
                event.uid = stable_uid(absolute, index, event.ts, event.cmd)
    return events, fmt


def _info_rank(event: Event) -> int:
    """信息量排序：有退出码/错误原文 > 有 history 编号 > 普通历史。"""
    if event.exit_code is not None or event.stderr:
        return 0
    if event.hist_id is not None:
        return 1
    return 2


def _dedupe(events):
    """同一条命令在 hook 与历史文件里同时出现时只保留信息更全的那条。"""
    ordered = sorted(events, key=lambda ev: (ev.ts if ev.ts else -1.0, _info_rank(ev)))
    kept = []
    for event in ordered:
        replaced = False
        for idx in range(len(kept) - 1, max(-1, len(kept) - 8), -1):
            other = kept[idx]
            if other.cmd != event.cmd:
                continue
            if other.uid and event.uid and other.uid == event.uid:
                if _info_rank(event) < _info_rank(other):
                    kept[idx] = event
                replaced = True
                break
            if other.source == event.source:
                continue
            if other.hist_id is not None and event.hist_id is not None and other.hist_id == event.hist_id:
                # 同一个 history 编号来自 hook 与 history 输出：同一次执行，合并保留信息更全的
                if _info_rank(event) < _info_rank(other):
                    kept[idx] = event
                replaced = True
                break
            if other.ts and event.ts and abs(other.ts - event.ts) <= 5:
                # history 输出里的每一行都是独立编号，哪怕命令文本相同也不能合并
                if other.hist_id is not None or event.hist_id is not None:
                    if event.hist_id is not None and other.hist_id == event.hist_id:
                        if _info_rank(event) < _info_rank(other):
                            kept[idx] = event
                        replaced = True
                        break
                    continue
                if _info_rank(event) < _info_rank(other):
                    kept[idx] = event
                replaced = True
                break
        if replaced:
            continue
        kept.append(event)
    captured = [ev for ev in kept if ev.ts and (ev.exit_code is not None or ev.stderr)]
    if captured:
        counter = Counter(ev.cmd for ev in captured)
        filtered = []
        for event in kept:
            if (
                event.source != "hook"
                and event.hist_id is None
                and not event.ts
                and counter.get(event.cmd, 0) > 0
            ):
                counter[event.cmd] -= 1
                continue
            filtered.append(event)
        kept = filtered
    return kept


def merge_events(events, cfg):
    cleaned = []
    for event in events:
        cmd = (event.cmd or "").strip("\n\r ")
        if not cmd:
            continue
        if any(cmd == prefix or cmd.startswith(prefix + " ") for prefix in cfg.ignore_prefixes or []):
            continue
        event.cmd = redact_command(cmd) if cfg.redact else cmd
        if event.stderr and cfg.redact:
            event.stderr = redact_error(event.stderr)
        cleaned.append(event)
    for event in cleaned:
        if not event.uid:
            # 内容派生的 ID：不依赖列表位置，导入前后保持稳定
            event.uid = stable_uid(event.source, event.hist_id, event.ts, event.cmd)
    deduped = _dedupe(cleaned)
    if cfg.max_events and len(deduped) > cfg.max_events:
        deduped = deduped[-cfg.max_events:]
    for index, event in enumerate(deduped, 1):
        event.seq = index
        event.sid = ""
    return deduped


def load_events(cfg, extra_paths=None, use_store=True):
    """读取配置里的历史来源（或显式给定的文件），返回 (事件列表, 元信息)。"""
    events = []
    files = []
    formats = []
    warnings = []
    specs = cfg.sources if extra_paths is None else list(extra_paths)
    for path in cfg.expand_sources(specs):
        try:
            cached = cache.get(cfg, path, cfg.redact)
            if cached is not None:
                parsed, fmt = cached
            else:
                parsed, fmt = parse_file(path)
                cache.put(cfg, path, fmt, parsed, cfg.redact)
        except OSError as exc:
            warnings.append("无法读取 %s：%s" % (path, exc))
            continue
        events.extend(parsed)
        files.append(path)
        formats.append(fmt)
    if use_store:
        store = cfg.store_path
        if os.path.exists(store):
            try:
                with open(store, "r", encoding="utf-8", errors="replace") as fh:
                    stored = parse_jsonl(fh.read(), source="hook")
            except OSError as exc:
                warnings.append("无法读取 hook 记录：%s" % exc)
                stored = []
            if stored:
                events.extend(stored)
                files.append(store)
                formats.append("hook")
    numbered = merge_events(events, cfg)
    meta = {
        "files": files,
        "formats": formats,
        "warnings": warnings,
        "captured": sum(1 for ev in numbered if ev.exit_code is not None or ev.stderr),
        "history_ids": sum(1 for ev in numbered if ev.hist_id is not None),
        "total": len(numbered),
    }
    return numbered, meta


def read_store(cfg):
    if not os.path.exists(cfg.store_path):
        return []
    try:
        with open(cfg.store_path, "r", encoding="utf-8", errors="replace") as fh:
            return parse_jsonl(fh.read(), source="hook")
    except OSError:
        return []


def append_event(cfg, event: Event):
    cfg.ensure()
    if not event.uid:
        event.uid = new_uid()
    if cfg.redact:
        event.cmd = redact_command(event.cmd)
        if event.stderr:
            event.stderr = redact_error(event.stderr)
    append_line(cfg.store_path, json.dumps(event.to_dict(), ensure_ascii=False))
