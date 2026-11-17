"""用前后几十条命令推断"当时在干什么"，并给出单条命令的目的。

它不是读心：只根据命令、错误、项目类型和修复链做加权判断，并明确给出置信度。
"""

from __future__ import annotations

from dataclasses import dataclass

from .intent import command_role
from .model import command_tokens
from .util import truncate


@dataclass
class TaskContext:
    label: str
    goal: str
    phase: str
    confidence: str
    score: float
    purpose: str = ""
    summary: str = ""
    start_seq: int = 0
    end_seq: int = 0

    def to_dict(self):
        return {
            "label": self.label,
            "goal": self.goal,
            "phase": self.phase,
            "confidence": self.confidence,
            "score": round(self.score, 2),
            "purpose": self.purpose,
            "summary": self.summary,
            "start_seq": self.start_seq,
            "end_seq": self.end_seq,
        }


@dataclass(frozen=True)
class Rule:
    name: str
    label: str
    goal: str
    heads: tuple = ()
    pairs: tuple = ()
    tokens: tuple = ()
    categories: tuple = ()
    kinds: tuple = ()


RULES = (
    Rule(
        name="python",
        label="Python 依赖与环境",
        goal="让 {project} 能安装依赖并正常运行",
        heads=("python", "python3", "python2", "pip", "pip3", "pipx", "pytest", "tox", "uv", "poetry", "flask"),
        pairs=(("python3", "-m"), ("pip", "install"), ("pip3", "install"), ("python", "-m")),
        tokens=("venv", "requirements", "flask", "django", "pytest", "pip ", "module"),
        categories=("MODULE", "PIP668", "CMD_NOT_FOUND:pytest", "BUILD"),
        kinds=("python", "django"),
    ),
    Rule(
        name="node",
        label="Node 开发服务",
        goal="让 {project} 的开发服务在本地跑起来",
        heads=("npm", "yarn", "pnpm", "node", "npx", "vite", "next"),
        pairs=(("npm", "run"), ("npm", "install"), ("yarn", "run"), ("pnpm", "run")),
        tokens=("package.json", "node_modules", "vite", "webpack", "dev server", "3000"),
        categories=("PORT", "CMD_NOT_FOUND:npm", "CMD_NOT_FOUND:node"),
        kinds=("node", "typescript"),
    ),
    Rule(
        name="git",
        label="Git 同步与提交",
        goal="把本地改动安全地同步到远端",
        heads=("git",),
        pairs=(("git", "push"), ("git", "pull"), ("git", "rebase"), ("git", "commit"), ("git", "merge")),
        tokens=("origin", "remote", "rebase", "non-fast-forward", "rejected"),
        categories=("GIT_REJECT", "GIT_CONFLICT"),
    ),
    Rule(
        name="apt",
        label="Ubuntu 软件包管理",
        goal="在 Ubuntu 上安装/升级需要的软件包",
        heads=("apt", "apt-get", "dpkg", "snap", "add-apt-repository"),
        pairs=(("apt", "install"), ("apt", "upgrade"), ("apt-get", "install"), ("dpkg", "-i")),
        tokens=("install", "upgrade", "jq", "lock-frontend", "dpkg"),
        categories=("PERM:dpkg-lock", "LOCK:dpkg"),
    ),
    Rule(
        name="docker",
        label="Docker 与容器",
        goal="让 Docker 可用并管理容器",
        heads=("docker", "docker-compose", "podman", "ctr", "nerdctl"),
        tokens=("docker.sock", "container", "image", "compose"),
        categories=("DOCKER", "PERM:docker"),
    ),
    Rule(
        name="service",
        label="系统服务运维",
        goal="让 {service} 服务按预期运行",
        heads=("systemctl", "service", "nginx", "apachectl", "ufw", "crontab"),
        pairs=(("systemctl", "restart"), ("systemctl", "reload"), ("systemctl", "status")),
        tokens=("nginx.conf", "reload", "restart", "service", "journalctl"),
        categories=("PERM",),
    ),
    Rule(
        name="network",
        label="网络与端口排查",
        goal="定位网络/端口问题的原因",
        heads=("curl", "wget", "ping", "ss", "netstat", "lsof", "dig", "nslookup", "nc", "traceroute"),
        tokens=("localhost", "127.0.0.1", "port", "http", "dns"),
        categories=("NET",),
    ),
    Rule(
        name="disk",
        label="磁盘空间清理",
        goal="释放磁盘/日志空间，让系统恢复正常",
        heads=("df", "du", "journalctl", "ncdu"),
        tokens=("vacuum", "disk", "space", "/var/log", "autoremove", "clean"),
        categories=("DISK",),
    ),
    Rule(
        name="build",
        label="构建与测试",
        goal="确认 {project} 能构建并通过测试",
        heads=("make", "cmake", "cargo", "go", "mvn", "gradle", "pytest", "tox", "meson"),
        tokens=("build", "test", "compile", "make"),
        categories=("BUILD",),
        kinds=("cmake", "make", "rust", "go", "java"),
    ),
    Rule(
        name="script",
        label="脚本执行权限",
        goal="让脚本/文件具备正确的执行权限",
        heads=("chmod", "chown", "chattr"),
        tokens=("+x", "permission", "deploy.sh", "chmod"),
        categories=("PERM:exec",),
    ),
    Rule(
        name="config",
        label="修改配置",
        goal="修改配置并让改动生效",
        heads=("vim", "vi", "nano", "emacs", "code", "sed", "tee"),
        tokens=("conf", "config", "nginx", "yaml", "toml", "env"),
    ),
    Rule(
        name="deploy",
        label="部署与发布",
        goal="把 {project} 部署到目标环境",
        heads=("bash", "sh", "ansible", "terraform", "helm", "kubectl"),
        tokens=("deploy", "release", "rollout", "helm", "kubectl"),
    ),
    Rule(
        name="explore",
        label="熟悉项目环境",
        goal="了解当前目录、项目和仓库状态",
        heads=("ls", "ll", "la", "pwd", "cd", "tree", "find", "fd", "cat", "which", "type", "uname"),
        tokens=("ls", "status", "tree"),
    ),
)

