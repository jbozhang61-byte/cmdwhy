"""分析引擎：把一串命令还原成 环境 + 动机 + 报错 + 修复链 + 输入更正。"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import causal
from . import errors as err_mod
from . import labels
from . import repairs
from .config import Config
from .context import attach_contexts
from .env import EnvCache
from .intent import classify_intent, command_key, command_role, fix_intent
from .model import (
    Analysis,
    Annotation,
    Event,
    Session,
    command_head,
    command_tokens,
    core_signature,
    is_trivial,
    similar_commands,
    split_command,
)
from .safety import danger_of
from .typo import SUBCOMMANDS, CorpusIndex, correction_for_event, propose_fixes
from .util import damerau, short_path

FIX_KEYWORDS = {
    "PERM": ("chmod", "chown", "sudo", "usermod", "newgrp"),
    "PERM:exec": ("chmod", "bash ", "sh "),
    "PERM:dpkg-lock": ("sudo", "apt", "dpkg"),
    "PERM:docker": ("usermod", "newgrp", "sudo"),
    "CMD_NOT_FOUND": (
        "apt install", "apt-get install", "snap install", "pip install", "pip3 install",
        "pipx install", "npm install -g", "cargo install", "go install",
    ),
    "MODULE": ("pip install", "pip3 install", "uv add", "poetry add", "apt install", "pipx"),
    "NOT_FOUND": ("mkdir", "touch", "git clone", "cd "),
    "PORT": ("kill", "fuser", "pkill", "killall"),
    "PIP668": ("venv", "pipx", "apt install python3-venv", "virtualenv"),
    "GIT_REJECT": ("git pull", "git fetch"),
    "GIT_CONFLICT": ("git add", "git rebase", "git merge", "git status"),
    "DISK": ("rm ", "journalctl --vacuum", "apt clean", "docker system prune", "truncate"),
    "LOCK": ("kill", "dpkg --configure", "systemctl", "wait"),
    "AUTH": ("ssh-add", "ssh-keygen", "git config", "gh auth"),
    "DOCKER": ("systemctl start docker", "usermod", "sudo"),
    "NET": ("curl", "ping", "ss ", "resolvectl", "systemctl"),
    "BUILD": ("apt install", "make clean", "pip install"),
    "USAGE": ("--help",),
}


@dataclass
class Chain:
    fail_seq: int
    retry_seq: int = None
    kind: str = ""
    steps: list = field(default_factory=list)
    verified: bool = False
    verify_seq: int = None
    probability: float = 0.0

    def to_dict(self):
        return {
            "fail_seq": self.fail_seq,
            "retry_seq": self.retry_seq,
            "kind": self.kind,
            "steps": [{"seq": seq, "cmd": cmd} for seq, cmd in self.steps],
            "verified": self.verified,
            "verify_seq": self.verify_seq,
            "probability": self.probability,
        }


# ---------------------------------------------------------------- 会话

def build_sessions(events, idle_gap, envs):
    sessions = []
    current = []
    for event in events:
        if current:
            last = current[-1]
            if event.ts and last.ts and event.ts - last.ts > idle_gap:
                sessions.append(_make_session("S%d" % (len(sessions) + 1), current, envs))
                current = []
        current.append(event)
    if current:
        sessions.append(_make_session("S%d" % (len(sessions) + 1), current, envs))
    for session in sessions:
        for event in session.events:
            event.sid = session.sid
    return sessions


def _make_session(sid, events, envs):
    starts = [ev.ts for ev in events if ev.ts]
    cwd = None
    for event in events:
        if event.cwd:
            cwd = event.cwd
            break
    env = envs.get(events[0].seq) if events else None
    return Session(
        sid=sid,
        events=list(events),
        start_ts=min(starts) if starts else 0.0,
        end_ts=max(starts) if starts else 0.0,
        cwd=cwd,
        env=env,
    )


# ---------------------------------------------------------------- 失败推断

def _retry_kind(a: Event, b: Event):
    """判断 b 是不是 a 的重跑：retry（原样/近似）或 correction（修正式）。"""
    if similar_commands(a.cmd, b.cmd):
        return "retry"
    ca, cb = core_signature(a.cmd), core_signature(b.cmd)
    if not ca or not cb:
        return None
    if ca[:2] == cb[:2] and (len(ca) <= 2 or len(cb) <= 2):
        return "retry"
    if ca[0] != cb[0]:
        if damerau(ca[0], cb[0]) == 1 and ca[1:] == cb[1:]:
            return "correction"
        return None
    if len(ca) > 1 and len(cb) > 1:
        ta, tb = " ".join(ca[1:]), " ".join(cb[1:])
        if ta != tb and damerau(ta, tb) <= 1:
            head = ca[0]
            if head in SUBCOMMANDS:
                valid = SUBCOMMANDS[head]
                if ca[1] in valid and cb[1] not in valid:
                    return None
                if ca[1] not in valid and cb[1] in valid:
                    return "correction"
            return "correction"
    return None


def _correction_word(a: Event, b: Event):
    ca, cb = core_signature(a.cmd), core_signature(b.cmd)
    if ca and cb and ca[0] != cb[0]:
        return ca[0]
    ta = split_command(a.cmd)
    tb = split_command(b.cmd)
    for index, token in enumerate(ta):
        if index < len(tb) and token != tb[index]:
            return token
    return ca[0] if ca else None


def _installs_missing(cmd: str, missing: str) -> bool:
    tokens = command_tokens(cmd)
    if len(tokens) < 3:
        return False
    head, sub = tokens[0], tokens[1]
    if head in ("apt", "apt-get", "snap") and sub == "install":
        return any(token == missing or damerau(token, missing) <= 1 for token in tokens[2:])
    if head in ("pip", "pip3", "pipx") and sub == "install":
        return True
    if head == "npm" and sub in ("install", "i"):
        return True
    return False


SERVER_HEADS = {
    "npm", "yarn", "pnpm", "node", "python", "python3", "uvicorn", "gunicorn",
    "flask", "rails", "docker", "docker-compose", "podman", "go",
}


def _infer_from_following(event, other):
    """从"下一条命令像是修复"反推失败类别（只用于没有退出码的历史）。"""
    tokens = command_tokens(other.cmd)
    if not tokens:
        return None
    head = tokens[0]
    sub = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
    current = command_tokens(event.cmd)
    current_head = current[0] if current else ""
    if head == "git" and sub in ("pull", "fetch") and "push" in event.cmd:
        return ("GIT_REJECT", "紧接着 git pull/fetch，通常是远端拒绝了 push（非快进）", "GIT_REJECT:fetch-first", "medium")
    if (
        head in ("python", "python3")
        and "-m" in tokens
        and "venv" in tokens
        and current_head in ("pip", "pip3")
    ):
        return ("PIP668", "紧接着创建虚拟环境，通常是系统 Python 受 PEP 668 保护", "PIP668", "medium")
    if head in ("kill", "pkill", "killall", "fuser") and current_head in SERVER_HEADS:
        return ("PORT", "紧接着结束进程，通常是端口或进程被占用", "PORT", "low")
    return None


def infer_failures(events, errors):
    """没有退出码的历史：用"随后立刻出现的修复动作"反推上一条大概率失败了。"""
    for index, event in enumerate(events):
        if event.exit_code is not None:
            continue
        for other in events[index + 1: index + 4]:
            if other.sid and event.sid and other.sid != event.sid:
                break
            text = other.cmd.strip()
            if text.startswith("sudo ") and similar_commands(event.cmd, text):
                errors[event.seq] = err_mod.infer_error(
                    "PERM",
                    "紧接着用 sudo 重跑了同一条命令，通常意味着上一条因权限不足失败",
                    signature="PERM",
                    confidence="low",
                )
                break
            if command_head(text) == "chmod" and text and event.cmd.strip().startswith("./"):
                errors[event.seq] = err_mod.infer_error(
                    "PERM",
                    "随后给脚本 chmod +x，通常意味着上一条没有执行权限",
                    signature="PERM:exec",
                    confidence="low",
                )
                break
            kind = _retry_kind(event, other)
            if kind == "correction":
                word = _correction_word(event, other) or event.head
                errors[event.seq] = err_mod.infer_error(
                    "CMD_NOT_FOUND",
                    "随后把 %s 改成了 %s，疑似输入错误" % (word, other.cmd.strip()),
                    signature="CMD_NOT_FOUND",
                    confidence="low",
                    missing_word=word,
                )
                break
            if _installs_missing(text, event.head):
                errors[event.seq] = err_mod.infer_error(
                    "CMD_NOT_FOUND",
                    "随后安装了 %s，通常意味着上一条命令不存在" % event.head,
                    signature="CMD_NOT_FOUND:" + event.head,
                    confidence="low",
                    missing_word=event.head,
                )
                break
            inferred = _infer_from_following(event, other)
            if inferred:
                category, detail, signature, confidence = inferred
                errors[event.seq] = err_mod.infer_error(
                    category, detail, signature=signature, confidence=confidence
                )
                break


# ---------------------------------------------------------------- 修复链

def _fits_failure(failure, cmd) -> bool:
    if failure is None:
        return False
    signature = getattr(failure, "signature", "") or ""
    category = getattr(failure, "category", "") or ""
    low = (cmd or "").lower()
    for key in (signature, category):
        for keyword in FIX_KEYWORDS.get(key, ()):
            if keyword in low:
                return True
    return False


def _is_retry_of_earlier(events, errors, position):
    """这条命令是不是在重跑更早的失败？如果是，它不该被算作别人的修复步骤。"""
    candidate = events[position]
    for back in range(max(0, position - 8), position):
        earlier = events[back]
        if earlier.exit_code == 0:
            continue
        if errors.get(earlier.seq) is None:
            continue
        if _retry_kind(earlier, candidate):
            return True
    return False


def find_chain(events, index, errors, window):
    event = events[index]
    failure = errors.get(event.seq)
    if failure is None or event.exit_code == 0:
        return None
    limit = min(len(events), index + window + 1)
    retry_index = None
    kind = ""
    for pos in range(index + 1, limit):
        other = events[pos]
        if other.sid != event.sid:
            break
        found = _retry_kind(event, other)
        if found:
            retry_index = pos
            kind = found
            break
    steps = []
    if retry_index is not None:
        for pos in range(index + 1, retry_index):
            candidate = events[pos]
            if candidate.failed:
                continue
            if _is_retry_of_earlier(events, errors, pos):
                continue
            if command_role(candidate.cmd) == "mutate":
                steps.append((candidate.seq, candidate.cmd))
        retry = events[retry_index]
        if not steps:
            same_core = core_signature(retry.cmd) == core_signature(event.cmd)
            if kind == "correction" or (same_core and retry.cmd.strip() != event.cmd.strip()):
                steps.append((retry.seq, retry.cmd))
        verified = retry.exit_code == 0
        return Chain(
            fail_seq=event.seq,
            retry_seq=retry.seq,
            kind=kind,
            steps=steps,
            verified=verified,
            verify_seq=retry.seq,
        )
    for pos in range(index + 1, limit):
        candidate = events[pos]
        if candidate.sid != event.sid:
            break
        if command_role(candidate.cmd) == "mutate" and _fits_failure(failure, candidate.cmd):
            return Chain(
                fail_seq=event.seq,
                retry_seq=None,
                kind="attempt",
                steps=[(candidate.seq, candidate.cmd)],
                verified=False,
                verify_seq=None,
            )
    return None


# ---------------------------------------------------------------- 变化描述

def _package_args(tokens):
    return [token for token in tokens[2:] if not token.startswith("-")]


def describe_changes(event, previous, envs):
    changes = []
    tokens = command_tokens(event.cmd)
    if not tokens:
        return changes
    head = tokens[0]
    sub = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
    if head == "cd":
        old = previous.cwd if previous else None
        new = event.cwd
        if old and new and old != new:
            changes.append("切换目录 %s → %s" % (short_path(old), short_path(new)))
        elif new:
            changes.append("切换目录到 %s" % short_path(new))
    elif head in ("apt", "apt-get", "dpkg", "snap") and sub in ("install", "remove", "purge"):
        packages = _package_args(tokens)
        if packages:
            changes.append("%s软件包 %s" % ("安装" if sub == "install" else "卸载", " ".join(packages[:4])))
    elif head in ("apt", "apt-get") and sub in ("upgrade", "full-upgrade"):
        changes.append("升级系统软件包")
    elif head in ("pip", "pip3", "pipx", "uv", "poetry") and sub in ("install", "add"):
        packages = [token for token in tokens[2:] if not token.startswith("-") and token not in ("-r",)]
        changes.append("安装 Python 依赖" + (" " + " ".join(packages[:3]) if packages else ""))
    elif head in ("npm", "yarn", "pnpm") and sub in ("install", "add", "ci"):
        changes.append("安装 Node 依赖")
    elif head in ("export", "unset", "alias", "source", "."):
        changes.append("修改 shell 环境（%s）" % " ".join(tokens[:2]))
    elif head.startswith("python") and "-m" in tokens and "venv" in tokens:
        target = tokens[tokens.index("venv") + 1] if tokens.index("venv") + 1 < len(tokens) else ".venv"
        changes.append("创建虚拟环境 %s" % target)
    elif head == "mkdir":
        changes.append("创建目录 " + " ".join([t for t in tokens[1:] if not t.startswith("-")][:2]))
    elif head in ("rm", "rmdir"):
        changes.append("删除 " + " ".join([t for t in tokens[1:] if not t.startswith("-")][:2]))
    elif head == "chmod":
        changes.append("修改权限 " + " ".join(tokens[1:3]))
    elif head == "chown":
        changes.append("修改属主 " + " ".join(tokens[1:4]))
    elif head == "git" and sub in ("checkout", "switch"):
        target = tokens[-1] if len(tokens) > 2 else ""
        changes.append("切换分支/版本 → %s" % target)
    elif head == "git" and sub in ("commit", "merge", "rebase", "pull", "push", "reset"):
        changes.append({"commit": "提交改动", "merge": "合并分支", "rebase": "变基", "pull": "同步远端", "push": "推送远端", "reset": "回退提交"}[sub])
    elif head in ("systemctl", "service") and sub in ("start", "stop", "restart", "reload", "enable", "disable"):
        target = tokens[-1] if len(tokens) > 2 else ""
        changes.append("%s服务 %s" % ({"start": "启动", "stop": "停止", "restart": "重启", "reload": "重载", "enable": "启用", "disable": "禁用"}[sub], target))
    elif head == "kill":
        changes.append("结束进程 " + " ".join(tokens[1:3]))
    elif head in ("vim", "vi", "nano", "code", "emacs"):
        changes.append("编辑文件 " + " ".join(tokens[1:2]))
    elif head == "docker" and sub == "run":
        changes.append("启动容器")
    return changes


# ---------------------------------------------------------------- 注解

def build_annotations(events, errors, chains, index: CorpusIndex, envs):
    annotations = []
    chain_by_fail = {chain.fail_seq: chain for chain in chains}
    fix_map = defaultdict(list)
    fix_kind = {}
    for chain in chains:
        for seq, _cmd in chain.steps:
            if chain.fail_seq not in fix_map[seq]:
                fix_map[seq].append(chain.fail_seq)
            fix_kind.setdefault(seq, chain.kind)
    seen_keys = set()
    for position, event in enumerate(events):
        ann = Annotation(seq=event.seq)
        ann.role = command_role(event.cmd)
        failure = errors.get(event.seq)
        ann.error = failure
        if event.exit_code is None:
            ann.status = "suspected" if failure is not None else "unknown"
            ann.status_conf = "low"
        elif event.exit_code == 0:
            ann.status = "ok"
            ann.status_conf = "high"
        else:
            ann.status = "fail"
            ann.status_conf = "high" if event.stderr else "medium"
        ann.intent = classify_intent(event)
        ann.confidence = ann.status_conf
        key = event.head
        if key and not is_trivial(event.cmd):
            ann.novelty = "new" if key not in seen_keys else None
            seen_keys.add(key)
        level, why = danger_of(event.cmd)
        ann.danger = level
        if level == "danger":
            ann.add("危险操作：%s" % why)
        previous = events[position - 1] if position else None
        if ann.status not in ("fail", "suspected"):
            ann.changes = describe_changes(event, previous, envs)
        if ann.changes:
            for change in ann.changes:
                ann.add("改变：" + change)
        if failure is not None:
            prefix = "推测" if failure.inferred else "报错"
            ann.add("%s %s：%s" % (prefix, failure.signature, failure.detail))
            if failure.exit_code is not None:
                ann.add("退出码 %s" % failure.exit_code)
        annotations.append(ann)

    # 修复链回填
    for chain in chains:
        fail_ann = annotations[chain.fail_seq - 1]
        fail_ann.steps = [cmd for _seq, cmd in chain.steps]
        fail_ann.verified = chain.verified
        fail_ann.verified_at = chain.verify_seq
        fail_ann.repair_probability = chain.probability
        if chain.steps:
            fail_ann.add("修复动作：" + " › ".join(cmd for _seq, cmd in chain.steps))
        else:
            fail_ann.add("没有修复动作，直接重跑")
        if chain.verify_seq:
            retry_event = events[chain.verify_seq - 1]
            if chain.verified:
                fail_ann.add("在 #%d 重跑并成功" % chain.verify_seq)
            elif retry_event.exit_code is None:
                fail_ann.add("在 #%d 重跑（未记录退出码，无法确认）" % chain.verify_seq)
            else:
                fail_ann.add("在 #%d 重跑仍失败（退出码 %s）" % (chain.verify_seq, retry_event.exit_code))

    # 修复动作的注解
    for seq, fails in fix_map.items():
        ann = annotations[seq - 1]
        ann.fix_of = sorted(set(fails))
        source = annotations[max(ann.fix_of) - 1]
        category = source.error.category if source.error else ""
        if fix_kind.get(seq) == "correction":
            ann.intent = "修正输入后重跑"
        else:
            ann.intent = fix_intent(category, events[seq - 1].cmd)
        ann.motivation = "修复 #%d 的报错" % source.seq
        if source.error is not None:
            ann.add("针对 #%d 的 %s：%s" % (source.seq, source.error.signature, source.error.detail))
        if source.verified:
            if source.verified_at == ann.seq:
                ann.add("这条命令本身就是修复后的验证重跑（退出码 0）")
            else:
                ann.add("随后 #%s 的重跑验证了这条修复" % source.verified_at)
            ann.confidence = "high" if source.status_conf == "high" else "medium"

    # 输入错误 / 权限缺失的自动纠正
    for ann in annotations:
        if ann.status not in ("fail", "suspected") or ann.error is None:
            continue
        correction = correction_for_event(events[ann.seq - 1], index, ann.error)
        if correction:
            ann.correction = correction
            ann.add("更正建议：%s（%s）" % (correction["command"], "；".join(correction["reasons"][:2])))

    # 动机（为什么敲这一行）
    for position, ann in enumerate(annotations):
        event = events[position]
        previous = events[position - 1] if position else None
        if ann.fix_of:
            continue
        if ann.status in ("fail", "suspected"):
            if ann.steps:
                ann.motivation = "执行失败，随后用修复动作救场"
            else:
                ann.motivation = "执行失败，暂时没看到修复动作"
        elif previous is not None and errors.get(previous.seq) is not None and ann.role == "inspect":
            ann.motivation = "排查 #%d 的报错" % previous.seq
            if ann.evidence:
                ann.add("只读排查，不改动环境")
        elif previous is not None and previous.sid == event.sid and _retry_kind(previous, event) == "retry" and errors.get(previous.seq):
            ann.motivation = "重试 #%d（怀疑是瞬时故障）" % previous.seq
        elif command_head(event.cmd) == "cd":
            ann.motivation = "切换工作目录"
        elif position == 0 or (previous is not None and previous.sid != event.sid):
            ann.motivation = "会话开始：先确认环境和项目状态"
        else:
            ann.motivation = ann.intent
        if ann.status == "ok" and ann.steps:
            ann.motivation = "重跑并确认修复生效"
    return annotations


# ---------------------------------------------------------------- 统计

def compute_stats(events, annotations, chains, sessions):
    status_counts = Counter(ann.status for ann in annotations)
    known = status_counts.get("ok", 0) + status_counts.get("fail", 0)
    fails = status_counts.get("fail", 0)
    verified_chains = [chain for chain in chains if chain.verified and chain.retry_seq]
    durations = []
    for chain in verified_chains:
        fail_event = events[chain.fail_seq - 1]
        retry_event = events[chain.verify_seq - 1]
        if fail_event.ts and retry_event.ts and retry_event.ts >= fail_event.ts:
            durations.append(retry_event.ts - fail_event.ts)
    signatures = Counter(
        ann.error.signature for ann in annotations if ann.error is not None
    )
    intents = Counter(ann.intent for ann in annotations if ann.intent)
    commands = Counter(event.head for event in events if event.head)
    sudo_count = sum(1 for event in events if command_tokens(event.cmd) and command_tokens(event.cmd)[0] == "sudo")
    novelty = [ann for ann in annotations if ann.novelty]
    danger = [ann for ann in annotations if ann.danger == "danger"]
    changes = sum(len(ann.changes) for ann in annotations)
    times = [event.ts for event in events if event.ts]
    return {
        "events": len(events),
        "sessions": len(sessions),
        "known": known,
        "ok": status_counts.get("ok", 0),
        "fail": fails,
        "suspected": status_counts.get("suspected", 0),
        "unknown": status_counts.get("unknown", 0),
        "error_rate": (fails / float(known)) if known else 0.0,
        "chains": len(chains),
        "verified_chains": len(verified_chains),
        "mttr": (sum(durations) / len(durations)) if durations else None,
        "signatures": signatures.most_common(8),
        "intents": intents.most_common(8),
        "commands": commands.most_common(8),
        "sudo": sudo_count,
        "novelty": len(novelty),
        "danger": len(danger),
        "changes": changes,
        "first_ts": min(times) if times else 0,
        "last_ts": max(times) if times else 0,
    }


# ---------------------------------------------------------------- 主入口

def analyze(events, cfg=None, meta=None, with_context=True) -> Analysis:
    cfg = cfg or Config()
    meta = meta or {}
    if not events:
        return Analysis(
            events=[],
            anns=[],
            sessions=[],
            stats=compute_stats([], [], [], []),
            sources=meta.get("files", []),
            warnings=meta.get("warnings", []),
        )
    env_cache = EnvCache()
    envs = {}
    for event in events:
        historical = bool(getattr(event, "distro", None))
        overrides = {
            "distro": getattr(event, "distro", None),
            "project": getattr(event, "project", None),
            "branch": getattr(event, "branch", None),
            "venv": getattr(event, "venv", None),
            "container": getattr(event, "container", None) if getattr(event, "container", None) is not None else (False if historical else None),
            "ssh": getattr(event, "ssh", None) if getattr(event, "ssh", None) is not None else (False if historical else None),
            "wsl": getattr(event, "wsl", None) if getattr(event, "wsl", None) is not None else (False if historical else None),
            "is_root": getattr(event, "is_root", None) if getattr(event, "is_root", None) is not None else (False if historical else None),
        }
        envs[event.seq] = env_cache.get(event.cwd, event.user, event.host, overrides)
    sessions = build_sessions(events, cfg.idle_gap, envs)
    errors = {event.seq: err_mod.classify_event(event) for event in events}
    infer_failures(events, errors)
    index = CorpusIndex(events)
    chains = []
    for position, event in enumerate(events):
        if event.exit_code == 0:
            continue
        chain = find_chain(events, position, errors, cfg.window)
        if chain:
            chain.probability = causal.chain_probability(chain, events, errors)
            chains.append(chain)
    annotations = build_annotations(events, errors, chains, index, envs)
    stats = compute_stats(events, annotations, chains, sessions)
    result = Analysis(
        events=events,
        anns=annotations,
        sessions=sessions,
        stats=stats,
        sources=meta.get("files", []),
        warnings=meta.get("warnings", []),
        envs=envs,
    )
    try:
        repairs.apply(result, repairs.load(cfg))
    except (OSError, ValueError):
        pass
    result.stats = compute_stats(events, annotations, chains, sessions)
    if with_context:
        attach_contexts(result, getattr(cfg, "context_window", 20))
    try:
        labels.apply(result, cfg)
    except (OSError, ValueError):
        pass
    return result
