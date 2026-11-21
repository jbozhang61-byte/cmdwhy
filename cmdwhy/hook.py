"""shell hook：记录每条命令的退出码、工作目录和发行版，供分析使用。"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import time

from .config import Config
from .env import detect_distro, is_container, is_ssh, is_wsl, runtime_profile
from .model import Event
from .sources import append_event
from .util import atomic_write

BASH_MARK_START = "# >>> cmdwhy >>>"
BASH_MARK_END = "# <<< cmdwhy <<<"
ZSH_MARK_START = "# >>> cmdwhy >>>"
ZSH_MARK_END = "# <<< cmdwhy <<<"

BASH_HOOK = r"""# cmdwhy shell hook（由 cmdwhy hook install 生成，可重复安装）
if [ -n "$_CMDWHY_HOOK_LOADED" ]; then
    return 0 2>/dev/null || true
fi
_CMDWHY_HOOK_LOADED=1
_CMDWHY_LAST=""
_CMDWHY_LAST_NUM=""
_CMDWHY_DISTRO=""

_cmdwhy_record() {
    local ec=$?
    local line cmd num
    line=$(HISTTIMEFORMAT='' history 1 2>/dev/null)
    num=$(printf '%s\n' "$line" | sed -n 's/^ *\([0-9][0-9]*\)  *.*/\1/p')
    cmd=$(printf '%s\n' "$line" | sed 's/^ *[0-9][0-9]*  *//')
    if [ -z "$cmd" ]; then return; fi
    # 同一个 history 编号才视为重复；连续执行同一条命令也要分别记录
    if [ -n "$num" ] && [ "$num" = "$_CMDWHY_LAST_NUM" ]; then return; fi
    if [ -z "$num" ] && [ "$cmd" = "$_CMDWHY_LAST" ]; then return; fi
    _CMDWHY_LAST="$cmd"
    _CMDWHY_LAST_NUM="$num"
    case "$cmd" in
        cmdwhy*|_cmdwhy*) return ;;
    esac
    if [ -z "$_CMDWHY_DISTRO" ]; then
        _CMDWHY_DISTRO=$(sed -n 's/^PRETTY_NAME="\(.*\)"/\1/p' /etc/os-release 2>/dev/null)
    fi
    command __CMDWHY__ record --exit "$ec" --cmd "$cmd" --hist-id "$num" --cwd "$PWD" --shell bash --distro "$_CMDWHY_DISTRO" >/dev/null 2>&1 &
    disown $! 2>/dev/null || true
}

# bash 5.1+ 允许 PROMPT_COMMAND 是数组；不能粗暴覆盖
if declare -p PROMPT_COMMAND 2>/dev/null | grep -q 'declare -a'; then
    PROMPT_COMMAND+=(_cmdwhy_record)
elif [ -n "$PROMPT_COMMAND" ]; then
    case "$PROMPT_COMMAND" in
        *_cmdwhy_record*) ;;
        *) PROMPT_COMMAND="_cmdwhy_record;$PROMPT_COMMAND" ;;
    esac
else
    PROMPT_COMMAND="_cmdwhy_record"
fi
"""

ZSH_HOOK = r"""# cmdwhy shell hook（由 cmdwhy hook install 生成，可重复安装）
if [[ -n "$_CMDWHY_HOOK_LOADED" ]]; then
    return 0
fi
_CMDWHY_HOOK_LOADED=1
_CMDWHY_CMD=""
_CMDWHY_DISTRO=""

_cmdwhy_preexec() {
    _CMDWHY_CMD="$1"
}

_cmdwhy_precmd() {
    local ec=$?
    local cmd="$_CMDWHY_CMD"
    _CMDWHY_CMD=""
    if [ -z "$cmd" ]; then return; fi
    case "$cmd" in
        cmdwhy*|_cmdwhy*|exit|logout) return ;;
    esac
    if [ -z "$_CMDWHY_DISTRO" ]; then
        _CMDWHY_DISTRO=$(sed -n 's/^PRETTY_NAME="\(.*\)"/\1/p' /etc/os-release 2>/dev/null)
    fi
    command __CMDWHY__ record --exit "$ec" --cmd "$cmd" --cwd "$PWD" --shell zsh --distro "$_CMDWHY_DISTRO" >/dev/null 2>&1
}

autoload -Uz add-zsh-hook 2>/dev/null
if ! add-zsh-hook preexec _cmdwhy_preexec 2>/dev/null; then
    preexec_functions+=(_cmdwhy_preexec)
fi
if ! add-zsh-hook precmd _cmdwhy_precmd 2>/dev/null; then
    precmd_functions+=(_cmdwhy_precmd)
fi
"""

FISH_HOOK = r"""# cmdwhy shell hook（由 cmdwhy hook install 生成，可重复安装）
if set -q _CMDWHY_HOOK_LOADED
    return
end
set -g _CMDWHY_HOOK_LOADED 1
set -g _CMDWHY_CMD ""

function _cmdwhy_preexec --on-event fish_preexec
    set -g _CMDWHY_CMD $argv
end

function _cmdwhy_record --on-event fish_prompt
    set -l ec $status
    if not set -q _CMDWHY_CMD
        return
    end
    set -l cmd $_CMDWHY_CMD
    set -e _CMDWHY_CMD
    test -z "$cmd"; and return
    string match -q 'cmdwhy*' -- $cmd; and return
    test "$cmd" = exit; and return
    test "$cmd" = logout; and return
    set -l distro (sed -n 's/^PRETTY_NAME="\(.*\)"/\1/p' /etc/os-release 2>/dev/null)
    command __CMDWHY__ record --exit $ec --cmd "$cmd" --cwd "$PWD" --shell fish --distro "$distro" >/dev/null 2>&1
