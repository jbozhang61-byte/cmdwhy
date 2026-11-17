"""核心数据结构：命令事件、会话、环境快照、注解、分析结果。"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from functools import lru_cache

ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_PREFIXES = ("sudo", "command", "builtin", "exec", "nohup", "time", "env")
STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_SUSPECT = "suspected"
STATUS_UNKNOWN = "unknown"


@lru_cache(maxsize=8192)
def split_command(cmd: str):
    cmd = (cmd or "").strip()
    if not cmd:
        return ()
    try:
        return tuple(shlex.split(cmd, comments=False, posix=True))
    except ValueError:
        return tuple(cmd.split())


@lru_cache(maxsize=8192)
def command_tokens(cmd: str):
    """去掉前缀环境变量赋值和 sudo 包装后的有效 token。"""
    toks = list(split_command(cmd))
    changed = True
    while toks and changed:
        changed = False
        if ENV_ASSIGN_RE.match(toks[0]):
            toks.pop(0)
            changed = True
            continue
        if toks[0] in SHELL_PREFIXES:
            prefix = toks.pop(0)
            changed = True
            if prefix == "sudo":
                while toks and toks[0].startswith("-"):
                    flag = toks.pop(0)
                    if flag in ("-u", "-g", "-p", "-C") and toks:
                        toks.pop(0)
    return tuple(toks)


def command_head(cmd: str) -> str:
    toks = command_tokens(cmd)
    return toks[0] if toks else ""


def command_sub(cmd: str, heads=()) -> str:
    """取子命令，如 git 的 push、apt 的 install。heads 为空则取第二个 token。"""
    toks = command_tokens(cmd)
    if len(toks) < 2:
        return ""
    if toks[1].startswith("-"):
        return ""
    if heads and toks[0] not in heads:
        return ""
    return toks[1]


@lru_cache(maxsize=8192)
def core_signature(cmd: str):
    """用于判断"是不是同一条命令的重跑"：去掉 sudo、环境变量、短横线参数。"""
    out = []
    for tok in command_tokens(cmd):
        if tok.startswith("-") and len(tok) > 1:
            continue
        if tok in (">", ">>", "2>", "2>>", "|", "&&", "||", ";"):
            break
        out.append(tok.lower())
        if len(out) >= 6:
            break
    return tuple(out)


def similar_commands(a: str, b: str, threshold=0.6) -> bool:
    ca, cb = core_signature(a), core_signature(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    if ca[0] != cb[0]:
        return False
    sa, sb = set(ca), set(cb)
    union = len(sa | sb)
    return union > 0 and len(sa & sb) / float(union) >= threshold


def variant_commands(a: str, b: str) -> bool:
    """修正式重跑：同 head，去掉参数后的命令仅差一两个字符（sudo/拼写/参数微调）。"""
    ca, cb = core_signature(a), core_signature(b)
    if not ca or not cb or ca[0] != cb[0]:
        return False
    if ca == cb:
        return True
    ta = " ".join(ca[1:])
    tb = " ".join(cb[1:])
    if not ta or not tb:
        return False
    from .util import damerau

    return damerau(ta, tb) <= 2


def is_trivial(cmd: str) -> bool:
    toks = split_command(cmd)
    return not toks or (len(toks) == 1 and toks[0] in ("ls", "ll", "pwd", "cd", "clear", "history"))


@dataclass
class Event:
    seq: int = 0
    uid: str = ""
    ts: float = 0.0
    cmd: str = ""
    exit_code: int = None
    cwd: str = None
    user: str = None
    host: str = None
    shell: str = None
    duration_ms: int = None
    stderr: str = None
    hist_id: int = None
    distro: str = None
    project: str = None
    branch: str = None
    venv: str = None
    source: str = "history"
    sid: str = ""
    session_tag: str = None

    @property
    def failed(self) -> bool:
        return self.exit_code is not None and self.exit_code != 0

    @property
    def status(self) -> str:
        if self.exit_code is None:
            return STATUS_UNKNOWN
        return STATUS_OK if self.exit_code == 0 else STATUS_FAIL

    @property
    def head(self) -> str:
        return command_head(self.cmd)

    @property
    def tokens(self):
        return command_tokens(self.cmd)

    @property
    def core(self):
        return core_signature(self.cmd)

    @property
    def has_capture(self) -> bool:
        return bool(self.stderr) or self.exit_code is not None

    def to_dict(self) -> dict:
        data = {
            "seq": self.seq,
            "uid": self.uid,
            "ts": self.ts,
            "cmd": self.cmd,
            "exit_code": self.exit_code,
            "cwd": self.cwd,
            "user": self.user,
            "host": self.host,
            "shell": self.shell,
            "duration_ms": self.duration_ms,
            "stderr": self.stderr,
            "hist_id": self.hist_id,
            "distro": self.distro,
            "project": self.project,
            "branch": self.branch,
            "venv": self.venv,
            "source": self.source,
            "sid": self.sid,
        }
        if self.session_tag:
            data["session_tag"] = self.session_tag
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(
            seq=int(data.get("seq") or 0),
            uid=str(data.get("uid") or data.get("event_id") or ""),
            ts=float(data.get("ts") or 0),
            cmd=str(data.get("cmd") or data.get("command") or ""),
            exit_code=_to_int(data.get("exit_code", data.get("exit"))),
            cwd=data.get("cwd") or data.get("directory") or data.get("dir"),
            user=data.get("user"),
            host=data.get("host") or data.get("hostname"),
            shell=data.get("shell"),
            duration_ms=_to_int(data.get("duration_ms", data.get("duration"))),
            stderr=(str(data.get("stderr"))[:4000] if data.get("stderr") else None),
            hist_id=_to_int(data.get("hist_id", data.get("history_id", data.get("histno")))),
            distro=data.get("distro"),
            project=data.get("project"),
            branch=data.get("branch"),
            venv=data.get("venv"),
            source=str(data.get("source") or "hook"),
            sid=str(data.get("sid") or ""),
            session_tag=data.get("session_tag"),
        )


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Session:
    sid: str
    events: list
    start_ts: float = 0.0
    end_ts: float = 0.0
    cwd: str = None
    env: object = None

    @property
    def duration(self) -> float:
        if self.start_ts and self.end_ts:
            return max(0.0, self.end_ts - self.start_ts)
        return 0.0

    @property
    def n(self) -> int:
        return len(self.events)


@dataclass
class EnvInfo:
    cwd: str = None
    project: str = None
    project_root: str = None
    project_kind: str = None
    branch: str = None
    dirty: bool = False
    venv: str = None
    python: str = None
    distro: str = None
    user: str = None
    host: str = None
    is_root: bool = False
    container: bool = False
    ssh: bool = False
    shell: str = None

    def short(self, home=None, width=34) -> str:
        parts = [short_cwd(self.cwd, home, width)]
        if self.project:
            kind = "(%s)" % self.project_kind if self.project_kind else ""
            parts.append(self.project + kind)
        if self.branch:
            parts.append("git:" + self.branch + ("*" if self.dirty else ""))
        if self.venv:
            parts.append("venv:" + self.venv)
        return " · ".join(parts)

    def full(self, home=None) -> str:
        bits = []
        if self.cwd:
            bits.append(short_cwd(self.cwd, home, 60))
        if self.project:
            kind = "（%s 项目）" % self.project_kind if self.project_kind else ""
            bits.append(self.project + kind)
        if self.branch:
            bits.append("分支 %s%s" % (self.branch, "（有未提交改动）" if self.dirty else ""))
        if self.venv:
            bits.append("虚拟环境 %s%s" % (self.venv, " / Python " + self.python if self.python else ""))
        if self.distro:
            bits.append(self.distro)
        who = self.user or ""
        if self.host:
            who = (who + "@" if who else "") + self.host
        if who:
            bits.append(who)
        if self.is_root:
            bits.append("root 权限")
        if self.container:
            bits.append("容器内")
        if self.ssh:
            bits.append("SSH 会话")
        return " · ".join(bits)

    def to_dict(self) -> dict:
        return {
            "cwd": self.cwd,
            "project": self.project,
            "project_root": self.project_root,
            "project_kind": self.project_kind,
            "branch": self.branch,
            "dirty": self.dirty,
            "venv": self.venv,
            "python": self.python,
            "distro": self.distro,
            "user": self.user,
            "host": self.host,
            "is_root": self.is_root,
            "container": self.container,
            "ssh": self.ssh,
            "shell": self.shell,
        }


def short_cwd(cwd, home=None, width=34):
    from .util import short_path

    return short_path(cwd, home=home, width=width)


CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低"}


@dataclass
class Annotation:
    seq: int
    status: str = STATUS_UNKNOWN
    status_conf: str = "low"
    intent: str = ""
    motivation: str = ""
    evidence: list = field(default_factory=list)
    error: object = None
    fix_of: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    verified: bool = False
    verified_at: int = None
    correction: dict = None
    novelty: str = None
    task: str = None
    task_goal: str = None
    phase: str = None
    purpose: str = None
    context_summary: str = None
    changes: list = field(default_factory=list)
    danger: str = None
    note: str = None
    role: str = "other"
    confidence: str = "low"

    def add(self, text):
        if text and text not in self.evidence:
            self.evidence.append(text)

    def to_dict(self) -> dict:
        data = {
            "seq": self.seq,
            "status": self.status,
            "status_confidence": self.status_conf,
            "role": self.role,
            "intent": self.intent,
            "motivation": self.motivation,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "fix_of": list(self.fix_of),
            "steps": list(self.steps),
            "verified": self.verified,
            "verified_at": self.verified_at,
            "novelty": self.novelty,
            "task": self.task,
            "task_goal": self.task_goal,
            "phase": self.phase,
            "purpose": self.purpose,
            "context_summary": self.context_summary,
            "changes": list(self.changes),
            "danger": self.danger,
            "note": self.note,
        }
        if self.error is not None:
            data["error"] = self.error.to_dict()
        if self.correction:
            data["correction"] = self.correction
        return data


@dataclass
class Analysis:
    events: list
    anns: list
    sessions: list
    stats: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    envs: dict = field(default_factory=dict)
    contexts: dict = field(default_factory=dict)

    def ann(self, seq) -> Annotation:
        idx = seq - 1
        if 0 <= idx < len(self.anns):
            return self.anns[idx]
        return Annotation(seq=seq)

    def event(self, seq) -> Event:
        return self.events[seq - 1]

    @property
    def session_of(self):
        table = {}
        for sess in self.sessions:
            for ev in sess.events:
                table[ev.seq] = sess
        return table
