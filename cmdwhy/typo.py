"""输入错误纠正：先看"真的存在什么"，再看"你以前成功用过什么"。

原则：
1. 候选必须真实存在（PATH 可执行文件、shell 内建、合法子命令）或你历史上成功用过；
2. 距离最多 2，且必须同首字母（除距离 1 的极端情况）；
3. 危险命令（rm/dd/mkfs...）默认降权，避免"帮你改"成灾难。
"""

from __future__ import annotations

import math
import os
import re
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from .model import command_tokens, core_signature, split_command
from .util import damerau, keyboard_near

BUILTINS = {
    "alias", "bg", "bind", "break", "builtin", "cd", "command", "continue", "declare",
    "dirs", "disown", "echo", "enable", "eval", "exec", "exit", "export", "fc", "fg",
    "getopts", "hash", "help", "history", "jobs", "kill", "let", "local", "logout",
    "mapfile", "popd", "printf", "pushd", "pwd", "read", "readonly", "return", "set",
    "shift", "shopt", "source", "suspend", "test", "times", "trap", "type", "typeset",
    "ulimit", "umask", "unalias", "unset", "wait", "which",
}

SUBCOMMANDS = {
    "git": "add am apply bisect blame branch checkout cherry-pick clean clone commit config "
           "describe diff fetch format-patch grep init log merge mv notes pull push rebase "
           "reflog remote reset restore revert rm shortlog show stash status submodule switch tag worktree".split(),
    "apt": "install remove purge update upgrade full-upgrade search show list policy autoremove "
           "autoclean clean edit-sources depends rdepends".split(),
    "apt-get": "install remove purge update upgrade dist-upgrade search show autoremove autoclean clean".split(),
    "systemctl": "start stop restart reload status enable disable is-active is-enabled "
                 "is-failed daemon-reload list-units list-unit-files cat show edit mask unmask".split(),
    "journalctl": "boot list-boots since until unit user follow disk-usage vacuum-size vacuum-time".split(),
    "pip": "install uninstall list show freeze download wheel check config cache".split(),
    "pip3": "install uninstall list show freeze download wheel check config cache".split(),
    "docker": "build compose exec images logs ps pull push rm rmi run start stop restart tag "
              "inspect network volume system".split(),
    "docker-compose": "up down ps logs build restart stop start exec run config".split(),
    "npm": "install uninstall run start test build init ci publish update audit list link".split(),
    "yarn": "add remove install run start test build init publish upgrade".split(),
    "pnpm": "add remove install run start test build init publish update".split(),
    "cargo": "build run test check clean doc update add remove publish bench fmt clippy".split(),
    "go": "build run test get mod vet fmt clean install doc env".split(),
    "kubectl": "get describe apply delete logs exec port-forward rollout scale create config "
               "top explain edit patch".split(),
    "npm": "install uninstall run start test build init ci publish update audit list link".split(),
    "ufw": "allow deny enable disable status reload reset delete".split(),
    "snap": "install remove list refresh revert enable disable".split(),
    "conda": "install create activate deactivate list update remove env".split(),
    "brew": "install uninstall update upgrade list search info services".split(),
}

ROOT_HINTS = {
    "apt", "apt-get", "dpkg", "systemctl", "mount", "umount", "ufw", "iptables", "ip6tables",
    "useradd", "usermod", "userdel", "groupadd", "passwd", "visudo", "crontab", "nginx",
    "apachectl", "adduser", "addgroup", "swapon", "swapoff", "fdisk", "parted", "modprobe",
    "hostnamectl", "timedatectl", "reboot", "shutdown", "poweroff", "docker",
}

DESTRUCTIVE = {
    "rm", "dd", "mkfs", "shutdown", "reboot", "poweroff", "kill", "killall", "pkill",
    "chmod", "chown", "mv", "truncate", "wipefs", "fdisk", "parted", "shred",
}