DEFAULT_CONTEXT = TaskContext(
    label="日常操作",
    goal="完成当前目录下的操作",
    phase="推进",
    confidence="low",
    score=0.0,
)


def _same_project(left, right):
    if left is None or right is None:
        return True
    if left.project is None or right.project is None:
        return True
    return left.project == right.project


def _window_events(analysis, seq, window):
    events = analysis.events
    index = seq - 1
    session = analysis.session_of.get(seq)
    low = max(0, index - window)
    high = min(len(events) - 1, index + window)
    if session is not None:
        low = max(low, session.events[0].seq - 1)
        high = min(high, session.events[-1].seq - 1)
    current_env = analysis.envs.get(seq)
    start = index
    while start - 1 >= low and _same_project(analysis.envs.get(events[start - 1].seq), current_env):
        start -= 1
    end = index
    while end + 1 <= high and _same_project(analysis.envs.get(events[end + 1].seq), current_env):
        end += 1
    return events[start: end + 1], start + 1, end + 1


def _window_features(analysis, window_events):
    features = []
    for event in window_events:
        tokens = command_tokens(event.cmd)
        head = tokens[0] if tokens else ""
        sub = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
        ann = analysis.ann(event.seq)
        features.append((event, head, sub, event.cmd.lower(), ann.error))
    return features


def _score_rule(rule, features, current_seq, scale, project_kind):
    score = 0.0
    hits = []
    for event, head, sub, text, error in features:
        local = 0
        if head in rule.heads:
            local += 2
        if (head, sub) in rule.pairs:
            local += 3
        local += min(3, sum(1 for token in rule.tokens if token in text))
        if error is not None:
            if error.signature in rule.categories or error.category in rule.categories:
                local += 5
        if local:
            distance = abs(event.seq - current_seq)
            weight = 1.0 / (1.0 + distance / float(max(1, scale)))
            score += local * weight
            if local >= 3:
                hits.append((event.seq, event.cmd))
    if project_kind and project_kind in rule.kinds:
        score += 1.5
    return score, hits


def _dominant_project(analysis, window_events, current_env):
    if current_env is not None and current_env.project:
        return current_env.project
    counts = {}
    for event in window_events:
        env = analysis.envs.get(event.seq)
        if env is not None and env.project:
            counts[env.project] = counts.get(env.project, 0) + 1
    if not counts:
        return "当前项目"
    return max(counts.items(), key=lambda item: item[1])[0]


