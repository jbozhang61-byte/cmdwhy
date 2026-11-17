"""根据最近命令、任务上下文和当前环境，推断下一步做什么。

原则：只提出有依据的动作；自动执行只允许低/中风险、非破坏性命令。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .env import detect_project, detect_venv, git_info
from .model import command_tokens
from .safety import is_dangerous
from .typo import ROOT_HINTS


@dataclass
class Action:
    command: str
    reason: str
    kind: str = "next"
    risk: str = "low"
    executable: bool = True
    confidence: str = "medium"

    def to_dict(self):
        return {
            "command": self.command,
            "reason": self.reason,
            "kind": self.kind,
            "risk": self.risk,
            "executable": self.executable,
            "confidence": self.confidence,
        }


@dataclass
class Plan:
    actions: list = field(default_factory=list)
    focus_seq: int = None
    task: str = None
    goal: str = None
    note: str = ""

    def to_dict(self):
        return {
            "focus_seq": self.focus_seq,
            "task": self.task,
            "goal": self.goal,
            "note": self.note,
            "actions": [action.to_dict() for action in self.actions],
        }


NON_EXECUTABLE_PREFIXES = ("cd ", "source ", ". ", "export ", "alias ", "unset ", "disown ", "exec ")


def _is_executable(command):
    stripped = command.strip()
    if not stripped:
        return False
    if stripped.startswith(NON_EXECUTABLE_PREFIXES):
        return False
    if "<" in stripped and ">" in stripped:
        return False
    return not is_dangerous(stripped)


def _has_file(cwd, *names):
    return any(os.path.exists(os.path.join(cwd, name)) for name in names)


def _git_dirty(cwd):
    info = git_info(cwd)
    return info is not None and info.get("dirty")


def _python_test_hint(cwd):
    if _has_file(cwd, "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"):
        return "pytest -q"
    if os.path.isdir(os.path.join(cwd, "tests")):
        return "pytest -q"
    return None


def build_plan(analysis, knowledge=None, cwd=None, limit=5, focus_seq=None):
    cwd = os.path.abspath(cwd or os.getcwd())
    actions = []

    def add(command, reason, kind="next", risk="low", confidence="medium"):
        command = (command or "").strip()
        if not command or any(action.command == command for action in actions):
            return
        actions.append(
            Action(
                command=command,
                reason=reason,
                kind=kind,
                risk=risk,
                executable=_is_executable(command),
                confidence=confidence,
            )
        )

    events = analysis.events
    if not events:
        add("ls -la", "先确认当前目录里有什么，再决定下一步")
        add("git status", "确认是否在 Git 仓库、有没有未提交改动", "inspect")
        add("cmdwhy doctor", "检查数据目录、历史来源和 hook 是否正常", "inspect")
        return Plan(actions=actions[:limit], note="还没有命令记录")

    if focus_seq is not None and 1 <= int(focus_seq) <= len(events):
        last = analysis.event(int(focus_seq))
    else:
        last = events[-1]
    ann = analysis.ann(last.seq)
    context = analysis.contexts.get(last.seq)
    error = ann.error
    task = context.label if context is not None else ann.task
    goal = context.goal if context is not None else ann.task_goal

    if error is not None and ann.status in ("fail", "suspected"):
        category = error.category
        signature = error.signature
        if ann.correction:
            add(
                ann.correction["command"],
                "修正 #%d 的输入错误：%s" % (last.seq, "；".join(ann.correction.get("reasons", [])[:2])),
                "fix",
                "low",
                ann.correction.get("confidence", "medium"),
            )
        if category == "PERM":
            head = last.head
            if head != "sudo" and head in ROOT_HINTS and not last.cmd.strip().startswith("sudo"):
                add("sudo " + last.cmd.strip(), "补 root 权限后重试（%s）" % signature, "fix", "medium")
            if signature == "PERM:exec":
                tokens = command_tokens(last.cmd)
                script = tokens[0] if tokens else last.cmd
                add("chmod +x " + script, "给脚本加执行位，再重跑", "fix", "low")
                add(last.cmd.strip(), "确认 chmod 后脚本能运行", "retry", "low")
        elif category == "CMD_NOT_FOUND":
            word = error.missing_word or last.head
            if word and not ann.correction:
                add("command-not-found " + word, "查询缺失命令对应的 Ubuntu 包名", "inspect", "low", "medium")
                add("apt search " + word, "在软件源里搜索同名包", "inspect", "low", "low")
        elif category == "MODULE":
            module = error.module
            if module:
                add("python3 -m pip install " + module, "安装缺失的 Python 模块 %s" % module, "fix", "medium")
        elif category == "PIP668":
            add("python3 -m venv .venv", "创建独立虚拟环境，绕过 PEP 668 对系统 Python 的保护", "setup", "medium")
            if _has_file(cwd, "requirements.txt"):
                add(
                    "./.venv/bin/python -m pip install -r requirements.txt",
                    "在虚拟环境里安装项目依赖",
                    "fix",
                    "medium",
                )
        elif category == "PORT":
            port = error.port or "<端口>"
            add("ss -ltnp | grep " + str(port), "确认端口被哪个进程占用", "inspect", "low")
            add("lsof -i :" + str(port), "用另一种方式确认占用进程", "inspect", "low")
        elif category == "GIT_REJECT":
            add("git pull --rebase", "先同步远端，消除非快进冲突", "fix", "medium")
            add(last.cmd.strip(), "同步后重跑推送", "retry", "low")
        elif category == "DOCKER":
            if "daemon" in (error.text or "").lower():
                add("sudo systemctl start docker", "启动 Docker 守护进程", "fix", "medium")
            add("sudo " + last.cmd.strip(), "用 root 权限访问 Docker 后重试", "fix", "medium")
        elif category == "AUTH":
            add("ssh -T git@github.com", "先验证 SSH 凭据是否可用", "inspect", "low", "low")
        elif category == "NET":
            add("curl -v " + (last.cmd.split()[-1] if last.cmd.split() else "localhost"), "加详细输出定位网络问题", "inspect", "low", "low")

        if knowledge is not None:
            for remedy in knowledge.lookup(signature, category, limit=2):
                for step in remedy.steps:
                    add(
                        step,
                        "你以前这样修好过（验证 %d 次）" % remedy.verified,
                        "kb",
                        "medium",
                        "high" if remedy.verified else "medium",
                    )
        if ann.steps and not ann.verified:
            add(last.cmd.strip(), "修复动作已执行，重跑确认是否生效", "retry", "low")
    else:
        # 上一条成功：根据修复链和环境给出下一步
        if ann.fix_of:
            source = analysis.ann(max(ann.fix_of))
            if source.error is not None and source.error.category == "PERM":
                add(source.cmd, "权限修复已完成，重跑原命令确认", "retry", "low")
            elif source.error is not None and source.error.category in ("GIT_REJECT",):
                add("git push", "远端已同步，继续推送", "retry", "low")
        project = detect_project(cwd)
        kind = project[1] if project else None
        if kind in ("python", "django"):
            venv = detect_venv(cwd)
            if not venv:
                add("python3 -m venv .venv", "项目还没有虚拟环境，先建一个", "setup", "medium", "medium")
            elif _has_file(cwd, "requirements.txt"):
                add(
                    "./.venv/bin/python -m pip install -r requirements.txt",
                    "把依赖装进项目的虚拟环境",
                    "setup",
                    "medium",
                    "low",
                )
            test_cmd = _python_test_hint(cwd)
            if test_cmd:
                add(test_cmd, "运行测试，确认项目当前状态", "inspect", "low", "low")
        elif kind in ("node", "typescript"):
            if not os.path.isdir(os.path.join(cwd, "node_modules")):
                add("npm install", "安装 Node 依赖", "setup", "medium", "low")
            package = os.path.join(cwd, "package.json")
            if os.path.exists(package):
                try:
                    with open(package, "r", encoding="utf-8", errors="replace") as fh:
                        data = json.load(fh)
                    if "test" in (data.get("scripts") or {}):
                        add("npm test", "运行 package.json 里的测试脚本", "inspect", "low", "low")
                except (OSError, ValueError):
                    pass
        if _git_dirty(cwd):
            add("git diff --stat", "查看未提交改动，决定是否提交", "inspect", "low", "low")
        if context is not None and context.label.startswith("Python") and not ann.fix_of:
            add("pytest -q", "当前任务在 Python 项目里，跑一遍测试确认状态", "inspect", "low", "low")

    actions = actions[: max(1, limit)]
    return Plan(actions=actions, focus_seq=last.seq, task=task, goal=goal)
