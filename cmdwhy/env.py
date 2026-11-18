"""工作环境推断：目录、项目类型、Git 分支、虚拟环境、发行版、容器/SSH。"""

from __future__ import annotations

import copy
import getpass
import os
import platform
import re
import socket
import shutil
import subprocess
from functools import lru_cache

from .model import EnvInfo

PROJECT_MARKERS = (
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("requirements.txt", "python"),
    ("Pipfile", "python"),
    ("manage.py", "django"),
    ("package.json", "node"),
    ("tsconfig.json", "typescript"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("Gemfile", "ruby"),
    ("composer.json", "php"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("build.gradle.kts", "java"),
    ("CMakeLists.txt", "cmake"),
    ("Makefile", "make"),
    ("docker-compose.yml", "docker"),
    ("compose.yaml", "docker"),
    ("Dockerfile", "docker"),
    ("Chart.yaml", "kubernetes"),
    ("kustomization.yaml", "kubernetes"),
    ("main.tf", "terraform"),
    ("terraform.tfstate", "terraform"),
)

KIND_ORDER = (
    "python",
    "django",
    "node",
    "typescript",
    "go",
    "rust",
    "java",
    "ruby",
    "php",
    "dotnet",
    "cmake",
    "make",
    "docker",
    "kubernetes",
    "terraform",
)

VENV_NAMES = (".venv", "venv", "env", ".env", "virtualenv")


@lru_cache(maxsize=1)
def read_os_release():
    data = {}
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    data[key] = value.strip().strip('"').strip("'")
            break
        except OSError:
            continue
    return data


@lru_cache(maxsize=1)
def detect_distro() -> str:
    if os.name == "nt":
        return "Windows %s" % platform.release()
    info = read_os_release()
    name = info.get("NAME") or platform.system()
    version = info.get("VERSION_ID") or ""
    pretty = info.get("PRETTY_NAME") or ""
    if info.get("ID") == "ubuntu" and version:
        return "Ubuntu " + version
    if pretty:
        return pretty
    return (name + " " + version).strip()


@lru_cache(maxsize=1)
def is_container() -> bool:
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        return any(token in content for token in ("docker", "kubepods", "containerd", "lxc"))
    except OSError:
        return False


@lru_cache(maxsize=1)
def is_ssh() -> bool:
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY") or os.environ.get("SSH_CLIENT"))


@lru_cache(maxsize=1)
def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


@lru_cache(maxsize=1)
def detect_pkg_manager():
    if os.name == "nt":
        return "winget" if shutil.which("winget") else None
    for name in ("apt-get", "dnf", "pacman", "zypper", "apk", "brew"):
        if shutil.which(name):
            return "apt" if name == "apt-get" else name
    return None


def _git(cwd, args):
    try:
        proc = subprocess.run(
            ["git", "-C", cwd] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip()


@lru_cache(maxsize=256)
def git_info(cwd):
    if not cwd or not os.path.isdir(cwd):
        return None
    root = _git(cwd, ["rev-parse", "--show-toplevel"])
    if not root:
        return None
    branch = _git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"]) or ""
    if branch == "HEAD":
        branch = "detached"
    status = _git(cwd, ["status", "--porcelain", "-uno"])
    return {
        "root": root,
        "branch": branch,
        "dirty": bool(status),
    }


def detect_project(cwd):
    """向上找项目根，返回 (root, kind, markers)。"""
    if not cwd:
        return None
    try:
        current = os.path.abspath(cwd)
    except (TypeError, ValueError):
        return None
    if not os.path.isdir(current):
        return None
    root = None
    for _ in range(16):
        if os.path.isdir(os.path.join(current, ".git")):
            root = current
            break
        if any(os.path.exists(os.path.join(current, name)) for name, _ in PROJECT_MARKERS):
            root = current
            break
        try:
            current_names = os.listdir(current)
        except OSError:
            current_names = []
        if any(name.endswith((".csproj", ".sln", ".fsproj")) for name in current_names):
            root = current
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    if not root:
        return None
    kinds = []
    marks = []
    for name, kind in PROJECT_MARKERS:
        if os.path.exists(os.path.join(root, name)):
            kinds.append(kind)
            marks.append(name)
    try:
        root_names = os.listdir(root)
    except OSError:
        root_names = []
    if any(name.endswith((".csproj", ".sln", ".fsproj")) for name in root_names):
        kinds.append("dotnet")
        marks.append("*.csproj")
    if not kinds and os.path.isdir(os.path.join(root, ".git")):
        kinds = ["git"]
    kind = next((item for item in KIND_ORDER if item in kinds), kinds[0] if kinds else None)
    return root, kind, marks


def detect_venv(cwd):
    if not cwd:
        return None
    venv_env = os.environ.get("VIRTUAL_ENV")
    try:
        current = os.path.abspath(cwd)
    except (TypeError, ValueError):
        return None
    if venv_env:
        try:
            if os.path.commonpath([os.path.abspath(venv_env), current]) == os.path.abspath(venv_env):
                return os.path.basename(venv_env.rstrip("/\\")) or venv_env
        except ValueError:
            pass
    for _ in range(8):
        for name in VENV_NAMES:
            candidate = os.path.join(current, name)
            if os.path.isfile(os.path.join(candidate, "pyvenv.cfg")):
                return name
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def venv_python(venv_name, cwd):
    if not venv_name or not cwd:
        return None
    current = os.path.abspath(cwd)
    for _ in range(8):
        cfg = os.path.join(current, venv_name, "pyvenv.cfg")
        if os.path.isfile(cfg):
            try:
                with open(cfg, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if "version" in line.lower() and "=" in line:
                            return line.split("=", 1)[1].strip()
            except OSError:
                return None
            return None
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def build_env(cwd, user=None, host=None, overrides=None) -> EnvInfo:
    env = EnvInfo(cwd=cwd or os.getcwd())
    env.user = user or _safe_user()
    env.host = host or _safe_host()
    env.is_root = _is_root()
    env.container = is_container()
    env.ssh = is_ssh()
    env.wsl = is_wsl()
    env.pkg_manager = detect_pkg_manager()
    env.shell = os.path.basename(os.environ.get("SHELL") or os.environ.get("ComSpec") or "") or None
    env.distro = detect_distro()
    project = detect_project(env.cwd)
    if project:
        env.project_root, env.project_kind, _marks = project
        env.project = os.path.basename(env.project_root)
    info = git_info(env.cwd)
    if info:
        env.branch = info["branch"]
        env.dirty = info["dirty"]
        if not env.project:
            env.project = os.path.basename(info["root"])
            env.project_root = info["root"]
    env.venv = detect_venv(env.cwd)
    if env.venv:
        env.python = venv_python(env.venv, env.cwd)
    for key, value in (overrides or {}).items():
        if value and hasattr(env, key):
            setattr(env, key, value)
    return env


def _safe_user():
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or os.environ.get("USERNAME")


def _safe_host():
    try:
        return socket.gethostname()
    except OSError:
        return None


def _is_root() -> bool:
    if hasattr(os, "geteuid"):
        try:
            return os.geteuid() == 0
        except OSError:
            return False
    return False


class EnvCache:
    """按工作目录缓存环境探测结果，避免对每条历史都跑 git。"""

    def __init__(self, fallback_cwd=None):
        self.fallback_cwd = fallback_cwd or os.getcwd()
        self._cache = {}

    def get(self, cwd, user=None, host=None, overrides=None) -> EnvInfo:
        overrides = overrides or {}
        if not cwd:
            # history 输出 / JSONL 里没有 cwd：不要拿当前目录冒充当时环境
            env = EnvInfo(user=user, host=host)
            env.is_root = _is_root()
            env.container = is_container()
            env.ssh = is_ssh()
            env.shell = os.path.basename(os.environ.get("SHELL") or os.environ.get("ComSpec") or "") or None
            for field, value in overrides.items():
                if value and hasattr(env, field):
                    setattr(env, field, value)
            return env
        key = cwd
        if key not in self._cache:
            self._cache[key] = build_env(key, user=user, host=host)
        env = copy.copy(self._cache[key])
        if user:
            env.user = user
        if host:
            env.host = host
            if host != _safe_host() and not (overrides or {}).get("distro"):
                env.distro = None
        for field, value in (overrides or {}).items():
            if value and hasattr(env, field):
                setattr(env, field, value)
        return env


def quick_env(cwd=None) -> EnvInfo:
    return build_env(cwd or os.getcwd())
