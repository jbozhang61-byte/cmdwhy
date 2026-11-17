"""cw run：执行命令、捕获退出码与错误输出，失败后立刻检索同类错误并给出改正建议。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from . import errors as err_mod
from .analyze import analyze
from .config import config_for
from .env import quick_env
from .knowledge import load_knowledge
from .model import Event
from .report import Renderer
from .safety import is_dangerous, safe_to_autofix
from .sources import append_event, load_events
from .typo import CorpusIndex, propose_fixes
from .util import Paint, color_enabled, fmt_duration


def _pump(stream, target, buffer=None):
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        try:
            target.write(chunk)
            target.flush()
        except (OSError, ValueError):
            pass
        if buffer is not None:
            buffer.append(chunk)


def run_command(cmd, cwd=None, timeout=None):
    """cmd 为字符串时走 shell（支持管道），为列表时不经过 shell（更安全）。"""
    start = time.time()
    proc = subprocess.Popen(
        cmd,
        shell=isinstance(cmd, str),
        cwd=cwd or os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    err_chunks = []
    out_thread = threading.Thread(target=_pump, args=(proc.stdout, sys.stdout.buffer), daemon=True)
    err_thread = threading.Thread(target=_pump, args=(proc.stderr, sys.stderr.buffer, err_chunks), daemon=True)
    out_thread.start()
    err_thread.start()
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        code = 124
        print("cmdwhy: 命令超时（%s 秒），已终止。" % timeout, file=sys.stderr)
    out_thread.join(timeout=2)
    err_thread.join(timeout=2)
    duration = time.time() - start
    stderr = b"".join(err_chunks).decode("utf-8", "replace")
    return code, stderr, duration, start


def _last_analysis(cfg, event):
    events, meta = load_events(cfg)
    if not events or events[-1].cmd != event.cmd or events[-1].ts != event.ts:
        events.append(event)
        for index, item in enumerate(events, 1):
            item.seq = index
        meta = {"files": [cfg.store_path], "warnings": []}
    analysis = analyze(events, cfg, meta)
    return analysis


def diagnose_event(cfg, analysis, event, renderer, show_fix=False):
    ann = analysis.ann(event.seq)
    knowledge = load_knowledge(cfg)
    error = ann.error
    if error is None:
        return 1
    signature = error.signature
    remedies = knowledge.lookup(signature, error.category)
    if not remedies and error.text:
        remedies = knowledge.lookup_text(error.text, error.category)
    index = CorpusIndex(analysis.events)
    fixes = propose_fixes(event.cmd, index=index, error=error) if show_fix else None
    print("")
    print(renderer.render_diagnosis(signature, error.category, knowledge.occurrences(signature), remedies, fixes=fixes))
    if fixes:
        best = fixes[0]
        print("")
        print(renderer.p("最可能改成：", "yellow") + renderer.p(best.command, "bold", "green"))
        if is_dangerous(best.command):
            print(renderer.p("这条建议被标记为危险操作，不会自动执行。", "red"))
        else:
            print(renderer.p("执行： cw run --fix --yes -- " + best.command, "grey"))
    return 0


def cmd_run(cfg, argv, fix=False, yes=False, retry=False, quiet=False, shell=False):
    if not argv:
        print("用法：cw run [--shell] [--fix] [--yes] [--retry] -- <命令>", file=sys.stderr)
        return 2
    import shlex

    argv = list(argv)
    if shell:
        display = " ".join(argv)
        target = display
    else:
        display = " ".join(shlex.quote(part) for part in argv)
        target = argv
    env = quick_env(os.getcwd())
    code, stderr, duration, started = run_command(target)
    event = Event(
        ts=started,
        cmd=display,
        exit_code=code,
        cwd=os.getcwd(),
        user=env.user,
        host=env.host,
        distro=env.distro,
        shell=env.shell,
        duration_ms=int(duration * 1000),
        stderr=stderr[-4000:] if stderr else None,
        source="hook",
    )
    append_event(cfg, event)
    analysis = _last_analysis(cfg, event)
    last = analysis.events[-1]
    ann = analysis.ann(last.seq)
    if code != 0:
        print("", file=sys.stderr)
        print(
            "cmdwhy: 退出码 %d（用时 %s）" % (code, fmt_duration(duration)),
            file=sys.stderr,
        )
        renderer = Renderer(Paint(color_enabled()), home=os.path.expanduser("~"))
        diagnose_event(cfg, analysis, last, renderer, show_fix=bool(fix or yes))
        if not yes and getattr(cfg, "autocorrect", False):
            index = CorpusIndex(analysis.events)
            fixes = propose_fixes(display, index=index, error=ann.error)
            if fixes:
                fix = fixes[0]
                if (
                    fix.confidence == "high"
                    and fix.kind in ("head", "subcommand", "chmod")
                    and not is_dangerous(fix.command)
                    and safe_to_autofix(fix.command)
                ):
                    print("cmdwhy: autocorrect 已开启，自动执行修正： " + fix.command, file=sys.stderr)
                    fix_code, fix_err, fix_duration, fix_started = run_command(fix.command)
                    fix_event = Event(
                        ts=fix_started,
                        cmd=fix.command,
                        exit_code=fix_code,
                        cwd=os.getcwd(),
                        user=env.user,
                        host=env.host,
                        distro=env.distro,
                        shell=env.shell,
                        duration_ms=int(fix_duration * 1000),
                        stderr=fix_err[-4000:] if fix_err else None,
                        source="hook",
                    )
                    append_event(cfg, fix_event)
                    if fix_code == 0:
                        print("cmdwhy: 已自动改正并执行成功。", file=sys.stderr)
                        if fix.kind == "chmod":
                            print("cmdwhy: 权限已修正，重跑原命令确认效果。", file=sys.stderr)
                            retry_code, retry_err, retry_duration, retry_started = run_command(target)
                            retry_event = Event(
                                ts=retry_started,
                                cmd=display,
                                exit_code=retry_code,
                                cwd=os.getcwd(),
                                user=env.user,
                                host=env.host,
                                distro=env.distro,
                                shell=env.shell,
                                duration_ms=int(retry_duration * 1000),
                                stderr=retry_err[-4000:] if retry_err else None,
                                source="hook",
                            )
                            append_event(cfg, retry_event)
                            return retry_code
                    return fix_code
        if not yes and getattr(cfg, "autocorrect", False):
            knowledge = load_knowledge(cfg)
            remedies = knowledge.lookup(ann.error.signature, ann.error.category)
            remedy = None
            for candidate in remedies:
                if candidate.verified <= 0:
                    continue
                if any("<" in step or ">" in step for step in candidate.steps):
                    continue
                if any("sudo" in step.split() for step in candidate.steps):
                    continue
                if all(safe_to_autofix(step) and not is_dangerous(step) for step in candidate.steps):
                    remedy = candidate
                    break
            if remedy is not None:
                print(
                    "cmdwhy: 找到同类错误的历史修法（验证 %d 次），自动执行 %d 步。"
                    % (remedy.verified, len(remedy.steps)),
                    file=sys.stderr,
                )
                for step in remedy.steps:
                    print("cmdwhy: 修复步骤： " + step, file=sys.stderr)
                    step_code, step_err, step_duration, step_started = run_command(step)
                    step_event = Event(
                        ts=step_started,
                        cmd=step,
                        exit_code=step_code,
                        cwd=os.getcwd(),
                        user=env.user,
                        host=env.host,
                        distro=env.distro,
                        shell=env.shell,
                        duration_ms=int(step_duration * 1000),
                        stderr=step_err[-4000:] if step_err else None,
                        source="autocorrect",
                    )
                    append_event(cfg, step_event)
                    if step_code != 0:
                        print("cmdwhy: 修复步骤失败（退出码 %d），停止。", step_code, file=sys.stderr)
                        return step_code
                return 0
        if yes:
            index = CorpusIndex(analysis.events)
            fixes = propose_fixes(display, index=index, error=ann.error)
            fix_cmd = fixes[0].command if fixes else ""
            if not fix_cmd or "<" in fix_cmd or is_dangerous(fix_cmd) or not safe_to_autofix(fix_cmd):
                print("cmdwhy: 没有可安全自动执行的修正命令，请手动确认。", file=sys.stderr)
                return code
            print("", file=sys.stderr)
            print("cmdwhy: 自动执行修正： " + fix_cmd, file=sys.stderr)
            fix_code, fix_err, fix_duration, fix_started = run_command(fix_cmd)
            fix_event = Event(
                ts=fix_started,
                cmd=fix_cmd,
                exit_code=fix_code,
                cwd=os.getcwd(),
                user=env.user,
                host=env.host,
                distro=env.distro,
                shell=env.shell,
                duration_ms=int(fix_duration * 1000),
                stderr=fix_err[-4000:] if fix_err else None,
                source="hook",
            )
            append_event(cfg, fix_event)
            if fix_code != 0:
                print("cmdwhy: 修正命令也失败了（退出码 %d），停止。", fix_code, file=sys.stderr)
                return fix_code
            if retry and fixes and fixes[0].kind in ("install", "install-module", "chmod", "git-sync"):
                print("cmdwhy: 重跑原命令： " + display, file=sys.stderr)
                retry_code, retry_err, retry_duration, retry_started = run_command(target)
                retry_event = Event(
                    ts=retry_started,
                    cmd=display,
                    exit_code=retry_code,
                    cwd=os.getcwd(),
                    user=env.user,
                    host=env.host,
                    distro=env.distro,
                    shell=env.shell,
                    duration_ms=int(retry_duration * 1000),
                    stderr=retry_err[-4000:] if retry_err else None,
                    source="hook",
                )
                append_event(cfg, retry_event)
                if retry_code == 0:
                    print("cmdwhy: 重跑成功，这次修复已记入知识库。", file=sys.stderr)
                return retry_code
            return fix_code
    elif not quiet:
        print("cmdwhy: 成功（%s），已记录 #%d。" % (fmt_duration(duration), last.seq), file=sys.stderr)
    return code