def _service_name(window_events):
    names = ("nginx", "docker", "mysql", "postgresql", "redis", "ssh", "cron", "apache2", "ufw")
    for event in window_events:
        text = event.cmd.lower()
        for name in names:
            if name in text:
                return name
    return "系统服务"


def _phase(analysis, ann, window_events):
    if ann.fix_of:
        return "修复"
    if ann.status in ("fail", "suspected"):
        return "排查"
    if ann.role == "inspect" and any(
        analysis.ann(event.seq).status in ("fail", "suspected") for event in window_events if event.seq < ann.seq
    ):
        return "排查"
    if any(analysis.ann(event.seq).verified for event in window_events if event.seq < ann.seq):
        if ann.role == "run" or ann.intent.startswith(("运行", "查看", "检查")):
            return "验证"
    if ann.intent.startswith(("安装", "创建虚拟环境", "更新包索引", "设置环境变量")):
        return "准备"
    if ann.intent.startswith(("删除", "清理", "结束", "卸载")):
        return "清理"
    if ann.intent.startswith(("提交", "推送", "拉取", "同步")):
        return "同步"
    return "推进"


def _focus(event):
    tokens = command_tokens(event.cmd)
    head = tokens[0] if tokens else ""
    if head in ("ss", "lsof", "netstat", "nc"):
        return "端口占用"
    if head == "journalctl":
        return "服务日志"
    if head in ("df", "du"):
        return "磁盘占用"
    if head == "git":
        return "仓库状态"
    if head in ("ps", "pgrep"):
        return "进程"
    return "现场"


def _nearest_failure(analysis, seq, window_events, before=True):
    candidates = [event.seq for event in window_events if (event.seq < seq if before else event.seq > seq)]
    if before:
        candidates = sorted(candidates, reverse=True)
    else:
        candidates = sorted(candidates)
    for candidate in candidates:
        ann = analysis.ann(candidate)
        if ann.error is not None and ann.status in ("fail", "suspected"):
            return ann
    return None


def _setup_thing(event):
    tokens = command_tokens(event.cmd)
    head = tokens[0] if tokens else ""
    if head in ("apt", "apt-get", "snap", "dpkg"):
        packages = [token for token in tokens[2:] if not token.startswith("-")]
        return "软件包 " + " ".join(packages[:2]) if packages else "系统软件包"
    if head in ("pip", "pip3", "pipx", "uv", "poetry"):
        return "Python 依赖"
    if head in ("python", "python3") and "-m" in tokens and "venv" in tokens:
        return "虚拟环境"
    if head == "npm":
        return "Node 依赖"
    return "前置条件"


def _purpose(analysis, ann, ctx, window_events, window):
    event = analysis.event(ann.seq)
    tokens = command_tokens(event.cmd)
    head = tokens[0] if tokens else ""
    if ann.fix_of:
        source = analysis.ann(max(ann.fix_of))
        signature = source.error.signature if source.error else "上一条失败"
        return "修复 #%d 的 %s：%s" % (source.seq, signature, ann.intent)
    if ann.status in ("fail", "suspected"):
        signature = ann.error.signature if ann.error is not None else "未知错误"
        return "尝试%s；因 %s 失败，成为当前任务的卡点" % (ann.intent, signature)
    for earlier in window_events:
        earlier_ann = analysis.ann(earlier.seq)
        if earlier_ann.verified and earlier_ann.verified_at == ann.seq:
            return "重跑 #%d 的命令，验证修复是否真的生效" % earlier.seq
    previous_failure = _nearest_failure(analysis, ann.seq, window_events, before=True)
    if ann.role == "inspect" and previous_failure is not None:
        return "收集%s信息，定位 #%d 的 %s，为下一步修复提供依据" % (
            _focus(event),
            previous_failure.seq,
            previous_failure.error.signature if previous_failure.error else "错误",
        )
    # 为后面的运行/测试做准备
    if ann.intent.startswith(("安装", "创建虚拟环境", "更新包索引", "运行 npm 脚本")) or head in (
        "apt",
        "apt-get",
        "pip",
        "pip3",
        "npm",
    ):
        later = None
        for other in window_events:
            if other.seq <= ann.seq or other.seq > ann.seq + 10:
                continue
            other_ann = analysis.ann(other.seq)
            if other_ann.role in ("run", "inspect") or other.seq == ann.verified_at:
                later = other
                break
        if later is not None:
            return "为后面的 %s 准备%s，推进“%s”" % (
                truncate(later.cmd, 30),
                _setup_thing(event),
                ctx.label,
            )
    if ann.verified and ann.verified_at and ann.verified_at < ann.seq:
        return "重跑并确认前面的修复生效，验证“%s”是否真的完成" % ctx.label
    if ann.intent.startswith(("提交", "推送", "拉取", "同步")):
        return "%s，把当前阶段的改动同步到远端" % ann.intent
    return "%s，服务于“%s”" % (ann.intent, ctx.label)


