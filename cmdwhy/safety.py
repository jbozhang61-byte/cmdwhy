"""危险命令识别：只用于提示与阻止自动执行建议，不拦截用户自己敲的命令。"""

from __future__ import annotations

import re

DANGER_RULES = (
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*[rf][a-zA-Z]*\s+(/|/\*|~|~/|\$HOME)\s*$"), "递归删除根目录或家目录"),
    (re.compile(r"\brm\s+-rf\s+/\s*$"), "递归删除根目录"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "格式化文件系统"),
    (re.compile(r"\bdd\b[^|]*\bof=/dev/(sd|nvme|hd)"), "直接写块设备"),
    (re.compile(r">\s*/dev/(sd|nvme|hd)"), "直接写块设备"),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt)\b"), "关机/重启"),
    (re.compile(r"\binit\s+[06]\b"), "切换运行级别"),
    (re.compile(r"\bchmod\s+-R\s+777\s+/\s*$"), "把根目录改成 777"),
    (re.compile(r"\bchown\s+-R\s+[^\s]+\s+/\s*$"), "递归修改根目录属主"),
    (re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork 炸弹"),
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba)?sh\b"), "把网络脚本直接交给 shell"),
    (re.compile(r"\bgit\s+push\s+.*--force"), "强制推送（可能覆盖远端历史）"),
    (re.compile(r"\bdocker\s+system\s+prune\s+-a"), "清理所有未使用镜像"),
    (re.compile(r"\btruncate\s+-s\s*0\b"), "清空文件内容"),
)

WARN_RULES = (
    (re.compile(r"\brm\s+(-[a-zA-Z]+\s+)*[^|]*"), "删除文件"),
    (re.compile(r"\bmv\s+.*\s+/(tmp|dev/null)"), "移动文件"),
    (re.compile(r"\bsudo\s+su\b"), "切换 root"),
    (re.compile(r"\bkill\s+-9\b"), "强制结束进程"),
)


def danger_of(cmd: str):
    """返回 (级别, 说明)，级别是 danger / warn / None。"""
    text = (cmd or "").strip()
    if not text:
        return None, None
    for pattern, why in DANGER_RULES:
        if pattern.search(text):
            return "danger", why
    for pattern, why in WARN_RULES:
        if pattern.search(text):
            return "warn", why
    return None, None


def is_dangerous(cmd: str) -> bool:
    level, _ = danger_of(cmd)
    return level == "danger"


def safe_to_autofix(cmd: str) -> bool:
    level, _ = danger_of(cmd)
    return level is None
