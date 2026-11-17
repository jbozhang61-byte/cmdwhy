"""内置演示数据：一段真实感的 Ubuntu 日常（含报错、sudo 重试、拼写错误、端口占用）。

它不读你的真实历史，用来验证分析效果：cmdwhy demo
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .model import Event

BASE = datetime(2026, 11, 17, 9, 12, 0, tzinfo=timezone(timedelta(hours=8))).timestamp()

HOME = "/home/ubuntu"
API = HOME + "/work/api"
WEB = API + "/web"
INFRA = HOME + "/infra"


def _ev(minute, cmd, exit_code=None, stderr=None, cwd=API, source="hook", **extra):
    data = {
        "ts": BASE + minute * 60.0,
        "cmd": cmd,
        "exit_code": exit_code,
        "stderr": stderr,
        "cwd": cwd,
        "user": "ubuntu",
        "host": "devbox",
        "distro": "Ubuntu 24.04",
        "shell": "bash",
        "source": source,
    }
    data.update(extra)
    return Event(**data)


def demo_events():
    events = []
    # ---------------- S1 09:12 从依赖报错到跑起来 ----------------
    events += [
        _ev(0, "ls -la", 0, project="api", branch="main", venv=".venv"),
        _ev(0.5, "git status", 0, project="api", branch="main", venv=".venv"),
        _ev(
            1,
            "python3 app.py",
            1,
            stderr='Traceback (most recent call last):\n  File "app.py", line 3, in <module>\n'
            "    import flask\nModuleNotFoundError: No module named 'flask'",
            project="api",
            branch="main",
            venv=".venv",
        ),
        _ev(
            3,
            "pip install -r requirements.txt",
            1,
            stderr="error: externally-managed-environment\n\n"
            "× This environment is externally managed\n"
            "╰─> To install Python packages system-wide, try apt install python3-xyz\n"
            "    or use a virtual environment. See PEP 668 for more information.",
            project="api",
            branch="main",
            venv=".venv",
        ),
        _ev(5, "sudo apt install python3-venv -y", 0, project="api", branch="main", venv=".venv"),
        _ev(6, "python3 -m venv .venv", 0, project="api", branch="main", venv=".venv"),
        _ev(7, "source .venv/bin/activate", 0, project="api", branch="main", venv=".venv"),
        _ev(8, "pip install -r requirements.txt", 0, project="api", branch="main", venv=".venv"),
        _ev(9, "python3 app.py", 0, project="api", branch="main", venv=".venv", duration_ms=2100),
        _ev(12, "pytest -q", 127, stderr="bash: pytest: command not found", project="api", branch="main", venv=".venv"),
        _ev(13, "pip install pytest", 0, project="api", branch="main", venv=".venv"),
        _ev(14, "pytest -q", 0, project="api", branch="main", venv=".venv", duration_ms=4300),
        _ev(18, "git status", 0, project="api", branch="main", venv=".venv"),
        _ev(
            20,
            "git puhs",
            1,
            stderr="git: 'puhs' is not a git command. See 'git --help'.",
            project="api",
            branch="main",
            venv=".venv",
        ),
        _ev(20.5, "git push", 0, project="api", branch="main", venv=".venv"),
        _ev(22, "git log --oneline -5", 0, project="api", branch="main", venv=".venv"),
        _ev(30, "git checkout -b feat/history-why", 0, project="api", branch="feat/history-why", venv=".venv"),
    ]
    # ---------------- S2 11:40 权限、端口、Docker ----------------
    events += [
        _ev(
            148,
            "apt install jq",
            1,
            stderr="E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)\n"
            "E: Unable to lock the administration directory (/var/lib/dpkg/), are you root?",
            project="api",
            branch="main",
            venv=".venv",
        ),
        _ev(149, "sudo apt install jq -y", 0, project="api", branch="main", venv=".venv"),
        _ev(152, "./deploy.sh", 126, stderr="bash: ./deploy.sh: Permission denied", project="api", branch="main", venv=".venv"),
        _ev(153, "chmod +x deploy.sh", 0, project="api", branch="main", venv=".venv"),
        _ev(154, "./deploy.sh", 0, project="api", branch="main", venv=".venv", duration_ms=820),
        _ev(
            160,
            "npm run dev",
            1,
            stderr="Error: listen EADDRINUSE: address already in use :::3000\n"
            "    at Server.setupListenHandle [as _listen2] (node:net:1751:16)",
            cwd=WEB,
            project="api",
            branch="main",
            venv=None,
        ),
        _ev(161, "ss -ltnp | grep 3000", 0, cwd=WEB, project="api", branch="main"),
        _ev(162, "lsof -i :3000", 0, cwd=WEB, project="api", branch="main"),
        _ev(163, "kill 4242", 0, cwd=WEB, project="api", branch="main"),
        _ev(164, "npm run dev", 0, cwd=WEB, project="api", branch="main", duration_ms=600),
        _ev(
            170,
            "docker ps",
            1,
            stderr="permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: "
            "Get \"http://%2Fvar%2Frun%2Fdocker.sock/v1.45/containers/json\": dial unix /var/run/docker.sock: connect: permission denied",
            cwd=WEB,
            project="api",
            branch="main",
        ),
        _ev(171, "sudo docker ps", 0, cwd=WEB, project="api", branch="main"),
        _ev(175, "journalctl -u docker -n 20 --no-pager", 0, cwd=WEB, project="api", branch="main"),
    ]
    # ---------------- S3 15:05 纯历史（无退出码） ----------------
    events += [
        _ev(353, "cd ~/infra", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(353.5, "ls", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(354, "vim nginx.conf", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(356, "nginx -t", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(357, "sudo nginx -t", 0, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(358, "systemctl reload nginx", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(359, "sudo systemctl reload nginx", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(361, "curl -I localhost", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(362, 'curl -sS -o /dev/null -w "%{http_code}" localhost/health', None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(365, "journalctl -u nginx -n 20 --no-pager", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(366, "df -h", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(367, "du -sh /var/log", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(368, "sudo journalctl --vacuum-size=200M", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
        _ev(371, "uptime", None, cwd=INFRA, source="bash_history", project="infra", branch="main", venv=None),
    ]
    # ---------------- S4 18:20 远端拒绝推送 ----------------
    events += [
        _ev(548, "git push origin main", None, source="bash_history", project="api", branch="main", venv=".venv"),
        _ev(548.5, "git pull --rebase", None, source="bash_history", project="api", branch="main", venv=".venv"),
        _ev(549, "git push origin main", None, source="bash_history", project="api", branch="main", venv=".venv"),
        _ev(550, "git log --oneline -5", None, source="bash_history", project="api", branch="main", venv=".venv"),
        _ev(553, "git checkout -b fix/port-config", None, source="bash_history", project="api", branch="fix/port-config", venv=".venv"),
        _ev(556, "python3 -m pytest -q", None, source="bash_history", project="api", branch="fix/port-config", venv=".venv"),
        _ev(560, "git add -A", None, source="bash_history", project="api", branch="fix/port-config", venv=".venv"),
        _ev(561, 'git commit -m "fix: use env port"', None, source="bash_history", project="api", branch="fix/port-config", venv=".venv"),
        _ev(562, "git push", None, source="bash_history", project="api", branch="fix/port-config", venv=".venv"),
    ]
    # ---------------- S5 21:00 系统维护 ----------------
    events += [
        _ev(708, "uname -a", None, cwd=HOME, source="bash_history", project=None, branch=None, venv=None),
        _ev(709, "df -h", None, cwd=HOME, source="bash_history", project=None, branch=None, venv=None),
        _ev(710, "sudo apt update", 0, cwd=HOME, project=None, branch=None, venv=None),
        _ev(712, "sudo apt upgrade -y", 0, cwd=HOME, project=None, branch=None, venv=None),
        _ev(714, "sudo apt autoremove -y", 0, cwd=HOME, project=None, branch=None, venv=None),
        _ev(716, "sudo journalctl --vacuum-size=200M", 0, cwd=HOME, project=None, branch=None, venv=None),
        _ev(718, "sudo systemctl restart nginx", 0, cwd=HOME, project=None, branch=None, venv=None),
        _ev(719, "curl -I https://example.com", 0, cwd=HOME, project=None, branch=None, venv=None),
        _ev(720, "htop", None, cwd=HOME, source="bash_history", project=None, branch=None, venv=None),
    ]
    # 模拟 shell 内建 history 的编号（501 起），演示“按 history 数字分析”
    for index, event in enumerate(events, start=501):
        event.hist_id = index
    return events
