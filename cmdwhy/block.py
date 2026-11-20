"""多条命令成组分析：把 50–60 条历史当成一个阶段，而不是逐条解释。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from .context import attach_contexts
from .labels import apply as apply_labels
from .report import ROLE_LABELS
from .util import short_path, truncate


def _env_text(env):
    if env is None:
        return "环境未知"
    parts = []
    if env.cwd:
        home = None
        if env.user and env.cwd.startswith("/home/" + env.user):
            home = "/home/" + env.user
        elif env.cwd.startswith("/root"):
            home = "/root"
        parts.append(short_path(env.cwd, home=home, width=28))
    if env.project:
        parts.append(env.project + ("(%s)" % env.project_kind if env.project_kind else ""))
    if env.branch:
        parts.append("git:" + env.branch + ("*" if env.dirty else ""))
    if env.venv:
        parts.append("venv:" + env.venv)
    if env.distro:
        parts.append(env.distro)
    if env.cwd and env.wsl:
        parts.append("WSL")
    elif env.cwd and env.container:
        parts.append("container")
    if env.cwd and env.ssh:
        parts.append("ssh")
    if env.cwd and env.pkg_manager:
        parts.append(env.pkg_manager)
    return " · ".join(parts) if parts else "环境未知"


def _time_text(ts):
    if not ts:
        return "--:--"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _env_changes(analysis, seqs):
    changes = []
    previous = None
    for seq in seqs:
        env = analysis.envs.get(seq)
        if env is None:
            continue
        if previous is not None:
            if env.project and previous.project and env.project != previous.project:
                changes.append("项目 %s → %s" % (previous.project, env.project))
            if env.branch and previous.branch and env.branch != previous.branch:
                changes.append("分支 %s → %s" % (previous.branch, env.branch))
            if env.cwd and previous.cwd and env.cwd != previous.cwd:
                home = None
                if env.user and env.cwd.startswith("/home/" + env.user):
                    home = "/home/" + env.user
                elif env.cwd.startswith("/root"):
                    home = "/root"
                changes.append("cd " + short_path(env.cwd, home=home, width=24))
            if env.venv != previous.venv:
                if env.venv:
                    changes.append("进入 venv " + env.venv)
                elif previous.venv:
                    changes.append("离开 venv " + previous.venv)
        previous = env
    unique = []
    for item in changes:
        if item not in unique:
            unique.append(item)
    return unique[-5:]


def build_block(analysis, seqs, cfg=None, window=20):
    seqs = sorted({int(seq) for seq in seqs if 1 <= int(seq) <= len(analysis.events)})
    if not seqs:
        return None
    attach_contexts(analysis, window, seqs=seqs)
    if cfg is not None:
        try:
            apply_labels(analysis, cfg)
        except (OSError, ValueError):
            pass
    events = [analysis.event(seq) for seq in seqs]
    anns = [analysis.ann(seq) for seq in seqs]
    contexts = [analysis.contexts.get(seq) for seq in seqs]
    task_counter = Counter()
    phase_order = []
    role_counter = Counter()
    error_counter = Counter()
    groups = []
    current = None
    for event, ann, context in zip(events, anns, contexts):
        task = ann.task or (context.label if context else "日常操作")
        phase = ann.phase or (context.phase if context else "推进")
        task_counter[task] += 1
        if phase and phase not in phase_order:
            phase_order.append(phase)
        if ann.role:
            role_counter[ROLE_LABELS.get(ann.role, ann.role)] += 1
        if ann.error is not None and ann.status in ("fail", "suspected"):
            error_counter[ann.error.signature] += 1
        if current is None or current["task"] != task:
            current = {"task": task, "start": event.seq, "end": event.seq, "count": 1, "phases": []}
            groups.append(current)
        else:
            current["end"] = event.seq
            current["count"] += 1
        if phase and phase not in current["phases"]:
            current["phases"].append(phase)
    ok = sum(1 for ann in anns if ann.status == "ok")
    fail = sum(1 for ann in anns if ann.status == "fail")
    suspected = sum(1 for ann in anns if ann.status == "suspected")
    unknown = sum(1 for ann in anns if ann.status not in ("ok", "fail", "suspected"))
    fixes = sum(1 for ann in anns if ann.fix_of)
    verified = sum(1 for ann in anns if ann.verified)
    sessions = len({event.sid for event in events if event.sid})
    start, end = seqs[0], seqs[-1]
    span = "%s–%s" % (_time_text(events[0].ts), _time_text(events[-1].ts))
    result = "成功 %d · 失败 %d · 疑似 %d · 未记录 %d；修复动作 %d，验证 %d" % (
        ok, fail, suspected, unknown, fixes, verified
    )
    rows = []
    for event, ann, context in zip(events, anns, contexts):
        rows.append(
            {
                "seq": event.seq,
                "time": _time_text(event.ts),
                "status": ann.status,
                "cmd": event.cmd,
                "intent": ann.intent,
                "purpose": ann.purpose,
                "role": ann.role,
                "role_label": ROLE_LABELS.get(ann.role, ann.role),
                "task": ann.task or (context.label if context else ""),
                "phase": ann.phase or (context.phase if context else ""),
                "error": ann.error.signature if ann.error is not None else None,
            }
        )
    return {
        "start_seq": start,
        "end_seq": end,
        "count": len(seqs),
        "span": span,
        "sessions": sessions,
        "environment": _env_text(analysis.envs.get(events[-1].seq) if events else None),
        "env_changes": _env_changes(analysis, seqs),
        "tasks": [{"label": label, "count": count} for label, count in task_counter.most_common()],
        "phases": phase_order,
        "roles": [{"label": label, "count": count} for label, count in role_counter.most_common()],
        "errors": [{"signature": sig, "count": count} for sig, count in error_counter.most_common(8)],
        "groups": groups,
        "result": result,
        "commands": rows,
    }


def render_block(data, renderer=None):
    p = renderer.p if renderer is not None else None
    bold = p.bold if p is not None else (lambda text: text)
    grey = (lambda text: p(text, "grey")) if p is not None else (lambda text: text)
    lines = []
    if data is None:
        return "没有可分析的命令段。"
    lines.append(
        bold("命令段  #%d–#%d" % (data["start_seq"], data["end_seq"]))
        + "  %d 条 · %d 个会话 · %s" % (data["count"], data["sessions"], data["span"])
    )
    lines.append("环境    " + data["environment"])
    lines.append("任务    " + " · ".join("%s×%d" % (item["label"], item["count"]) for item in data["tasks"][:5]))
    lines.append("阶段    " + (" → ".join(data["phases"]) if data["phases"] else "未知"))
    lines.append("结果    " + data["result"])
    if data["errors"]:
        lines.append("错误    " + " · ".join("%s×%d" % (item["signature"], item["count"]) for item in data["errors"]))
    if data["roles"]:
        lines.append("角色    " + " · ".join("%s×%d" % (item["label"], item["count"]) for item in data["roles"]))
    if data["env_changes"]:
        lines.append("环境变化 " + "；".join(data["env_changes"]))
    lines.append("")
    lines.append(bold("分组"))
    for group in data["groups"]:
        lines.append(
            "  [%s] #%d–#%d  %d 条 · %s"
            % (
                group["task"],
                group["start"],
                group["end"],
                group["count"],
                " → ".join(group["phases"]) if group["phases"] else "推进",
            )
        )
    lines.append("")
    lines.append(bold("命令"))
    for row in data["commands"]:
        lines.append(
            "  #%-4d %s %s  %s  %s  %s"
            % (
                row["seq"],
                _status_from_data(row),
                row["time"],
                truncate(row["cmd"], 46),
                row["role_label"],
                truncate(row["purpose"] or row["intent"] or "", 88),
            )
        )
        if row["error"]:
            lines.append(grey("        错误 %s" % row["error"]))
    return "\n".join(lines)


def _status_from_data(row):
    return {"ok": "✓", "fail": "✗", "suspected": "?"}.get(row["status"], "·")
