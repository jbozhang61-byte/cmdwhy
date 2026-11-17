"""解释目标解析：history 编号优先，其次分析序号（#序号）。"""

from __future__ import annotations

import re

RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


def history_map(analysis):
    table = {}
    for event in analysis.events:
        if event.hist_id is not None:
            table.setdefault(event.hist_id, []).append(event)
    return table


def _resolve_hist(number, table, notes):
    matches = table.get(number) or []
    if not matches:
        return []
    if len(matches) > 1:
        latest = max(matches, key=lambda event: event.seq)
        notes.append(
            "history 编号 %d 对应 %d 条命令，显示最近一条；其他可用 #分析序号 指定" % (number, len(matches))
        )
        return [latest.seq]
    return [matches[0].seq]


def _hist_range(table, start, end):
    chosen = []
    for hist_id, events in table.items():
        if start <= hist_id <= end:
            chosen.extend(event.seq for event in events)
    return sorted(chosen)


def resolve_targets(analysis, targets):
    """把 explain 的参数解析成事件序号。

    规则：
        last                  最近一条
        #18 / seq:18          分析序号（内部排序号）
        #18-20 / seq:18-20    分析序号区间
        h518 / h:518          强制按 history 编号
        h518-520              强制按 history 编号区间
        518                   history 编号优先；没有则按分析序号
        518-520               有 history 编号时按编号区间，否则按分析序号区间

    返回 (seqs, notes)。
    """
    events = analysis.events
    total = len(events)
    table = history_map(analysis)
    seqs = []
    notes = []
    for raw in targets:
        token = (raw or "").strip()
        if not token:
            continue
        low = token.lower()
        if low in ("last", "l"):
            if total:
                seqs.append(events[-1].seq)
            else:
                notes.append("历史为空，没有 last 可解释")
            continue

        explicit = None
        body = token
        if token.startswith("#"):
            explicit = "seq"
            body = token[1:]
        elif low.startswith("seq:"):
            explicit = "seq"
            body = token[4:]
        elif low.startswith("h:"):
            explicit = "hist"
            body = token.split(":", 1)[1]
        elif re.match(r"^h\d", low):
            explicit = "hist"
            body = token[1:]

        range_match = RANGE_RE.match(body)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start > end:
                start, end = end, start
            if explicit == "seq":
                chosen = list(range(max(1, start), min(total, end) + 1))
                if chosen:
                    seqs.extend(chosen)
                else:
                    notes.append("分析序号范围 %d-%d 超出当前历史（共 %d 条）" % (start, end, total))
            elif explicit == "hist":
                chosen = _hist_range(table, start, end)
                if chosen:
                    seqs.extend(chosen)
                    notes.append("按 history 编号 %d-%d 解析" % (start, end))
                else:
                    notes.append("没有找到 history 编号 %d-%d" % (start, end))
            elif any(start <= hist_id <= end for hist_id in table):
                seqs.extend(_hist_range(table, start, end))
                notes.append("按 history 编号 %d-%d 解析" % (start, end))
            else:
                seqs.extend(range(max(1, start), min(total, end) + 1))
            continue

        if body.isdigit():
            number = int(body)
            if explicit == "seq":
                if 1 <= number <= total:
                    seqs.append(number)
                else:
                    notes.append("分析序号 %d 超出当前历史（共 %d 条）" % (number, total))
            elif explicit == "hist":
                found = _resolve_hist(number, table, notes)
                if found:
                    seqs.extend(found)
                else:
                    notes.append("没有找到 history 编号 %s" % body)
            elif number in table:
                seqs.extend(_resolve_hist(number, table, notes))
            elif 1 <= number <= total:
                seqs.append(number)
            else:
                notes.append("没有找到 history 编号或分析序号 %d" % number)
            continue

        notes.append("无法识别的目标：%s" % token)

    seen = set()
    unique = []
    for seq in seqs:
        if seq in seen:
            continue
        seen.add(seq)
        unique.append(seq)
    return unique, notes