@lru_cache(maxsize=1)
def path_binaries():
    """扫描 PATH 里的可执行文件名（去掉扩展名）。"""
    names = Counter()
    seen_dirs = set()
    exts = ("",)
    if os.name == "nt":
        exts += tuple(ext.lower() for ext in os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";") if ext)
    for entry in (os.environ.get("PATH") or "").split(os.pathsep):
        if not entry:
            continue
        try:
            real = os.path.abspath(entry)
        except (OSError, ValueError):
            continue
        if real in seen_dirs or not os.path.isdir(real):
            continue
        seen_dirs.add(real)
        try:
            listing = os.listdir(real)
        except OSError:
            continue
        for name in listing:
            lowered = name.lower()
            if os.name == "nt":
                for ext in exts:
                    if ext and lowered.endswith(ext):
                        names[name[: -len(ext)].lower()] += 1
                        break
                else:
                    if not os.path.splitext(name)[1]:
                        names[lowered] += 1
            else:
                names[name] += 1
    return names


@lru_cache(maxsize=1)
def known_commands():
    return set(path_binaries()) | set(BUILTINS) | set(SUBCOMMANDS)


class CorpusIndex:
    """从历史里统计：哪些命令/子命令你常用且成功过。"""

    def __init__(self, events):
        self.head_counts = Counter()
        self.sub_counts = defaultdict(Counter)
        self.sub_success = defaultdict(Counter)
        self.core_counts = Counter()
        self.core_success = Counter()
        self.full_counts = Counter()
        self.project_counts = Counter()
        self.events = list(events or [])
        for event in self.events:
            tokens = command_tokens(event.cmd)
            if not tokens:
                continue
            head = tokens[0]
            self.head_counts[head] += 1
            if len(tokens) > 1 and not tokens[1].startswith("-"):
                self.sub_counts[head][tokens[1]] += 1
                if event.exit_code == 0:
                    self.sub_success[head][tokens[1]] += 1
            core = core_signature(event.cmd)
            key = " ".join(core)
            self.core_counts[key] += 1
            self.full_counts[event.cmd] += 1
            if event.exit_code == 0:
                self.core_success[key] += 1
            if event.cwd:
                self.project_counts[event.cwd] += 1

    def success_of(self, command):
        core = " ".join(core_signature(command))
        return self.core_success.get(core, 0), self.core_counts.get(core, 0)

    def uses_of(self, head):
        return self.head_counts.get(head, 0)


@dataclass
class Fix:
    command: str
    kind: str = "typo"
    score: float = 0.0
    confidence: str = "low"
    reasons: list = field(default_factory=list)
    distance: int = 0
    uses: int = 0
    successes: int = 0

    def to_dict(self):
        return {
            "command": self.command,
            "kind": self.kind,
            "confidence": self.confidence,
            "score": round(self.score, 3),
            "distance": self.distance,
            "uses": self.uses,
            "successes": self.successes,
            "reasons": list(self.reasons),
        }


@dataclass
class Suggestion:
    word: str
    score: float
    distance: int
    reasons: list = field(default_factory=list)
    uses: int = 0
    successes: int = 0


def typo_kind(a: str, b: str) -> str:
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 2:
            i, j = diffs
            if a[i] == b[j] and a[j] == b[i]:
                return "字母顺序颠倒"
        return "相邻键误触" if keyboard_near(a, b) else "替换了一个字母"
    if len(a) + 1 == len(b):
        return "少打了一个字母"
    if len(a) - 1 == len(b):
        return "多打了一个字母"
    return "几处拼写差异"


def _score_pair(word, candidate, uses=0, successes=0, prefer_sub=False, is_path=False):
    distance = damerau(word, candidate)
    if distance == 0 or distance > 2:
        return None
    if len(candidate) < 2:
        return None
    score = 1.0 / (1.0 + distance)
    if word[:1].lower() != candidate[:1].lower() and distance > 1:
        return None
    if word[:1].lower() == candidate[:1].lower():
        score *= 1.15
    if keyboard_near(word, candidate):
        score *= 1.3
    if is_path:
        score *= 1.15
    if uses:
        score *= 1.0 + min(1.2, math.log1p(uses) / 3.0)
    if successes:
        score *= 1.0 + min(0.4, math.log1p(successes) / 5.0)
    if prefer_sub:
        score *= 1.7
    if candidate in DESTRUCTIVE:
        score *= 0.35
    if word[:1].lower() != candidate[:1].lower() and distance > 1:
        score *= 0.5
    return score, distance