def _summary(analysis, seq, window_events, start_seq, end_seq, window):
    parts = []
    current = analysis.ann(seq)
    if current.error is not None and current.status in ("fail", "suspected"):
        parts.append("#%d 报 %s" % (seq, current.error.signature))
    else:
        previous = _nearest_failure(analysis, seq, window_events, before=True)
        if previous is not None and previous.error is not None:
            parts.append("#%d 报 %s" % (previous.seq, previous.error.signature))
    verified = []
    for event in window_events:
        ann = analysis.ann(event.seq)
        if ann.verified and ann.verified_at and ann.verified_at != event.seq:
            after = 0 if ann.verified_at >= seq else 1
            verified.append((after, abs(ann.verified_at - seq), ann))
    if verified:
        verified.sort(key=lambda item: (item[0], item[1]))
        parts.append("#%d 验证成功" % verified[0][2].verified_at)
    if len(parts) < 2:
        heads = []
        for event in window_events:
            tokens = command_tokens(event.cmd)
            if tokens and tokens[0] not in heads:
                heads.append(tokens[0])
        if heads:
            parts.append("相关命令：" + "、".join(heads[:4]))
    if not parts:
        parts.append("没有明显的关键命令")
    return "；".join(parts) + "（窗口 #%d–#%d，共 %d 条）" % (start_seq, end_seq, len(window_events))


def infer_context(analysis, seq, window=20):
    if not analysis.events:
        return DEFAULT_CONTEXT
    window_events, start_seq, end_seq = _window_events(analysis, seq, max(1, window))
    current_env = analysis.envs.get(seq)
    project_kind = current_env.project_kind if current_env is not None else None
    features = _window_features(analysis, window_events)
    best = None
    best_score = 0.0
    best_hits = []
    for rule in RULES:
        score, hits = _score_rule(rule, features, seq, window, project_kind)
        if score > best_score:
            best, best_score, best_hits = rule, score, hits
    if best is None or best_score < 1.5:
        best = Rule(
            name="daily",
            label="日常操作",
            goal="完成当前目录下的操作",
        )
        best_score = 0.0
    project = _dominant_project(analysis, window_events, current_env)
    goal = best.goal.format(project=project, service=_service_name(window_events))
    if best_score >= 8:
        confidence = "high"
    elif best_score >= 4:
        confidence = "medium"
    else:
        confidence = "low"
    ctx = TaskContext(
        label=best.label,
        goal=goal,
        phase="推进",
        confidence=confidence,
        score=best_score,
        start_seq=start_seq,
        end_seq=end_seq,
    )
    ann = analysis.ann(seq)
    ctx.phase = _phase(analysis, ann, window_events)
    ctx.purpose = _purpose(analysis, ann, ctx, window_events, window)
    ctx.summary = _summary(analysis, seq, window_events, start_seq, end_seq, window)
    return ctx


def attach_contexts(analysis, window=20, seqs=None):
    """给注解补上任务、目标、阶段、目的、上下文摘要。可只算指定序号。"""
    if not analysis.events:
        return analysis
    window = max(1, int(window or 20))
    if seqs is None:
        targets = list(analysis.anns)
    else:
        targets = [analysis.ann(seq) for seq in seqs if 1 <= seq <= len(analysis.events)]
    for ann in targets:
        context = infer_context(analysis, ann.seq, window)
        analysis.contexts[ann.seq] = context
        ann.task = context.label
        ann.task_goal = context.goal
        ann.phase = context.phase
        ann.purpose = context.purpose
        ann.context_summary = context.summary
    return analysis
