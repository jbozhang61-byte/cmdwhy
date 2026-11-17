"""脱敏：避免把密码、token、私钥写进历史分析数据。"""

from __future__ import annotations

import re

_PATTERNS = (
    (
        re.compile(
            r"(?i)(--?(?:password|passwd|pass|token|secret|api[-_]?key|access[-_]?key|"
            r"auth[-_]?token|client[-_]?secret)(?:=|\s+))([^\s'\"]+)"
        ),
        r"\1***",
    ),
    (
        re.compile(
            r"(?i)\b(export\s+[A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*=)([^\s]+)"
        ),
        r"\1***",
    ),
    (re.compile(r"(https?://[^\s/:@]+:)([^\s/@]+)(@)"), r"\1***\3"),
    (re.compile(r"(?i)(authorization:\s*(?:bearer|token|basic)\s+)([A-Za-z0-9._~+/=-]+)"), r"\1***"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b"), "***"),
    (re.compile(r"\b(AKIA[0-9A-Z]{12,})\b"), "***"),
    (re.compile(r"(?i)\b(ssh-(?:rsa|ed25519|ecdsa)\s+AAAA)[A-Za-z0-9+/=]{20,}"), r"\1…***"),
    (
        re.compile(r"(?<![A-Za-z0-9_./@-])(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_./@-])"),
        lambda m: m.group(0)[:4] + "…***",
    ),
)

_EXTRA = []


def add_pattern(regex: str, repl: str = "***"):
    """用户自定义脱敏规则（config 之外的 API）。"""
    _EXTRA.append((re.compile(regex), repl))


def redact_text(text: str) -> str:
    if not text:
        return text
    out = str(text)
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    for pattern, repl in _EXTRA:
        out = pattern.sub(repl, out)
    return out


def redact_command(cmd: str) -> str:
    return redact_text(cmd)


def redact_error(text: str) -> str:
    return redact_text(text)