def suggest_heads(word, index: CorpusIndex = None, next_token=None, limit=3):
    word = (word or "").strip()
    if not word:
        return []
    candidates = set()
    path_names = path_binaries()
    candidates.update(path_names.keys())
    candidates.update(BUILTINS)
    if index is not None:
        candidates.update(index.head_counts.keys())
    results = []
    for candidate in candidates:
        if candidate == word:
            continue
        uses = 0
        successes = 0
        if index is not None:
            uses = index.head_counts.get(candidate, 0)
        prefer = bool(next_token and next_token in SUBCOMMANDS.get(candidate, ()))
        scored = _score_pair(word, candidate, uses=uses, prefer_sub=prefer, is_path=candidate in path_names)
        if not scored:
            continue
        score, distance = scored
        reasons = [typo_kind(word, candidate)]
        if candidate in path_names:
            reasons.append("系统里存在这个命令")
        if uses:
            reasons.append("你用过 %d 次" % uses)
        if prefer:
            reasons.append("后面的 %s 是它的合法子命令" % next_token)
        results.append(Suggestion(candidate, score, distance, reasons, uses))
    results.sort(key=lambda item: (-item.score, item.distance, item.word))
    return results[:limit]


def suggest_subs(head, word, index: CorpusIndex = None, limit=3):
    word = (word or "").strip()
    valid = SUBCOMMANDS.get(head)
    if not valid or not word:
        return []
    # 只把"成功用过"的历史子命令当成合法候选；失败过的可能是同一个拼写错误
    if index is not None:
        corpus_subs = set(index.sub_success.get(head, {}).keys())
    else:
        corpus_subs = set()
    if word in valid:
        return []
    results = []
    for candidate in list(valid) + sorted(corpus_subs - set(valid)):
        if candidate == word:
            continue
        uses = index.sub_counts.get(head, {}).get(candidate, 0) if index is not None else 0
        scored = _score_pair(word, candidate, uses=uses)
        if not scored:
            continue
        score, distance = scored
        reasons = ["%s 的合法子命令" % head, typo_kind(word, candidate)]
        if uses:
            reasons.append("你用过 %d 次" % uses)
        results.append(Suggestion(candidate, score, distance, reasons, uses))
    results.sort(key=lambda item: (-item.score, item.distance, item.word))
    return results[:limit]


def _rebuild(tokens, pos, new_value):
    new_tokens = list(tokens)
    new_tokens[pos] = new_value
    return " ".join(shlex.quote(tok) for tok in new_tokens)


def is_known_command(head) -> bool:
    return head in known_commands()