end
"""


def invocation():
    exe = shutil.which("cmdwhy")
    if exe:
        return shlex.quote(exe)
    return shlex.quote(sys.executable) + " -m cmdwhy"


HOOKS = {"bash": BASH_HOOK, "zsh": ZSH_HOOK, "fish": FISH_HOOK}


def hook_script(shell, cfg):
    template = HOOKS.get(shell)
    if template is None:
        raise ValueError("不支持的 shell：%s" % shell)
    return template.replace("__CMDWHY__", invocation())


def hook_path(shell, cfg):
    return os.path.join(cfg.hooks_dir, "cmdwhy.%s" % shell)


def rc_path(shell):
    home = os.path.expanduser("~")
    if shell == "bash":
        return os.path.join(home, ".bashrc")
    if shell == "fish":
        return os.path.join(home, ".config", "fish", "config.fish")
    return os.path.join(home, ".zshrc")


def install(cfg, shells=("bash", "zsh"), rc_override=None, print_only=False):
    cfg.ensure()
    messages = []
    for shell in shells:
        script = hook_script(shell, cfg)
        path = hook_path(shell, cfg)
        if print_only:
            messages.append(script)
            continue
        atomic_write(path, script)
        rc = rc_override or rc_path(shell)
        os.makedirs(os.path.dirname(os.path.abspath(rc)), exist_ok=True)
        block = "%s\nsource %s\n%s" % (BASH_MARK_START, shlex.quote(path), BASH_MARK_END)
        existing = ""
        if os.path.exists(rc):
            with open(rc, "r", encoding="utf-8", errors="replace") as fh:
                existing = fh.read()
        if BASH_MARK_START in existing:
            messages.append("%s 已经安装过（%s），跳过。" % (shell, rc))
            continue
        with open(rc, "a", encoding="utf-8", newline="\n") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(block + "\n")
        messages.append("已写入 %s，并在 %s 末尾加入加载语句。" % (path, rc))
    if not print_only:
        messages.append("新开一个对应 shell 的终端，或 source 刚写入的 rc 文件后生效。")
    return messages


def uninstall(cfg, shells=("bash", "zsh", "fish"), rc_override=None):
    messages = []
    for shell in shells:
        rc = rc_override or rc_path(shell)
        if not os.path.exists(rc):
            messages.append("%s 不存在，跳过。" % rc)
            continue
        with open(rc, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        out = []
        skip = False
        removed = False
        for line in lines:
            if line.strip() == BASH_MARK_START:
                skip = True
                removed = True
                continue
            if line.strip() == BASH_MARK_END:
                skip = False
                continue
            if not skip:
                out.append(line)
        if removed:
            atomic_write(rc, "".join(out))
            messages.append("已从 %s 移除 cmdwhy 加载语句。" % rc)
        else:
            messages.append("%s 里没有找到 cmdwhy 配置。" % rc)
    return messages


def status(cfg, shells=("bash", "zsh", "fish"), rc_override=None):
    data = {
        "home": cfg.home,
        "store": cfg.store_path,
        "store_exists": os.path.exists(cfg.store_path),
        "events": 0,
        "cmd_in_path": shutil.which("cmdwhy") or "",
        "shells": [],
    }
    if data["store_exists"]:
        try:
            with open(cfg.store_path, "r", encoding="utf-8", errors="replace") as fh:
                data["events"] = sum(1 for line in fh if line.strip())
        except OSError:
            pass
    for shell in shells:
        rc = rc_override or rc_path(shell)
        installed = False
        if os.path.exists(rc):
            with open(rc, "r", encoding="utf-8", errors="replace") as fh:
                installed = BASH_MARK_START in fh.read()
        data["shells"].append({"shell": shell, "rc": rc, "installed": installed, "script": hook_path(shell, cfg)})
    return data


def make_event(cfg, args) -> Event:
    stderr = None
    if getattr(args, "stderr", None):
        stderr = args.stderr
    elif getattr(args, "stderr_file", None):
        try:
            with open(args.stderr_file, "r", encoding="utf-8", errors="replace") as fh:
                stderr = fh.read()[-4000:]
        except OSError:
            stderr = None
    raw_hist = getattr(args, "hist_id", None)
    try:
        hist_id = int(raw_hist) if raw_hist not in (None, "") else None
    except (TypeError, ValueError):
        hist_id = None
    event = Event(
        ts=float(getattr(args, "ts", None) or time.time()),
        cmd=args.cmd,
        hist_id=hist_id,
        exit_code=getattr(args, "exit", None),
        cwd=getattr(args, "cwd", None) or os.getcwd(),
        user=getattr(args, "user", None),
        host=getattr(args, "host", None),
        shell=getattr(args, "shell", None),
        distro=getattr(args, "distro", None),
        container=is_container(),
        ssh=is_ssh(),
        wsl=is_wsl(),
        is_root=(hasattr(os, "geteuid") and os.geteuid() == 0),
        runtime=runtime_profile(),
        stderr=stderr,
        source="hook",
    )
    return event


def record(cfg, args):
    event = make_event(cfg, args)
    append_event(cfg, event)
    return event
