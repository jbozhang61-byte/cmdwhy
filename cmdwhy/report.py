"""终端报告渲染：时间线、单条解释、四段式复盘、统计、知识库、纠错建议。"""

from __future__ import annotations

import os
import random
from collections import Counter, defaultdict

from .hints import hint_for
from .intent import classify_intent
from .model import CONFIDENCE_LABELS, STATUS_FAIL, STATUS_OK, STATUS_SUSPECT, STATUS_UNKNOWN
from .util import (
    Paint,
    bar,
    fmt_date,
    fmt_datetime,
    fmt_duration,
    fmt_span,
    fmt_time,
    percent,
    short_path,
    truncate,
)

MARK = chr(96)


def inline_code(text):
    return MARK + str(text).replace(MARK, "'") + MARK


class Renderer:
    def __init__(self, paint=None, home=None):
        self.p = paint or Paint(False)
        self.home = home or os.path.expanduser("~")

    # ------------------------------------------------------------ 小工具

    def _path(self, path, width=34):
        return short_path(path, self.home, width)

    def _status(self, ann, event) -> str:
        p = self.p
        if ann.status == STATUS_OK:
            text = "✓ 成功"
            if event.exit_code is not None:
                text += "（0）"
            return p(text, "green")
        if ann.status == STATUS_FAIL:
            text = "✗ 失败"
            if event.exit_code is not None:
                text += "（%s）" % event.exit_code
            return p(text, "red")
        if ann.status == STATUS_SUSPECT:
            return p("? 疑似失败（无退出码，靠上下文推断）", "yellow")
        return p("· 未记录退出码", "grey")

    def _env_parts(self, env):
        parts = []
        if env is None:
            return parts
        if env.cwd:
            parts.append(self._path(env.cwd, 30))
        if env.project:
            kind = "(%s)" % env.project_kind if env.project_kind else ""
            parts.append(env.project + kind)
        if env.branch:
            parts.append("git:" + env.branch + ("*" if env.dirty else ""))
        if env.venv:
            parts.append("venv:" + env.venv)
        if env.distro:
            parts.append(env.distro)
        return parts

    def _env_line(self, env):
        parts = self._env_parts(env)
        return " · ".join(parts) if parts else "环境未知"

    def _session_header(self, session):
        p = self.p
        title = p.bold("── " + session.sid)
        span = fmt_span(session.start_ts, session.end_ts)
        duration = fmt_duration(session.duration) if session.duration else "时长未知"
        meta = " · ".join([span, duration, self._env_line(session.env)])
        return [title + "  " + p(meta, "grey")]

    def _session_summary(self, analysis, session):
        fails = sum(1 for ev in session.events if analysis.ann(ev.seq).status == STATUS_FAIL)
        suspected = sum(1 for ev in session.events if analysis.ann(ev.seq).status == STATUS_SUSPECT)
        fixes = sum(1 for ev in session.events if analysis.ann(ev.seq).fix_of)
        bits = ["%d 条命令" % session.n]
        if fails:
            bits.append("%d 处报错" % fails)
        if suspected:
            bits.append("%d 处疑似失败" % suspected)
        if fixes:
            bits.append("%d 个修复动作" % fixes)
        return "   " + self.p(" · ".join(bits), "grey")

    def _event_head(self, event):
        hist = ("h%d" % event.hist_id) if event.hist_id is not None else ""
        stable = ("e" + event.uid) if event.uid else ""
        return "  #%-3d %s  %s %s %s" % (
            event.seq,
            fmt_time(event.ts),
            self.p((hist.ljust(6) + stable).ljust(18), "grey"),
            self.p("$", "grey"),
            self.p(truncate(event.cmd, 96), "bold"),
        )

    def _ref(self, analysis, seq):
        try:
            event = analysis.event(seq)
        except Exception:
            return "#%d" % seq
        if getattr(event, "uid", ""):
            return "#%d[e%s]" % (seq, event.uid)
        return "#%d" % seq

    # ------------------------------------------------------------ 时间线

    def render_timeline(self, analysis, limit=20, sid=None, verbose=False):
        if not analysis.events:
            return "没有命令记录。先运行 " + self.p.bold("cmdwhy ingest") + " 或 " + self.p.bold("cmdwhy hook install") + "。"
        events = analysis.events
        if sid:
            events = [ev for ev in events if ev.sid == sid]
            if not events:
                return "没有找到会话 %s。" % sid
        shown = events[-limit:]
        shown_seqs = {ev.seq for ev in shown}
        lines = []
        title = self.p.bold("命令时间线")
        lines.append(
            title
            + "  "
            + self.p(
                "最近 %d 条 / 共 %d 条 · %d 个会话" % (len(shown), len(analysis.events), len(analysis.sessions)),
                "grey",
            )
        )
        if any(event.hist_id is not None for event in analysis.events):
            hint = "h518 = history 编号；e1a2b3c4 = 稳定 ID；#18 = 当前顺序（新增历史会变）。推荐 cmdwhy explain e1a2b3c4"
        else:
            hint = "e1a2b3c4 = 稳定 ID（推荐）；#12 = 当前顺序（会变）。cmdwhy history 显示两者"
        lines.append(self.p(hint, "grey"))
        lines.append("")
        for session in analysis.sessions:
            session_events = [ev for ev in session.events if ev.seq in shown_seqs]
            if not session_events:
                continue
            lines.extend(self._session_header(session))
            lines.append(self._session_summary(analysis, session))
            for event in session_events:
                lines.extend(self._event_block(analysis, event, verbose=verbose))
            lines.append("")
        return "\n".join(lines).rstrip()

    def _event_block(self, analysis, event, verbose=False):
        ann = analysis.ann(event.seq)
        p = self.p
        lines = [self._event_head(event)]
        detail = ["       " + self._status(ann, event)]
        if ann.intent and ann.status == STATUS_OK:
            detail.append(ann.intent)
        elif ann.intent:
            detail.append("意图：" + ann.intent)
        if ann.novelty:
            detail.append(p("新增", "magenta"))
        if ann.danger == "danger":
            detail.append(p("危险操作", "red"))
        lines.append("  ".join(detail))
        if ann.error is not None:
            lines.append(
                "       "
                + p("报错", "red")
                + "  "
                + p(ann.error.signature, "bold")
                + "  "
                + p(truncate(ann.error.detail, 96), "grey")
            )
        if ann.motivation and ann.motivation != ann.intent:
            lines.append("       " + p("动机", "cyan") + "  " + ann.motivation)
        if ann.fix_of:
            source = analysis.ann(ann.fix_of[0])
            lines.append(
                "       "
                + p("修复", "green")
                + "  %s 的 %s" % (self._ref(analysis, source.seq), source.error.signature if source.error else "失败")
            )
        if ann.steps:
            text = " → ".join(truncate(step, 46) for step in ann.steps)
            mark = p("  ✓ 已验证", "green") if ann.verified else p("  未验证", "yellow")
            lines.append("       " + p("修复链", "green") + "  " + text + mark)
        if ann.correction:
            conf = CONFIDENCE_LABELS.get(ann.correction.get("confidence"), "")
            lines.append(
                "       "
                + p("更正", "yellow")
                + "  "
                + p(ann.correction["command"], "bold")
                + p("（%s）" % conf, "grey")
            )
        if ann.changes:
            lines.append("       " + p("改变", "blue") + "  " + "；".join(ann.changes))
        if verbose:
            if ann.task:
                lines.append("       " + p("任务", "cyan") + "  " + ann.task + " · " + (ann.phase or "推进"))
            if ann.purpose:
                lines.append("       " + p("目的", "cyan") + "  " + truncate(ann.purpose, 100))
            for evidence in ann.evidence:
                if evidence.startswith(("报错", "推测", "改变")):
                    continue
                lines.append("       " + p("·", "grey") + " " + p(truncate(evidence, 100), "grey"))
        return lines

    # ------------------------------------------------------------ 编号列表

    def render_history_list(self, analysis, limit=50, sid=None, grep=None, duplicates=False, show_all=False):
        rows, totals = build_history_rows(analysis, sid=sid, grep=grep, duplicates=duplicates)
        p = self.p
        if not rows:
            if duplicates:
                return "没有重复出现的命令。"
            if grep:
                return "没有匹配 %s 的命令。" % grep
            return "没有命令记录。"
        selected = rows if show_all else rows[-limit:]
        repeat_commands = sum(1 for count in totals.values() if count > 1)
        meta = ["共 %d 条" % sum(totals.values()), "显示 %d 条" % len(selected)]
        if repeat_commands:
            meta.append("%d 个命令重复出现" % repeat_commands)
        if duplicates:
            meta.append("只看重复")
        if grep:
            meta.append("过滤 %s" % grep)
        lines = [p.bold("命令编号") + "  " + p(" · ".join(meta), "grey")]
        if any(row["hist_id"] is not None for row in rows):
            lines.append(p("编号来自 history 输出；没有 history 编号的显示为 #分析序号。查看：cmdwhy explain <编号>", "grey"))
        else:
            lines.append(p("编号是 cmdwhy 的分析序号。查看：cmdwhy explain <编号>", "grey"))
        lines.append("")
        for row in selected:
            stamp = fmt_time(row["ts"]) if row["ts"] else "--:--:--"
            marker = ""
            if row["total"] > 1:
                marker = p("  （第 %d/%d 次）" % (row["occurrence"], row["total"]), "grey")
            stable = ("e" + row["uid"]) if row.get("uid") else " " * 11
            lines.append("  %6s  %-11s  %s  %s%s" % (row["id"], stable, stamp, truncate(row["cmd"], 80), marker))
        lines.append("")
        lines.append(p("重复命令会显示“第 k/n 次”，每个编号对应一次具体执行，可直接 cmdwhy explain <编号>。", "grey"))
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 会话概要

    def render_summary(self, analysis, sessions):
        p = self.p
        lines = [p.bold("会话概要") + "  " + p("%d 个会话" % len(sessions), "grey")]
        for session in sessions:
            lines.append("")
            lines.append(
                p.bold("── " + session.sid)
                + "  "
                + p(
                    "%s · %s · %s"
                    % (
                        fmt_span(session.start_ts, session.end_ts),
                        fmt_duration(session.duration) if session.duration else "时长未知",
                        self._env_line(session.env),
                    ),
                    "grey",
                )
            )
            fails = [analysis.ann(event.seq) for event in session.events if analysis.ann(event.seq).status in ("fail", "suspected")]
            fixes = [analysis.ann(event.seq) for event in session.events if analysis.ann(event.seq).steps]
            verified = sum(1 for ann in fixes if ann.verified)
            lines.append(
                "   %d 条命令 · %d 处报错 · %d 个修复动作%s"
                % (session.n, len(fails), len(fixes), "（%d 已验证）" % verified if verified else "")
            )
            tasks = []
            for event in session.events:
                task = analysis.ann(event.seq).task
                if task and task != "日常操作" and task not in tasks:
                    tasks.append(task)
            if tasks:
                lines.append("   任务  " + " · ".join(tasks[:4]))
            error_counts = Counter(ann.error.signature for ann in fails if ann.error is not None)
            if error_counts:
                lines.append(
                    "   错误  "
                    + " · ".join("%s ×%d" % (name, count) for name, count in error_counts.most_common(4))
                )
            steps = []
            for ann in fixes:
                for step in ann.steps:
                    if step not in steps:
                        steps.append(step)
            if steps:
                lines.append("   修复  " + " › ".join(truncate(step, 34) for step in steps[:4]))
            changes = []
            for event in session.events:
                for change in analysis.ann(event.seq).changes:
                    if change not in changes:
                        changes.append(change)
            if changes:
                lines.append("   改变  " + " · ".join(changes[:4]))
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 搜索

    def render_search(self, analysis, results, total=0, query="", filters=None):
        p = self.p
        title = p.bold("命令搜索")
        meta = []
        if query:
            meta.append("关键词：" + query)
        for item in filters or []:
            meta.append(item)
        meta.append("显示 %d / 共 %d 条" % (len(results), total))
        lines = [title + "  " + p(" · ".join(meta), "grey")]
        if not results:
            lines.append("")
            lines.append("没有匹配的命令。")
            return "\n".join(lines)
        lines.append("")
        for result in results:
            status = {
                "ok": ("✓", "green"),
                "fail": ("✗", "red"),
                "suspected": ("?", "yellow"),
                "unknown": ("·", "grey"),
            }.get(result.status, ("·", "grey"))
            error = ("  " + p(result.error, "red")) if result.error else ""
            lines.append(
                "  #%-3d %-11s %s  %s  %s  %s%s"
                % (
                    result.seq,
                    p(("e" + result.uid) if result.uid else "", "cyan"),
                    p(("h%d" % result.hist_id).ljust(6) if result.hist_id is not None else " " * 6, "grey"),
                    fmt_time(result.ts),
                    p(status[0], status[1]),
                    p(truncate(result.cmd, 64), "bold"),
                    error,
                )
            )
            detail = []
            if result.task:
                detail.append(result.task)
            if result.intent:
                detail.append(result.intent)
            if result.project:
                detail.append(result.project)
            if result.cwd:
                detail.append(self._path(result.cwd, 28))
            if detail:
                lines.append("       " + p(" · ".join(detail), "grey"))
        lines.append("")
        lines.append(p("查看详情：cmdwhy explain <编号>；e开头的是稳定 ID，新增历史后不会变", "grey"))
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 下一步计划

    def render_plan(self, analysis, plan, mode="suggest"):
        p = self.p
        lines = [p.bold("下一步计划")]
        meta = []
        if plan.focus_seq:
            meta.append("基于 " + self._ref(analysis, plan.focus_seq))
        if plan.task:
            meta.append(plan.task)
        if meta:
            lines.append("  " + p(" · ".join(meta), "grey"))
        if plan.goal:
            lines.append("  目标  " + plan.goal)
        if not plan.actions:
            lines.append("")
            lines.append("  没有推断出明确的下一步。可以先运行 cmdwhy explain <编号> 看上下文。")
            return "\n".join(lines).rstrip()
        risks = {"low": "低", "medium": "中", "high": "高"}
        for index, action in enumerate(plan.actions, 1):
            label = risks.get(action.risk, action.risk)
            lines.append("")
            lines.append("  %d. [%s风险] %s" % (index, label, p(action.command, "bold", "green")))
            suffix = ""
            if not action.executable:
                suffix = "（仅建议：需在交互 shell 执行）"
            elif action.risk == "high":
                suffix = "（高风险，永不自动执行）"
            elif action.risk == "medium":
                suffix = "（写操作，auto 不执行，需 --yes）"
            lines.append("       " + action.reason + p(suffix, "yellow"))
        lines.append("")
        if mode == "auto":
            lines.append(p("当前模式 auto：只自动执行低风险步骤；写操作需 cmdwhy do --yes；高风险永不自动执行。", "yellow"))
        elif mode == "off":
            lines.append(p("当前模式 off：先 cmdwhy mode suggest 再使用。", "yellow"))
        else:
            lines.append(p("当前模式 suggest：只给计划；cmdwhy do --yes 执行低/中风险；cmdwhy mode auto 只自动跑低风险。", "grey"))
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 单条解释

    def render_explain(self, analysis, seqs, verbose=True):
        lines = []
        for seq in seqs:
            if seq < 1 or seq > len(analysis.events):
                lines.append("没有 #%d 这条命令。" % seq)
                continue
            event = analysis.event(seq)
            ann = analysis.ann(seq)
            session = analysis.session_of.get(seq)
            lines.append("")
            lines.append(
                self.p.bold("#%d" % seq)
                + ("  " + self.p("e" + event.uid, "cyan") if event.uid else "")
                + "  "
                + self.p(fmt_datetime(event.ts), "grey")
            )
            lines.append("─" * 74)
            lines.append("命令    " + self.p(event.cmd, "bold"))
            if event.uid:
                lines.append("稳定 ID  " + self.p("e" + event.uid, "cyan") + "（推荐；新增历史后也不会变）")
            result = self._status(ann, event)
            if event.duration_ms:
                result += self.p("  用时 %s" % fmt_duration(event.duration_ms / 1000.0), "grey")
            lines.append("结果    " + result)
            conf = CONFIDENCE_LABELS.get(ann.status_conf, "")
            basis = "退出码/错误原文" if ann.status_conf == "high" else ("仅退出码" if ann.status_conf == "medium" else "上下文推断")
            lines.append("置信度  " + conf + "（依据：" + basis + "）")
            lines.append("意图    " + (ann.intent or "未知"))
            if ann.motivation:
                lines.append("动机    " + ann.motivation)
            context = analysis.contexts.get(seq) if getattr(analysis, "contexts", None) else None
            if ann.task:
                task_conf = CONFIDENCE_LABELS.get(context.confidence, "") if context is not None else ""
                suffix = "（任务判断 " + task_conf + "）" if task_conf else ""
                lines.append("任务    " + ann.task + " · " + (ann.phase or "推进") + suffix)
            if ann.task_goal:
                lines.append("目标    " + ann.task_goal)
            if ann.purpose:
                lines.append("目的    " + ann.purpose)
            if ann.error is not None:
                prefix = "推测" if ann.error.inferred else "报错"
                lines.append("错误    " + self.p(ann.error.signature, "bold") + "  " + ann.error.detail)
                if ann.error.exit_code is not None:
                    lines.append("退出码  " + str(ann.error.exit_code))
            env = analysis.envs.get(seq) if getattr(analysis, "envs", None) else None
            env = env or (session.env if session else None)
            lines.append("环境    " + self.p(self._env_line(env), "grey"))
            if session:
                lines.append(
                    "位置    会话 %s 第 %d 条 / 共 %d 条" % (session.sid, session.events.index(event) + 1, session.n)
                )
            if event.hist_id is not None:
                lines.append("历史编号  %d（cmdwhy explain %d 可直接定位）" % (event.hist_id, event.hist_id))
            explanation = self.why_sentence(analysis, ann)
            if explanation:
                lines.append("推断    " + explanation)
            if ann.evidence:
                lines.append("依据")
                for evidence in ann.evidence:
                    lines.append("  · " + evidence)
            if ann.context_summary:
                lines.append("上下文  " + ann.context_summary)
            hint = hint_for(ann.error.signature) if ann.error is not None else None
            if hint and (ann.status in (STATUS_FAIL, STATUS_SUSPECT) or ann.fix_of):
                lines.append("建议    " + hint["next"])
            if ann.correction:
                lines.append(
                    "更正    "
                    + self.p(ann.correction["command"], "bold")
                    + "  "
                    + p_join(ann.correction.get("reasons", []))
                )
            if seq < len(analysis.events):
                nxt = analysis.event(seq + 1)
                nxt_ann = analysis.ann(seq + 1)
                lines.append("后续    %s %s  %s" % (self._ref(analysis, nxt.seq), truncate(nxt.cmd, 50), self._status(nxt_ann, nxt)))
        return "\n".join(lines).strip()

    def why_sentence(self, analysis, ann):
        event = analysis.event(ann.seq)
        session = analysis.session_of.get(ann.seq)
        env = session.env if session else None
        where = ""
        if env is not None:
            if env.project:
                where = "在 %s 项目里" % env.project
            elif event.cwd:
                where = "在 %s 下" % self._path(event.cwd)
        intent = ann.intent or "执行命令"
        if ann.fix_of:
            source = analysis.ann(ann.fix_of[0])
            sig = source.error.signature if source.error else "上一条失败"
            text = "为了修复 %s 的 %s，你%s%s" % (self._ref(analysis, source.seq), sig, where, intent)
            if source.verified:
                if source.verified_at == ann.seq:
                    text += "；这条命令本身就是修复后的重跑，验证通过。"
                else:
                    text += "；%s 的重跑确认了修复生效。" % self._ref(analysis, source.verified_at)
            else:
                text += "；目前还没看到重跑验证。"
            return text
        if ann.status in (STATUS_FAIL, STATUS_SUSPECT):
            text = "%s%s%s" % (where, intent, "，但执行失败了")
            if ann.steps:
                text += "；你随后用 " + "、".join(ann.steps) + " 继续处理。"
            else:
                text += "，之后没有明显的修复动作。"
            return text
        if ann.motivation and ann.motivation.startswith("排查"):
            return "%s上一条命令失败，这条是只读排查（%s），目的是先看清事实再改。" % (where, intent)
        if ann.motivation and ann.motivation.startswith("重试"):
            return "%s上一条同类命令没有成功，这条是重试；如果反复出现，说明不是偶发问题。" % where
        if ann.motivation and ann.motivation.startswith("会话开始"):
            return "会话刚开始，你先确认环境和项目状态，属于探索性操作。"
        if ann.novelty:
            return "%s第一次出现这类操作（%s），通常是新任务或新环境带来的。" % (where, intent)
        return "%s%s。" % (where, intent)

    # ------------------------------------------------------------ 四段式报告

    def render_report(self, analysis, sections=None, random_n=2, seed=None):
        sections = sections or ["errors", "changes", "additions", "random"]
        stats = analysis.stats
        p = self.p
        lines = []
        lines.append(p.bold("# 命令历史注解报告"))
        import time as _time

        lines.append(
            p(
                "生成于 %s · %d 条命令 / %d 个会话 · 数据源：%s"
                % (
                    fmt_datetime(_time.time()),
                    stats["events"],
                    stats["sessions"],
                    "、".join(os.path.basename(path) for path in analysis.sources) or "未知",
                ),
                "grey",
            )
        )
        if analysis.warnings:
            for warning in analysis.warnings:
                lines.append(p("警告：" + warning, "yellow"))
        lines.append("")
        lines.append(p.bold("## 概览"))
        lines.append(
            "  成功 %d · 失败 %d（已确认 %d / 推测 %d）· 未记录退出码 %d"
            % (stats["ok"], stats["fail"] + stats["suspected"], stats["fail"], stats["suspected"], stats["unknown"])
        )
        if stats["known"]:
            lines.append(
                "  错误率 %s（已知状态的 %d 条中 %d 条失败）"
                % (percent(stats["fail"], stats["known"]), stats["known"], stats["fail"])
            )
        lines.append(
            "  修复链 %d 条，已验证 %d 条%s"
            % (
                stats["chains"],
                stats["verified_chains"],
                "，平均修复耗时 " + fmt_duration(stats["mttr"]) if stats.get("mttr") else "",
            )
        )
        lines.append(
            "  新增命令 %d 条 · 环境改变 %d 次 · 危险命令 %d 条"
            % (stats["novelty"], stats["changes"], stats["danger"])
        )
        if stats["signatures"]:
            lines.append("  高频错误：" + " · ".join("%s ×%d" % (sig, count) for sig, count in stats["signatures"][:5]))
        lines.append("")
        if "errors" in sections:
            lines.extend(self._report_errors(analysis))
        if "changes" in sections:
            lines.extend(self._report_changes(analysis))
        if "additions" in sections:
            lines.extend(self._report_additions(analysis))
        if "random" in sections:
            lines.extend(self._report_random(analysis, random_n, seed))
        return "\n".join(lines).rstrip()

    def _report_errors(self, analysis):
        p = self.p
        groups = defaultdict(list)
        for ann in analysis.anns:
            if ann.error is None:
                continue
            groups[ann.error.signature].append(ann)
        lines = [p.bold("## 一、报错：错在哪，后来怎么好的")]
        if not groups:
            lines.append("  没有捕获到报错。")
            lines.append("")
            return lines
        ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
        index = 1
        for signature, anns in ordered:
            fails = [ann for ann in anns if ann.status in (STATUS_FAIL, STATUS_SUSPECT)]
            if not fails:
                continue
            hint = hint_for(signature)
            lines.append("")
            lines.append(
                p.bold("### %d. %s" % (index, signature))
                + "  "
                + p("%s（%d 次）" % (hint["title"], len(fails)), "grey")
            )
            for ann in fails:
                event = analysis.event(ann.seq)
                lines.append(
                    "  %s %s  %s  %s"
                    % (self._ref(analysis, ann.seq), fmt_time(event.ts), truncate(event.cmd, 60), self._status(ann, event))
                )
                lines.append("       错误  " + truncate(ann.error.detail, 110))
                if ann.steps:
                    mark = "✓ 已验证" if ann.verified else "未验证"
                    lines.append("       修复  %s  →  %s" % (" → ".join(ann.steps), mark))
                    if ann.verified_at:
                        if ann.verified:
                            lines.append(
                                "       验证  %s %s 成功重跑"
                                % (self._ref(analysis, ann.verified_at), truncate(analysis.event(ann.verified_at).cmd, 50))
                            )
                        else:
                            lines.append(
                                "       重跑  %s %s（未记录退出码）"
                                % (self._ref(analysis, ann.verified_at), truncate(analysis.event(ann.verified_at).cmd, 50))
                            )
                elif ann.error.inferred:
                    lines.append("       修复  没看到明显的修复动作")
                if ann.correction:
                    lines.append("       更正  " + ann.correction["command"])
            lines.append("       建议  " + hint["next"])
            index += 1
        lines.append("")
        return lines

    def _report_changes(self, analysis):
        p = self.p
        lines = [p.bold("## 二、改变：环境/项目状态动了什么")]
        items = [(ann, analysis.event(ann.seq)) for ann in analysis.anns if ann.changes]
        if not items:
            lines.append("  没有识别到环境变化。")
            lines.append("")
            return lines
        for ann, event in items:
            for change in ann.changes:
                lines.append(
                    "  #%-3d %s  %-34s %s"
                    % (event.seq, fmt_time(event.ts), truncate(change, 34), p(truncate(event.cmd, 46), "grey"))
                )
        lines.append("")
        return lines

    def _report_additions(self, analysis):
        p = self.p
        lines = [p.bold("## 三、添加：第一次出现的命令")]
        items = [(ann, analysis.event(ann.seq)) for ann in analysis.anns if ann.novelty]
        if not items:
            lines.append("  没有新增命令。")
            lines.append("")
            return lines
        for ann, event in items:
            lines.append(
                "  #%-3d %s  %-22s %s"
                % (
                    event.seq,
                    fmt_time(event.ts),
                    truncate(event.head, 22),
                    p(truncate(classify_intent(event), 40), "grey"),
                )
            )
        lines.append("")
        return lines

    def _report_random(self, analysis, n, seed):
        p = self.p
        lines = [p.bold("## 四、随机：回看 %d 个会话" % n)]
        sessions = [session for session in analysis.sessions if session.n > 1]
        if not sessions:
            lines.append("  没有足够的会话可供抽样。")
            lines.append("")
            return lines
        rng = random.Random(seed)
        picked = rng.sample(sessions, min(n, len(sessions)))
        for session in picked:
            lines.append("")
            lines.append(
                "### 会话 %s · %s · %s"
                % (session.sid, fmt_span(session.start_ts, session.end_ts), self._env_line(session.env))
            )
            fails = [
                analysis.ann(ev.seq)
                for ev in session.events
                if analysis.ann(ev.seq).status in (STATUS_FAIL, STATUS_SUSPECT)
            ]
            fixes = [analysis.ann(ev.seq) for ev in session.events if analysis.ann(ev.seq).fix_of]
            intents = Counter(analysis.ann(ev.seq).intent for ev in session.events if analysis.ann(ev.seq).intent)
            lines.append("  %d 条命令 · %d 处报错 · %d 个修复动作" % (session.n, len(fails), len(fixes)))
            lines.append(
                "  主要意图：" + " · ".join("%s×%d" % (name, count) for name, count in intents.most_common(4))
            )
            for ann in fails[:3]:
                event = analysis.event(ann.seq)
                lines.append(
                    "  报错  %s %s  %s"
                    % (self._ref(analysis, ann.seq), truncate(event.cmd, 42), ann.error.signature if ann.error else "")
                )
                if ann.steps:
                    lines.append("        修复  " + " → ".join(ann.steps))
        lines.append("")
        return lines

    def render_digest(self, analysis, n=2, seed=None):
        body = self._report_random(analysis, n, seed)
        lines = [self.p.bold("随机回看")] + body[1:]
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 统计

    def render_stats(self, analysis):
        p = self.p
        stats = analysis.stats
        lines = [p.bold("命令历史统计")]
        lines.append("")
        span = fmt_span(stats.get("first_ts"), stats.get("last_ts"))
        lines.append("  覆盖范围  %s · %d 个会话 · %d 条命令" % (span, stats["sessions"], stats["events"]))
        lines.append(
            "  状态      成功 %d · 失败 %d（确认 %d / 推测 %d）· 未记录 %d"
            % (stats["ok"], stats["fail"] + stats["suspected"], stats["fail"], stats["suspected"], stats["unknown"])
        )
        if stats["known"]:
            lines.append(
                "  错误率    %s（已知状态的 %d 条中 %d 条失败）"
                % (percent(stats["fail"], stats["known"]), stats["known"], stats["fail"])
            )
        lines.append(
            "  修复      %d 条修复链 · %d 条已验证%s"
            % (
                stats["chains"],
                stats["verified_chains"],
                " · 平均修复 " + fmt_duration(stats["mttr"]) if stats.get("mttr") else "",
            )
        )
        if stats["sudo"]:
            lines.append("  sudo      %d 次（%s）" % (stats["sudo"], percent(stats["sudo"], stats["events"])))
        lines.append(
            "  新增/改变 %d 条新增命令 · %d 次环境改变 · %d 条危险命令"
            % (stats["novelty"], stats["changes"], stats["danger"])
        )
        lines.append("")
        if stats["intents"]:
            lines.append("  意图分布")
            top = stats["intents"][0][1] or 1
            for name, count in stats["intents"][:8]:
                lines.append("    %-18s %3d  %s" % (truncate(name, 18), count, p(bar(count / float(top), 14), "cyan")))
        if stats["commands"]:
            lines.append("")
            lines.append("  常用命令  " + " · ".join("%s×%d" % (name, count) for name, count in stats["commands"][:8]))
        if stats["signatures"]:
            lines.append("  高频错误  " + " · ".join("%s×%d" % (name, count) for name, count in stats["signatures"][:6]))
        lines.append("")
        if stats["unknown"] > stats["events"] / 2:
            lines.append(
                p(
                    "提示：超过一半的命令没有退出码。运行 cmdwhy hook install 后，新命令会带上退出码和错误原文，注解会准得多。",
                    "yellow",
                )
            )
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 会话/变化/新增

    def render_sessions(self, analysis):
        p = self.p
        lines = [p.bold("会话列表")]
        lines.append("")
        for session in analysis.sessions:
            fails = sum(
                1 for ev in session.events if analysis.ann(ev.seq).status in (STATUS_FAIL, STATUS_SUSPECT)
            )
            fixes = sum(1 for ev in session.events if analysis.ann(ev.seq).fix_of)
            lines.append(
                "  %-4s %-26s %3d 条 · %d 报错 · %d 修复 · %s"
                % (
                    session.sid,
                    fmt_span(session.start_ts, session.end_ts),
                    session.n,
                    fails,
                    fixes,
                    self._env_line(session.env),
                )
            )
        return "\n".join(lines).rstrip()

    def render_changes(self, analysis):
        p = self.p
        lines = [p.bold("环境/状态变化")]
        lines.append("")
        count = 0
        for ann in analysis.anns:
            if not ann.changes:
                continue
            event = analysis.event(ann.seq)
            for change in ann.changes:
                lines.append(
                    "  #%-3d %s  %-36s %s"
                    % (event.seq, fmt_time(event.ts), truncate(change, 36), p(truncate(event.cmd, 46), "grey"))
                )
                count += 1
        if not count:
            lines.append("  没有识别到环境变化。")
        return "\n".join(lines).rstrip()

    def render_additions(self, analysis):
        p = self.p
        lines = [p.bold("新增命令（第一次出现）")]
        lines.append("")
        count = 0
        for ann in analysis.anns:
            if not ann.novelty:
                continue
            event = analysis.event(ann.seq)
            lines.append(
                "  #%-3d %s  %-20s %s"
                % (event.seq, fmt_time(event.ts), truncate(event.head, 20), p(truncate(ann.intent, 44), "grey"))
            )
            count += 1
        if not count:
            lines.append("  没有新增命令。")
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 知识库 / 诊断 / 纠错

    def render_kb(self, knowledge):
        p = self.p
        summary = knowledge.summary()
        lines = [p.bold("错误知识库")]
        lines.append(
            "  %d 个错误签名 · 累计 %d 次出现 · %d 次验证有效 · 更新于 %s"
            % (
                summary["signatures"],
                summary["occurrences"],
                summary["verified_fixes"],
                fmt_datetime(summary["updated"]),
            )
        )
        lines.append("")
        if not knowledge.entries:
            lines.append("  还是空的。运行 cmdwhy ingest 之后，修复链会自动沉淀进来。")
            return "\n".join(lines)
        for signature in sorted(knowledge.entries):
            entry = knowledge.entries[signature]
            lines.append(
                p.bold(signature)
                + "  "
                + p(
                    "%s · 出现 %d 次"
                    % (hint_for(entry.get("category")).get("title", ""), int(entry.get("count") or 0)),
                    "grey",
                )
            )
            remedies = knowledge.lookup(signature, entry.get("category"), limit=5)
            for index, remedy in enumerate(remedies, 1):
                lines.append("    %d. %s" % (index, remedy.command))
                lines.append(
                    p("       有效 %d 次 · 最近 %s" % (remedy.verified, fmt_date(remedy.last_ts)), "grey")
                )
            if not remedies:
                lines.append("    （还没有沉淀出修复命令）")
            samples = entry.get("samples") or []
            if samples:
                lines.append("    错误样例：" + truncate(samples[0], 90))
            lines.append("")
        return "\n".join(lines).rstrip()

    def render_fixes(self, cmd, fixes):
        p = self.p
        lines = [p.bold("命令输入检查") + "  " + p(cmd, "grey")]
        if not fixes:
            lines.append("  没有找到足够相近的已知命令。")
            return "\n".join(lines)
        for index, fix in enumerate(fixes, 1):
            confidence = CONFIDENCE_LABELS.get(fix.confidence, "")
            lines.append("")
            lines.append("  %d. %s   %s" % (index, p(fix.command, "bold", "green"), p("可信度 " + confidence, "grey")))
            for reason in fix.reasons:
                lines.append("     · " + reason)
        best = fixes[0]
        lines.append("")
        if best.kind == "install":
            lines.append("建议先查包名： " + p("command-not-found " + (best.command.split()[0] if best.command else ""), "bold"))
            return "\n".join(lines).rstrip()
        lines.append("建议执行： " + p(best.command, "bold", "green"))
        return "\n".join(lines).rstrip()

    def render_diagnosis(self, signature, category, occurrences, remedies, fixes=None, source=None):
        p = self.p
        hint = hint_for(signature or category)
        lines = [p.bold("错误诊断") + "  " + p(signature, "bold")]
        meta = []
        if occurrences:
            meta.append("你的历史里出现过 %d 次" % occurrences)
        if source:
            meta.append(source)
        if meta:
            lines.append("  " + p(" · ".join(meta), "grey"))
        lines.append("")
        lines.append("  " + p("这是什么", "cyan") + "  " + hint["title"])
        lines.append("  " + p("为什么", "cyan") + "  " + hint["why"])
        verified_remedies = [remedy for remedy in remedies if remedy.verified > 0]
        if verified_remedies:
            lines.append("")
            lines.append("  " + p("你以前这样修好过（按有效次数排序）", "green"))
            for index, remedy in enumerate(verified_remedies, 1):
                lines.append("    %d. %s" % (index, p(remedy.command, "bold")))
                lines.append(
                    p("       有效 %d 次 · 最近 %s" % (remedy.verified, fmt_date(remedy.last_ts)), "grey")
                )
                if remedy.sample:
                    lines.append(p("       当时错误：" + truncate(remedy.sample, 80), "grey"))
        elif remedies:
            lines.append("")
            lines.append("  " + p("知识库里只有未验证的修法，以下仅供参考", "yellow"))
            for index, remedy in enumerate(remedies, 1):
                lines.append("    %d. %s" % (index, p(remedy.command, "bold")))
                lines.append(p("       还没有重跑验证过", "grey"))
        else:
            lines.append("")
            lines.append("  " + p("知识库里还没有同类修复记录，先用通用建议。", "yellow"))
        lines.append("")
        lines.append("  " + p("下一步", "cyan") + "  " + hint["next"])
        lines.append("  " + p("要避免", "cyan") + "  " + hint["avoid"])
        if fixes:
            lines.append("")
            lines.append("  " + p("针对这条输入，可能是", "yellow"))
            for index, fix in enumerate(fixes, 1):
                lines.append("    %d. %s" % (index, p(fix.command, "bold")))
                if fix.reasons:
                    lines.append(p("       " + "；".join(fix.reasons[:3]), "grey"))
        return "\n".join(lines).rstrip()

    # ------------------------------------------------------------ 导出

    def render_markdown(self, analysis, sections=None, random_n=2, seed=None):
        sections = sections or ["errors", "changes", "additions", "random"]
        stats = analysis.stats
        lines = ["# 命令历史注解报告", ""]
        lines.append(
            "> %d 条命令 / %d 个会话 · 数据源：%s"
            % (
                stats["events"],
                stats["sessions"],
                "、".join(os.path.basename(path) for path in analysis.sources) or "未知",
            )
        )
        lines.append("")
        lines.append("## 概览")
        lines.append("")
        lines.append(
            "- 成功 %d，失败 %d（确认 %d / 推测 %d），未记录退出码 %d"
            % (stats["ok"], stats["fail"] + stats["suspected"], stats["fail"], stats["suspected"], stats["unknown"])
        )
        if stats["known"]:
            lines.append(
                "- 错误率 %s（已知状态的 %d 条中失败 %d 条）"
                % (percent(stats["fail"], stats["known"]), stats["known"], stats["fail"])
            )
        lines.append(
            "- 修复链 %d 条，已验证 %d 条%s"
            % (
                stats["chains"],
                stats["verified_chains"],
                "，平均修复耗时 " + fmt_duration(stats["mttr"]) if stats.get("mttr") else "",
            )
        )
        lines.append(
            "- 新增命令 %d 条，环境改变 %d 次，危险命令 %d 条" % (stats["novelty"], stats["changes"], stats["danger"])
        )
        if stats["signatures"]:
            lines.append("- 高频错误：" + "、".join("%s ×%d" % (sig, count) for sig, count in stats["signatures"][:6]))
        lines.append("")
        if "errors" in sections:
            lines.extend(self._markdown_errors(analysis))
        if "changes" in sections:
            lines.append("## 改变：环境/项目状态动了什么")
            lines.append("")
            items = [(ann, analysis.event(ann.seq)) for ann in analysis.anns if ann.changes]
            if not items:
                lines.append("没有识别到环境变化。")
            for ann, event in items:
                for change in ann.changes:
                    lines.append("- %s %s — %s" % (fmt_time(event.ts), change, inline_code(event.cmd)))
            lines.append("")
        if "additions" in sections:
            lines.append("## 添加：第一次出现的命令")
            lines.append("")
            items = [(ann, analysis.event(ann.seq)) for ann in analysis.anns if ann.novelty]
            if not items:
                lines.append("没有新增命令。")
            for ann, event in items:
                lines.append("- %s %s — %s" % (fmt_time(event.ts), inline_code(event.cmd), ann.intent))
            lines.append("")
        if "random" in sections:
            lines.append("## 随机：回看会话")
            lines.append("")
            sessions = [session for session in analysis.sessions if session.n > 1]
            if sessions:
                rng = random.Random(seed)
                for session in rng.sample(sessions, min(random_n, len(sessions))):
                    lines.append("### 会话 %s · %s" % (session.sid, fmt_span(session.start_ts, session.end_ts)))
                    lines.append("")
                    lines.append("%d 条命令 · %s" % (session.n, self._env_line(session.env)))
                    fails = [
                        analysis.ann(ev.seq)
                        for ev in session.events
                        if analysis.ann(ev.seq).status in (STATUS_FAIL, STATUS_SUSPECT)
                    ]
                    for ann in fails[:3]:
                        lines.append(
                            "- %s %s — %s"
                            % (
                                self._ref(analysis, ann.seq),
                                inline_code(analysis.event(ann.seq).cmd),
                                ann.error.signature if ann.error else "",
                            )
                        )
                        if ann.steps:
                            lines.append("  - 修复：%s" % inline_code(" && ".join(ann.steps)))
                    lines.append("")
        return "\n".join(lines).rstrip()

    def _markdown_errors(self, analysis):
        groups = defaultdict(list)
        for ann in analysis.anns:
            if ann.error is None or ann.status not in (STATUS_FAIL, STATUS_SUSPECT):
                continue
            groups[ann.error.signature].append(ann)
        lines = ["## 报错：错在哪，后来怎么好的", ""]
        if not groups:
            lines.append("没有捕获到报错。")
            lines.append("")
            return lines
        for signature, anns in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
            hint = hint_for(signature)
            lines.append("### %s — %s（%d 次）" % (signature, hint["title"], len(anns)))
            lines.append("")
            for ann in anns:
                event = analysis.event(ann.seq)
                lines.append("- %s %s %s" % (self._ref(analysis, ann.seq), fmt_time(event.ts), inline_code(event.cmd)))
                lines.append("  - 错误：%s" % ann.error.detail)
                if ann.steps:
                    lines.append(
                        "  - 修复：%s（%s）"
                        % (" → ".join(inline_code(step) for step in ann.steps), "已验证" if ann.verified else "未验证")
                    )
                if ann.correction:
                    lines.append("  - 更正：%s" % inline_code(ann.correction["command"]))
            lines.append("")
            lines.append(hint["next"])
            lines.append("")
        return lines