def propose_fixes(cmd, index: CorpusIndex = None, error=None, limit=3):
    """给出最多 limit 条"应该改成什么"的建议（按可信度排序）。"""
    raw = (cmd or "").strip()
    if not raw:
        return []
    try:
        tokens = list(split_command(raw))
    except ValueError:
        tokens = raw.split()
    if not tokens:
        return []
    head = tokens[0]
    sub = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
    fixes = []
    signature = getattr(error, "signature", "") or ""
    category = getattr(error, "category", "") or ""
    missing = getattr(error, "missing_word", None)

    # 1) 子命令拼错：git stauts / apt instal
    if head in SUBCOMMANDS and sub:
        for item in suggest_subs(head, sub, index, limit=limit):
            fixes.append(
                Fix(
                    command=_rebuild(tokens, 1, item.word),
                    kind="subcommand",
                    score=item.score,
                    confidence=(
                        "high"
                        if item.distance <= 1 and item.word in SUBCOMMANDS.get(head, ())
                        else _confidence(item.score)
                    ),
                    reasons=["%s %s" % (head, item.word)] + item.reasons,
                    distance=item.distance,
                    uses=item.uses,
                )
            )

    # 2) 命令名拼错：gti status / pytnon app.py
    target = missing or head
    if target == head and not is_known_command(head):
        for item in suggest_heads(head, index, next_token=sub, limit=limit):
            fixes.append(
                Fix(
                    command=_rebuild(tokens, 0, item.word),
                    kind="head",
                    score=item.score,
                    confidence=_confidence(item.score),
                    reasons=item.reasons,
                    distance=item.distance,
                    uses=item.uses,
                )
            )
    # 3) 权限不足但没加 sudo
    if category == "PERM" and head != "sudo" and head in ROOT_HINTS:
        fixes.append(
            Fix(
                command="sudo " + raw,
                kind="sudo",
                score=0.92,
                confidence="high",
                reasons=[
                    "%s 是系统级操作，需要 root 权限（%s）" % (head, signature or "PERM"),
                ],
            )
        )

    # 3.1) 脚本没有执行权限
    if signature == "PERM:exec":
        script = tokens[0]
        fixes.append(
            Fix(
                command="chmod +x " + script,
                kind="chmod",
                score=0.9,
                confidence="high",
                reasons=["%s 缺少执行位" % script, "chmod +x 后就能重跑"],
            )
        )

    # 3.2) Docker 守护进程权限
    if category == "DOCKER" and head != "sudo":
        fixes.append(
            Fix(
                command="sudo " + raw,
                kind="sudo",
                score=0.9,
                confidence="high",
                reasons=["当前用户无权访问 docker.sock", "临时用 sudo，长期应加入 docker 组"],
            )
        )

    # 3.3) 远端拒绝推送
    if category == "GIT_REJECT":
        fixes.append(
            Fix(
                command="git pull --rebase",
                kind="git-sync",
                score=0.88,
                confidence="high",
                reasons=["远端有你本地没有的提交", "先 rebase 再重跑原命令，避免覆盖远端历史"],
            )
        )

    # 3.4) 系统 Python 受 PEP 668 保护
    if category == "PIP668":
        fixes.append(
            Fix(
                command="python3 -m venv .venv",
                kind="venv",
                score=0.85,
                confidence="high",
                reasons=["系统 Python 禁止直接 pip install", "创建独立虚拟环境后再安装"],
            )
        )

    # 3.5) 缺少 Python 模块
    if category == "MODULE" and getattr(error, "module", None):
        module = error.module
        fixes.append(
            Fix(
                command="python3 -m pip install " + module,
                kind="install-module",
                score=0.8,
                confidence="medium",
                reasons=["当前 Python 环境缺少 %s" % module, "注意要和 which python 指向同一个环境"],
            )
        )

    # 4) 找不到相近命令：提示"可能没安装"，而不是乱猜
    if not fixes and (category == "CMD_NOT_FOUND" or not is_known_command(head)):
        fixes.append(
            Fix(
                command="sudo apt install <包名>",
                kind="install",
                score=0.3,
                confidence="low",
                reasons=[
                    "没有找到足够相近的命令，%s 可能根本没装" % (missing or head),
                    "用 command-not-found %s 可以查到对应的 Ubuntu 包名" % (missing or head),
                ],
            )
        )

    fixes.sort(key=lambda fix: (-fix.score, fix.distance, fix.command))
    seen = set()
    unique = []
    for fix in fixes:
        if fix.command in seen:
            continue
        seen.add(fix.command)
        unique.append(fix)
    return unique[:limit]


def _confidence(score):
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def correction_for_event(event, index, error=None):
    """分析阶段用：给一条失败命令找改正方案，返回 dict 或 None。"""
    fixes = propose_fixes(event.cmd, index=index, error=error, limit=1)
    if not fixes:
        return None
    fix = fixes[0]
    if fix.kind == "install":
        return None
    return {
        "command": fix.command,
        "kind": fix.kind,
        "confidence": fix.confidence,
        "reasons": list(fix.reasons),
        "distance": fix.distance,
        "score": round(fix.score, 3),
    }
