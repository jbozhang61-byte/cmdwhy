"""错误识别：把 stderr / 退出码归一成稳定的错误签名，供检索与知识库复用。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .util import first_line, strip_ansi, truncate

RULES = (
    ("PIP668", re.compile(r"externally-managed-environment|pep[ -]?668|break-system-packages", re.I)),
    (
        "DOCKER",
        re.compile(
            r"cannot connect to the docker daemon|docker daemon socket|"
            r"permission denied while trying to connect to the docker daemon|is the docker daemon running",
            re.I,
        ),
    ),
    ("GIT_REJECT", re.compile(r"\[rejected\]|non-fast-forward|failed to push some refs|updates were rejected", re.I)),
    ("GIT_CONFLICT", re.compile(r"merge conflict|automatic merge failed|conflict \(content\)|needs merge", re.I)),
    (
        "CMD_NOT_FOUND",
        re.compile(
            r"command not found|: not found\b|is not a git command|unknown command|"
            r"no such command|not installed\.|command not found:",
            re.I,
        ),
    ),
    (
        "PORT",
        re.compile(r"address already in use|eaddrinuse|port \d+ (?:is )?already|bind: address already in use", re.I),
    ),
    (
        "PERM",
        re.compile(
            r"permission denied|operation not permitted|eacces|access is denied|"
            r"are you root|must be root|only root|requires root|superuser",
            re.I,
        ),
    ),
    (
        "AUTH",
        re.compile(
            r"authentication failed|permission denied \(publickey|401 unauthorized|403 forbidden|"
            r"invalid credentials|could not read username|access token|bad credentials",
            re.I,
        ),
    ),
    (
        "MODULE",
        re.compile(r"modulenotfounderror|importerror|no module named|cannot find module|module not found|cannot import name", re.I),
    ),
    (
        "BUILD",
        re.compile(
            r"undefined reference|fatal error: .*: no such file|make: \*\*\*|cmake error|gcc: error|"
            r"failed building wheel|error: command .* failed with exit status|linker command failed",
            re.I,
        ),
    ),
    ("DISK", re.compile(r"no space left|disk quota exceeded|read-only file system|insufficient space|inode", re.I)),
    (
        "LOCK",
        re.compile(r"could not get lock|unable to acquire the dpkg frontend lock|dpkg frontend lock|database is locked|another process", re.I),
    ),
    (
        "NET",
        re.compile(
            r"connection refused|network is unreachable|temporary failure in name resolution|"
            r"name or service not known|could not resolve host|connection timed out|timed out|"
            r"connection reset by peer|ssl certificate problem|no route to host",
            re.I,
        ),
    ),
    ("SYNTAX", re.compile(r"syntax error|unexpected token|invalid syntax|parse error|unexpected eof", re.I)),
    ("KILLED", re.compile(r"\bkilled\b|out of memory|oom-kill|cannot allocate memory", re.I)),
    (
        "USAGE",
        re.compile(r"invalid option|unrecognized option|unknown option|usage:|invalid argument|missing required argument", re.I),
    ),
)

EXIT_MAP = {
    126: ("PERM:exec", "退出码 126：文件存在但没有执行权限"),
    127: ("CMD_NOT_FOUND", "退出码 127：命令不存在"),
    130: ("INTERRUPT", "退出码 130：被 Ctrl-C 中断"),
    137: ("KILLED", "退出码 137：被 SIGKILL 终止（常见于内存不足）"),
    143: ("INTERRUPT", "退出码 143：被 SIGTERM 终止"),
    2: ("USAGE", "退出码 2：参数或用法错误"),
}

MISSING_WORD_PATTERNS = (
    re.compile(r"([\w.+-]+): command not found", re.I),
    re.compile(r"bash: ([\w.+-]+): command not found", re.I),
    re.compile(r"zsh: ([\w.+-]+): command not found", re.I),
    re.compile(r"command not found: ([\w.+-]+)", re.I),
    re.compile(r"git: '([\w-]+)' is not a git command", re.I),
    re.compile(r"unknown command '([\w-]+)'", re.I),
    re.compile(r"the program '([\w.+-]+)' is currently not installed", re.I),
    re.compile(r"([\w.+-]+): not found", re.I),
)

MODULE_PATTERNS = (
    re.compile(r"no module named '?([\w.]+)'?", re.I),
    re.compile(r"cannot find module '?([\w./@-]+)'?", re.I),
)

PATH_PATTERNS = (
    re.compile(r"'([^']+)': no such file or directory", re.I),
    re.compile(r"([/\w.~-]+): no such file or directory", re.I),
    re.compile(r"cannot (?:access|open|find) '?([^':\s]+)'?", re.I),
)


@dataclass
class ErrorInfo:
    category: str = "GENERIC"
    signature: str = "GENERIC"
    detail: str = ""
    confidence: str = "low"
    text: str = ""
    exit_code: int = None
    missing_word: str = None
    path: str = None
    module: str = None
    port: str = None
    inferred: bool = False
    note: str = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "signature": self.signature,
            "detail": self.detail,
            "confidence": self.confidence,
            "exit_code": self.exit_code,
            "missing_word": self.missing_word,
            "path": self.path,
            "module": self.module,
            "port": self.port,
            "inferred": self.inferred,
            "note": self.note,
        }


def _extract_missing_word(text):
    for pattern in MISSING_WORD_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _extract_path(text):
    for pattern in PATH_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _extract_module(text):
    for pattern in MODULE_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _extract_port(text, cmd):
    match = re.search(r":(\d{2,5})\b", text or "")
    if match:
        return match.group(1)
    match = re.search(r"\bport\s+(\d{2,5})\b", (text or "") + " " + (cmd or ""), re.I)
    return match.group(1) if match else None


def _qualifier(category, text, cmd):
    low = (text or "").lower()
    if category == "PERM":
        if "docker" in low:
            return "docker"
        if "dpkg" in low or "lock" in low:
            return "dpkg-lock"
        if "publickey" in low:
            return "ssh"
        if (cmd or "").strip().startswith("./") or "cannot execute" in low:
            return "exec"
        return "file"
    if category == "AUTH":
        if "publickey" in low:
            return "ssh-key"
        if "401" in low or "403" in low:
            return "http"
        return "credentials"
    if category == "NET":
        if "name resolution" in low or "resolve host" in low or "name or service" in low:
            return "dns"
        if "refused" in low:
            return "refused"
        if "timed out" in low or "timeout" in low:
            return "timeout"
        return "generic"
    if category == "LOCK":
        return "dpkg" if "dpkg" in low or "apt" in low else "generic"
    if category == "GIT_REJECT":
        return "fetch-first" if "fetch first" in low or "non-fast-forward" in low else "generic"
    if category == "DISK":
        if "inode" in low:
            return "inode"
        if "read-only" in low:
            return "readonly"
        return "space"
    if category == "KILLED":
        return "oom" if "memory" in low or "oom" in low else "signal"
    return None


def _detail_line(text):
    fallback = ""
    chosen = ""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not fallback:
            fallback = line
        if re.search(r"error|denied|not found|failed|rejected|refused|cannot|exception|traceback", line, re.I):
            chosen = line
    return truncate(first_line(chosen or fallback, 200), 170)


def classify_text(text, cmd="", exit_code=None) -> ErrorInfo:
    raw = strip_ansi(text or "")
    info = ErrorInfo(text=raw, exit_code=exit_code, confidence="high")
    for category, pattern in RULES:
        if pattern.search(raw):
            info.category = category
            break
    qualifier = _qualifier(info.category, raw, cmd)
    info.signature = info.category + (":" + qualifier if qualifier else "")
    info.detail = _detail_line(raw)
    info.missing_word = _extract_missing_word(raw)
    info.path = _extract_path(raw)
    info.module = _extract_module(raw)
    info.port = _extract_port(raw, cmd)
    return _refine(info, cmd)


def _refine(info, cmd):
    if info.category == "CMD_NOT_FOUND" and info.missing_word:
        info.signature = "CMD_NOT_FOUND:" + info.missing_word
    elif info.category == "MODULE" and info.module:
        info.signature = "MODULE:" + info.module.split(".")[0]
    elif info.category == "PORT" and info.port:
        info.signature = "PORT:" + info.port
    elif info.category == "PERM" and (cmd or "").strip().startswith("./"):
        info.signature = "PERM:exec"
    return info


def classify_event(event) -> ErrorInfo:
    """优先用 hook 捕获的 stderr；没有的话只能靠退出码推断。"""
    if event is None:
        return None
    if event.stderr:
        return classify_text(event.stderr, cmd=event.cmd, exit_code=event.exit_code)
    if event.exit_code is not None and event.exit_code != 0:
        mapped = EXIT_MAP.get(event.exit_code)
        if mapped:
            signature, detail = mapped
            category = signature.split(":", 1)[0]
            info = ErrorInfo(
                category=category,
                signature=signature,
                detail=detail,
                confidence="medium",
                exit_code=event.exit_code,
            )
            if category == "PERM" and not signature.endswith(":exec"):
                info.signature = "PERM"
            return info
        return ErrorInfo(
            category="GENERIC",
            signature="GENERIC",
            detail="退出码 %d（没有捕获到错误输出）" % event.exit_code,
            confidence="low",
            exit_code=event.exit_code,
        )
    return None


def infer_error(category, detail, signature=None, confidence="low", **kwargs) -> ErrorInfo:
    """给"没有退出码但上下文强烈暗示失败"的事件构造一个推测错误。"""
    info = ErrorInfo(
        category=category,
        signature=signature or category,
        detail=detail,
        confidence=confidence,
        inferred=True,
    )
    for key, value in kwargs.items():
        if hasattr(info, key):
            setattr(info, key, value)
    return info


def normalize_error_text(text) -> str:
    """归一化错误文本：去掉路径、时间、数字、引号内容，便于聚类。"""
    value = strip_ansi(text or "").lower()
    value = re.sub(r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(?:\.\d+)?", "<ts>", value)
    value = re.sub(r"0x[0-9a-f]+", "<hex>", value)
    value = re.sub(r"/[^\s:'\"]+", "<path>", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", value)
    value = re.sub(r"'[^']*'", "'<x>'", value)
    value = re.sub(r'"[^"]*"', '"<x>"', value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:240]


def signature_label(signature: str) -> str:
    if not signature:
        return "未知"
    if ":" not in signature:
        return signature
    head, tail = signature.split(":", 1)
    return "%s（%s）" % (head, tail)