def build_history_rows(analysis, sid=None, grep=None, duplicates=False):
    """把事件整理成 history 风格的编号行；重复命令保留每一次出现。"""
    events = analysis.events
    if sid:
        events = [event for event in events if event.sid == sid]
    totals = Counter(event.cmd for event in events)
    seen = Counter()
    rows = []
    for event in events:
        seen[event.cmd] += 1
        rows.append(
            {
                "seq": event.seq,
                "uid": event.uid,
                "hist_id": event.hist_id,
                "id": str(event.hist_id) if event.hist_id is not None else "#%d" % event.seq,
                "ts": event.ts,
                "cmd": event.cmd,
                "occurrence": seen[event.cmd],
                "total": totals[event.cmd],
            }
        )
    if grep:
        needle = grep.lower()
        rows = [row for row in rows if needle in row["cmd"].lower()]
    if duplicates:
        rows = [row for row in rows if row["total"] > 1]
    return rows, totals


def p_join(items):
    return "（" + "；".join(items) + "）" if items else ""


def analysis_to_dict(analysis):
    sessions = []
    for session in analysis.sessions:
        sessions.append(
            {
                "sid": session.sid,
                "start_ts": session.start_ts,
                "end_ts": session.end_ts,
                "cwd": session.cwd,
                "env": session.env.to_dict() if getattr(session, "env", None) is not None else None,
                "events": [event.to_dict() for event in session.events],
            }
        )
    return {
        "stats": analysis.stats,
        "sources": analysis.sources,
        "warnings": analysis.warnings,
        "sessions": sessions,
        "annotations": [ann.to_dict() for ann in analysis.anns],
    }
